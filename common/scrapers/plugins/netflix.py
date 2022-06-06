from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api._generated import Response
    from typing import Any, Literal, Dict, Optional
    from playwright.sync_api._generated import Playwright, Page

# Standard Library
import time
from datetime import date, datetime
from functools import cache

# Common
import common.extended_re as re
from common.extended_path import ExtendedPath
from common.extended_playwright import sync_playwright
from common.scrapers.shared import ScraperShowShared, ScraperUpdateShared

# Config
# Unknown
from config.config import NetflixSecrets

# Apps
# Shows
from shows.models import Episode, Season, Show


class NetflixBase:
    WEBSITE = "Netflix"
    DOMAIN = "https://www.netflix.com"
    # Example show URLs
    #   https://www.netflix.com/title/80156387
    SHOW_URL_REGEX = re.compile(r"https:\/\/www\.netflix\.com\/title\/*(?P<show_id>.*?)(?:\?|$)")
    # Example episode URLs
    #   https://www.netflix.com/watch/80156389
    EPISODE_URL_REGEX = re.compile(r"https:\/\/www\.netflix\.com\/watch\/*(?P<show_id>.*?)(?:\/|$)")


class NetflixShow(NetflixBase, ScraperShowShared):
    FAVICON_URL = "https://assets.nflxext.com/ffe/siteui/common/icons/nficon2016.ico"

    @cache  # Values should never change
    def show_url(self) -> str:
        return f"{self.DOMAIN}/title/{self.show_id}"

    @cache  # Values should never change
    def episode_url(self, episode: Episode | int | str) -> str:
        if isinstance(episode, Episode):
            return f"{self.DOMAIN}/watch/{episode.episode_id}"
        else:
            return f"{self.DOMAIN}/watch/{episode}"

    # There is no seperate URL for seasons so make them a subdirectory of the show
    @cache  # Values should never change
    def season_html_path(self, season: str) -> ExtendedPath:
        return self.path_from_url(f"{self.show_url()}/{season}", ".html")

    # There is no simple way to connect the URL of the season with the Show
    # Instead just make a function that uses the name to connect the files
    @cache  # Values should never change
    def season_json_path(self, season: str | int) -> ExtendedPath:
        return self.path_from_url(f"{self.show_url()}/{season}", ".json")

    def login_if_needed(self, page: Page, url: str) -> None:
        # Check for the button to login to determine if user is logged in
        if page.query_selector("a[class='authLinks']"):
            page.goto(f"{self.DOMAIN}/login", wait_until="networkidle")
            page.type("input[id='id_userLoginId']", NetflixSecrets.EMAIL)
            page.type("input[id='id_password']", NetflixSecrets.PASSWORD)
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle")

            # After logging in attempt to go the the original page because it will not redirect automatically
            page.goto(url, wait_until="networkidle")

    def select_user_if_needed(self, page: Page) -> bool:
        # Check if it this is the user selection page
        if page.query_selector(f"span[class='profile-name'] >> text={NetflixSecrets.NAME}"):
            page.click(f"span[class='profile-name'] >> text={NetflixSecrets.NAME}")
            page.wait_for_load_state("networkidle")
            # Entry is more reliable one character at a time for some reason so loop through each character in the PIN
            for number in str(NetflixSecrets.PIN):
                # Netflix is screwing with me try slowing down pin entry
                time.sleep(0.256)
                page.type("div[class='pin-input-container']", number)
            page.wait_for_load_state("networkidle")

            # Never automatically redirects it seems like
            page.goto(self.show_url(), wait_until="networkidle")

            return True
        return False

    def go_to_page_logged_in(
        self,
        page: Page,
        url: str,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "networkidle",
    ) -> None:
        page.goto(url, wait_until=wait_until)
        self.login_if_needed(page, url)
        # Netflix is screwing with me and showing this screen multiple times
        while self.select_user_if_needed(page):
            time.sleep(1)

    def is_movie(self) -> bool:
        show_html_parsed = self.path_from_url(self.show_url()).parsed_html()
        # Determine if a given "show" is actually a movie
        for tag in show_html_parsed.strict_select("span[class='previewModal--tags-label']"):
            if "This movie is:" in tag.text:
                return True

        return False

    def show_files_up_to_date(self, minimum_timestamp: Optional[datetime]) -> bool:
        html_path = self.path_from_url(self.show_url())
        json_path = self.path_from_url(self.show_url(), ".json")

        if html_path.exists() and self.is_movie():
            return html_path.outdated(minimum_timestamp)
        else:
            return html_path.outdated(minimum_timestamp) or json_path.outdated(minimum_timestamp)

    def parsed_specific_season_json(self, body: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        test = self.maybe_parsed_specific_season_json(body)
        if test:
            return test
        else:
            raise Exception("No season info found")

    def maybe_parsed_specific_season_json(self, body: Dict[str, Any]) -> Optional[tuple[str, Dict[str, Any]]]:
        for season_id, season in body["jsonGraph"].get("seasons", {}).items():
            if season.get("episodes"):
                return (season_id, season)

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        with sync_playwright() as playwright:
            self.download_show(playwright, minimum_timestamp)

    def download_show(self, playwright: Playwright, minimum_timestamp: Optional[datetime] = None) -> None:
        html_path = self.path_from_url(self.show_url())

        if self.show_files_up_to_date(minimum_timestamp):
            page = self.playwright_browser(playwright).new_page()
            page.on("response", self.download_show_response)
            self.go_to_page_logged_in(page, self.show_url())

            # Open season selector if it exists so it is on the saved html
            page.click_if_exists("button[data-uia='dropdown-toggle']")

            # TODO: Verification
            html_path.write(page.content())

        # Movies require no additional downloads so return early
        if self.is_movie():
            return
            self.__download_movie(playwright)
        # Download seasons for TV shows
        else:
            self.download_seasons(playwright, minimum_timestamp)

    def download_show_response(self, response: Response):
        # All information from Netflix is under this url
        if "pathEvaluator?" in response.url:
            body = response.json()
            # Make sure this is a page with season info
            # THerefore all files being iterated over are either the show or season pages
            if body["jsonGraph"].get("seasons"):
                # If there is a summary for every season this has to be the show json
                if all("summary" in value.keys() for value in body["jsonGraph"]["seasons"].values()):
                    show_json_path = self.path_from_url(self.show_url(), ".json")
                    show_json_path.write_json(body)

    def download_seasons(self, playwright: Playwright, minimum_timestamp: Optional[datetime] = None) -> None:
        page = None
        show_json_parsed = self.path_from_url(self.show_url(), ".json").parsed_json()
        show_json_parsed_seasons = show_json_parsed["jsonGraph"]["seasons"]

        for _season_id, season_json_parsed in show_json_parsed_seasons.items():
            season_name = season_json_parsed["summary"]["value"]["name"]
            # Use the season name for files because the IDs are harder to work with
            #   The hTML page only includes titles and no identifiers
            #   The id's aren't a prominent value in the json
            season_html_path = self.season_html_path(season_name)
            season_json_path = self.season_json_path(season_name)

            if season_html_path.outdated(minimum_timestamp) or season_json_path.outdated(minimum_timestamp):
                # All season pages have to be downloaded from the show page so open the show page
                # Only do this the first time, all later pages can reuse existing page
                if not page:
                    page = self.playwright_browser(playwright).new_page()
                    page.on("response", lambda request: self.download_seasons_response(request, season_json_path))
                    self.go_to_page_logged_in(page, self.show_url())

                # Season selector only exists for shows with multiple seasons
                if page.click_if_exists("button[data-uia='dropdown-toggle']"):
                    # Loop throough all seasons until a matching one is found then click it
                    for page_thing in page.query_selector_all("div[class='episodeSelector--option']"):
                        if season_name in page_thing.strict_text_content():
                            page_thing.click()
                            break

                # Response doesn't trigger consistently to download season json file
                # Do a pointless query selector until the file exists to cause response to trigger
                while not season_json_path.exists():
                    page.query_selector("html")
                    time.sleep(1)

                # TODO: Verification
                season_html_path.write(page.content())
            continue
            self.download_episodes(playwright, season_json_path, minimum_timestamp)
        # If the page was initilized close it
        if page:
            page.close()

    def download_seasons_response(self, response: Response, season_json_path: ExtendedPath) -> None:
        if "pathEvaluator?" in response.url:
            # The show json file includes the season information
            # The only way to determine the first season id is by figuring out which season has episodes listed
            # This function also works for real season pages so just re-use it even thoguh it's more complex than needed
            body = response.json()
            if self.maybe_parsed_specific_season_json(body):
                _season_id, season_specific_json_parsed = self.parsed_specific_season_json(body)
                ExtendedPath("test.json").write_json(body)
                if season_specific_json_parsed.get("summary"):
                    season_name = season_specific_json_parsed["summary"]["value"]["name"]
                    self.season_json_path(season_name).write_json(body)
                # Some json doesn't have a title for some reason
                # See https://www.netflix.com/title/81145024 season 1
                # Just pray the passed value is accurate I guess
                else:
                    season_json_path.write_json(body)

    def update_all(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if self.is_movie():
            self.update_movie(minimum_info_timestamp, minimum_modified_timestamp)
        else:
            self.update_show(minimum_info_timestamp, minimum_modified_timestamp)

    def update_movie(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        # For shows that have only a single season the show information is just not available in Show.json
        # Using Show.html is required here but it is more fragile and likely to break in the future
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            season_info = Season().get_or_new(season_id=self.show_id, show=self.show_info)[0]
            episode_info = Episode().get_or_new(episode_id=self.show_id, season=season_info)[0]

            # The show name is literally not present on the json files for some reason
            # Use the html file for most of the information
            show_html_path = self.path_from_url(self.show_url())
            show_html_parsed = show_html_path.parsed_html()

            # Show name is not present on the json file
            name = show_html_parsed.strict_select("h3[class=previewModal--section-header] strong")[0].text
            season_info.name = episode_info.name = self.show_info.name = name

            # Show description is not present on the json file
            # Some shows do not have descriptions
            #   https://www.netflix.com/title/81364944
            maybe_description = show_html_parsed.select("p[class*='preview-modal-synopsis']")
            if maybe_description:
                episode_info.description = self.show_info.description = maybe_description[0].text

            # Show image is not present on the json file
            thumbnail_selector = "div[class='videoMerchPlayer--boxart-wrapper'] > img"
            img_url = show_html_parsed.strict_select(thumbnail_selector)[0].strict_get("src")
            episode_info.thumbnail_url = self.show_info.thumbnail_url = img_url

            # TODO: Get a bigger image from the episode html file
            episode_info.image_url = self.show_info.image_url = self.show_info.thumbnail_url

            self.show_info.add_timestamps_and_save(show_html_path)
            episode_info.number = season_info.number = "0"
            episode_info.sort_order = season_info.sort_order = 0

            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season_info.add_timestamps_and_save(show_html_path)

            # Episode ID is literall the same as the show_id
            if not episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):

                duration_string = show_html_parsed.strict_select_one("span[class='duration']").text
                split_duration_string = duration_string.split(" ")

                episode_info.duration = 0
                for partial_duration in split_duration_string:
                    if partial_duration.endswith("h"):
                        episode_info.duration += int(partial_duration[:-1]) * 60 * 60
                    elif partial_duration.endswith("m"):
                        episode_info.duration += int(partial_duration[:-1]) * 60

                year_int = int(show_html_parsed.strict_select("div[class='year']")[0].text)
                episode_info.release_date = datetime(year_int, 1, 1).astimezone()

                episode_info.add_timestamps_and_save(show_html_path)

    def update_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        # For shows that have only a single season the show information is just not available in Show.json
        # Using Show.html is required here but it is more fragile and likely to break in the future
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            # The show name is literally not present on the json files for some reason
            # Use the html file for most of the information
            show_html_path = self.path_from_url(self.show_url())
            show_html_parsed = show_html_path.parsed_html()

            # Show name is not present on the json file
            title_selector = "h3[class=previewModal--section-header] strong"
            self.show_info.name = show_html_parsed.strict_select(title_selector)[0].text

            # Show description is not present on the json file
            # Some shows do not have descriptions
            #   https://www.netflix.com/title/81364944
            maybe_description = show_html_parsed.select("p[class*='preview-modal-synopsis']")
            if maybe_description:
                self.show_info.description = maybe_description[0].text

            # Show image is not present on the json file
            thumbnail_selector = "div[class='videoMerchPlayer--boxart-wrapper'] > img"
            self.show_info.thumbnail_url = show_html_parsed.strict_select(thumbnail_selector)[0].strict_get("src")
            # TODO: Is there a bigger image I can use?
            self.show_info.image_url = self.show_info.thumbnail_url
            self.show_info.add_timestamps_and_save(show_html_path)

    def update_season(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        show_json_path = self.path_from_url(self.show_url(), ".json")
        parsed_show_json = show_json_path.parsed_json()
        episodes = parsed_show_json["jsonGraph"]["seasons"].items()

        for i, season in enumerate(episodes):
            season_info = Season().get_or_new(season_id=season[0], show=self.show_info)[0]

            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                # TODO: Does shortName work as a season number for most shows?
                season_info.number = season[1]["summary"]["value"]["shortName"]
                season_info.name = season[1]["summary"]["value"]["name"]
                season_info.sort_order = i
                season_info.add_timestamps_and_save(show_json_path)

    def update_episode(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        show_json_parsed = self.path_from_url(self.show_url(), ".json").parsed_json()
        show_json_parsed_seasons = show_json_parsed["jsonGraph"]["seasons"]

        # Go thoguh each season on the show json file
        for _season_id, season_json_parsed in show_json_parsed_seasons.items():
            season_name = season_json_parsed["summary"]["value"]["name"]
            season_json_path = self.season_json_path(season_name)
            season_json_parsed = season_json_path.parsed_json()
            season_id, specific_season_json_parsed = self.parsed_specific_season_json(season_json_parsed)
            season_info = Season().get_or_new(season_id=season_id, show=self.show_info)[0]

            # Ignore season entries that are not a list of episodes
            episodes = specific_season_json_parsed.get("episodes")
            if not episodes:
                continue

            for episode in episodes.items():
                # Ignore entries that aren't references to episodes
                # Not sure what entries labeled as current is but ignore that as well
                if episode[1]["$type"] != "ref" or episode[0] == "current":
                    continue

                episode_id = episode[1]["value"][1]
                episode_entry = season_json_parsed["jsonGraph"]["videos"][episode_id]

                episode_info = Episode().get_or_new(episode_id=episode_id, season=season_info)[0]
                if not episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                    episode_info.name = episode_entry["title"]["value"]
                    episode_info.number = episode_entry["summary"]["value"]["episode"]
                    episode_info.sort_order = episode_info.number
                    # Some entries use synopsis, some use contextualSynopsis
                    # TODO: Determine why
                    episode_info.description = episode_entry.get("synopsis", {}).get("value") or episode_entry.get(
                        "contextualSynopsis", {}
                    ).get("value")
                    # TODO: Is this more accurate than the value given in the html?
                    episode_info.duration = episode_entry["runtime"]["value"]
                    episode_info.release_date = datetime.fromtimestamp(
                        episode_entry["availability"]["value"]["availabilityStartTime"] / 1000
                    ).astimezone()

                    episode_info.image_url = episode_entry["interestingMoment"]["_342x192"]["webp"]["value"]["url"]
                    episode_info.thumbnail_url = episode_info.image_url
                    episode_info.add_timestamps_and_save(self.directory)

    # # Download the episodes because they incude a bigger thumbnail not present anywhere else
    # # When video autoplays the thumbnail is not sent so just don't call this function for now
    # def __download_episodes(
    #     self, playwright: Playwright, season_json_path: ExtendedPath, minimum_timestamp: Optional[datetime] = None
    # ) -> None:
    #     parsed_json = season_json_path.parsed_json()
    #     # Go through every season on the json
    #     #   Most json only havce 1 season entry but they sometimes have multiple
    #     page = None
    #     _season_id, parsed_season_specific_json = self.parsed_specific_season_json(parsed_json)
    #     # Only the the season specifically for this json file will have episodes listed
    #     for _episode_number, episode in parsed_season_specific_json["episodes"].items():
    #         # Skip entries that are not references to episodes
    #         if episode["$type"] != "ref":
    #             continue

    #         episode_id = episode["value"][1]
    #         episode_url = self.episode_url(episode_id)
    #         episode_path = self.path_from_url(episode_url)

    #         if episode_path.outdated(minimum_timestamp):
    #             # All season pages have to be downloaded from the show page so open the show page
    #             # Only do this the first time, al later pages can reuse existing page
    #             if not page:
    #                 page = self.playwright_browser(playwright).new_page()
    #             # Nothing in the json file appears to be worth saving so just get the html file
    #             self.go_to_page_logged_in(page, episode_url)
    #             # Once this exists the information I am looking for exists on the html page
    #             page.wait_for_selector("div[data-uia='video-canvas']")
    #             episode_path.write(page.content())
    #     # If the page was initilized close it
    #     if page:
    #         page.close()

    # # Can't use json for downloading the episode information for a movie
    # # Instead use the html file to download the episode information
    # # When video autoplays the thumbnail is not sent so just don't call this function for now
    # def download_movie(self, playwright: Playwright) -> None:
    #     episode_url = self.episode_url(self.show_id)
    #     episode_path = self.path_from_url(episode_url)
    #     if not episode_path.exists():
    #         page = self.playwright_browser(playwright).new_page()
    #         # Nothing in the json file appears to be worth saving so just get the html file
    #         self.go_to_page_logged_in(page, episode_url)
    #         # Once this exists the information I am looking for exists on the html page
    #         print("Wating for download to finish")
    #         page.wait_for_selector("div[role='button'][style^='background-image']")
    #         print("DONE")
    #         episode_path.write(page.content())
    #         page.close()


class NetflixUpdate(NetflixBase, ScraperUpdateShared):
    JUSTWATCH_PROVIDER_IDS = [384]

    def justwatch_update(self, justwatch_entry: dict[str, Any], date: datetime) -> None:
        justwatch_url = justwatch_entry["offers"][0]["urls"]["standard_web"]
        show_id = re.strict_search(self.SHOW_URL_REGEX, justwatch_url).group("show_id")
        show = Show.objects.filter(website=self.WEBSITE, show_id=show_id)
        # If there is a show entry make sure the information is newer than the JustWatch entry
        if show:
            NetflixShow(show[0]).import_all(minimum_info_timestamp=date)

    # Netflix doesn't have any calendar of sorts for this function
    def check_for_updates(self, earliest_date: Optional[date] = None) -> None:
        pass
