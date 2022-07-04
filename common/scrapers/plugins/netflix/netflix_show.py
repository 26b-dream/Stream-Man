# TODO: This scraper doesn't really work, needs to be updated
from __future__ import annotations

from typing import TYPE_CHECKING

# Standard Library
from multiprocessing.sharedctypes import Value

if TYPE_CHECKING:
    from playwright.sync_api._generated import Response
    from typing import Any, Literal, Dict, Optional
    from playwright.sync_api._generated import Page

# Standard Library
import time
from datetime import datetime
from functools import cache

# Third Party
from playwright.sync_api import sync_playwright

# Common
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_path import ExtendedPath
from common.scrapers.plugins.netflix.netflix_base import NetflixBase
from common.scrapers.shared import ScraperShowShared

# Config
from config.config import NetflixSecrets

# Apps
from shows.models import Episode, Season


class NetflixShow(NetflixBase, ScraperShowShared):
    FAVICON_URL = "https://assets.nflxext.com/ffe/siteui/common/icons/nficon2016.ico"

    @cache
    def path_from_url(self, url: str) -> ExtendedPath:
        url = url.removeprefix(self.DOMAIN)
        url = url.removeprefix("/")
        return DOWNLOADED_FILES_DIR / self.WEBSITE / ExtendedPath(url.replace("?", "/")).legalize().with_suffix(".html")

    @cache
    def show_url(self) -> str:
        return f"{self.DOMAIN}/title/{self.show_id}"

    @cache
    # it's fine to ignore the type mismatch because it is all inclusive of the parent type
    # TODO: Is there a way to write this without ignoring the type?
    def episode_url(self, episode: Episode | int | str) -> str:  # type: ignore
        if isinstance(episode, Episode):
            return f"{self.DOMAIN}/watch/{episode.episode_id}"
        else:
            return f"{self.DOMAIN}/watch/{episode}"

    @cache  # Values should never change
    def show_json_path(self) -> ExtendedPath:
        return self.path_from_url(f"{self.show_url()}").with_suffix(".json")

    # There is no seperate URL for seasons so make them a subdirectory of the show
    @cache
    def season_html_path(self, season: str) -> ExtendedPath:
        return self.path_from_url(f"{self.show_url()}/{season}")

    # There is no simple way to connect the URL of the season with the Show
    # Instead just make a function that uses the name to connect the files
    @cache  # Values should never change
    def season_json_path(self, season: str | int) -> ExtendedPath:
        return self.path_from_url(f"{self.show_url()}/{season}").with_suffix(".json")

    @cache
    def is_movie(self) -> bool:
        show_html_parsed = self.path_from_url(self.show_url()).parsed_html()
        # Determine if a given "show" is actually a movie
        for tag in show_html_parsed.strict_select("span[class='previewModal--tags-label']"):
            if "This movie is:" in tag.text:
                return True

        return False

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

    @cache
    def any_file_is_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        # Check if any show files are outdated first that way the information on them can be used
        if self.any_show_file_outdated(minimum_timestamp):
            return True

        # Ignore movies because they do not have any additional files
        if self.is_movie():
            return False

        show_json_parsed = self.show_json_path().parsed_json()
        show_json_parsed_seasons = show_json_parsed["jsonGraph"]["seasons"]

        for season_id, _season_json_parsed in show_json_parsed_seasons.items():
            if self.any_season_file_is_outdated(season_id):
                return True
        return False

    @cache
    def any_show_file_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        # Check if any files are out of date before launching the browser
        show_html_path = self.path_from_url(self.show_url())
        show_json_path = self.path_from_url(self.show_url()).with_suffix(".json")

        if show_html_path.exists():
            # Movies only have 1 file to check
            if self.is_movie():
                return show_html_path.outdated(minimum_timestamp)
            # Series have 2 files to check
            else:
                return show_html_path.outdated(minimum_timestamp) or show_json_path.outdated(minimum_timestamp)
        else:
            return True

    @cache
    def any_season_file_is_outdated(self, season_id: str, minimum_timestamp: Optional[datetime] = None) -> bool:
        season_html_path = self.season_html_path(season_id)
        season_json_path = self.season_json_path(season_id)

        # If the files are up to date nothing needs to be done
        return season_html_path.outdated(minimum_timestamp) or season_json_path.outdated(minimum_timestamp)

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
                time.sleep(1)
                page.type("div[class='pin-input-container']", number)

            # Because Netflix is weird the sleep is required to retain the user selection
            time.sleep(5)
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

    def download_response(self, response: Response):
        # All information from Netflix is under this url
        if "pathEvaluator?" in response.url:
            body = response.json()

            # Check if the information is for a specific season
            if the_tuple := self.maybe_parsed_specific_season_json(body):
                self.season_json_path(the_tuple[0]).write_json(body)
            # Check for information for a show
            if body["jsonGraph"].get("seasons"):
                # If there is a summary for every season this has to be the show json
                if all("summary" in value.keys() for value in body["jsonGraph"]["seasons"].values()):
                    show_json_path = self.show_json_path()
                    show_json_path.write_json(body)

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        # Check if files exist before creating a playwright instance
        if self.any_file_is_outdated(minimum_timestamp):
            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                page.on("response", lambda request: self.download_response(request))
                self.download_show(page, minimum_timestamp)
                if not self.is_movie():
                    self.download_seasons(page, minimum_timestamp)
                page.close()

    def download_show(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.any_show_file_outdated(minimum_timestamp):
            self.go_to_page_logged_in(page, self.show_url())

            # Open season selector if it exists so it is on the saved html
            page.click_if_exists("button[data-uia='dropdown-toggle']")

            # TODO: Verification
            html_path = self.path_from_url(self.show_url())
            html_path.write(page.content())

            # Close season selector to make season downloading more consistent
            page.click_if_exists("button[data-uia='dropdown-toggle']")

            # Only series have json files so only check for them if it's a series
            if not self.is_movie():
                self.wait_for_files(page, self.show_json_path())

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        show_json_parsed = self.show_json_path().parsed_json()
        show_json_parsed_seasons = show_json_parsed["jsonGraph"]["seasons"]

        for season_id, season_json_parsed in show_json_parsed_seasons.items():
            season_name = season_json_parsed["summary"]["value"]["name"]

            if self.any_season_file_is_outdated(season_id, minimum_timestamp):
                # All season pages have to be downloaded from the show page so open the show page
                # Only do this the first time, all later pages can reuse existing page
                if not page.url == self.show_url():
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
                # TODO: Verification
                self.wait_for_files(page, self.season_json_path(season_id))
                self.season_html_path(season_id).write(page.content())

    def update_all(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if self.is_movie():
            self.update_show(minimum_info_timestamp, minimum_modified_timestamp)
            self.update_movie(minimum_info_timestamp, minimum_modified_timestamp)
        else:
            self.update_show(minimum_info_timestamp, minimum_modified_timestamp)
            self.update_season(minimum_info_timestamp, minimum_modified_timestamp)
            self.update_episode(minimum_info_timestamp, minimum_modified_timestamp)

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

            # TODO: Do I like the "Series" name?
            self.show_info.media_type = "Movie" if self.is_movie() else "Series"

            self.show_info.add_timestamps_and_save(show_html_path)

    def update_season(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        show_json_path = self.show_json_path()
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
        show_json_path = self.show_json_path()
        show_json_parsed = show_json_path.parsed_json()
        show_json_parsed_seasons = show_json_parsed["jsonGraph"]["seasons"]
        # Go thoguh each season on the show json file
        for season_id, season_json_parsed in show_json_parsed_seasons.items():
            season_json_path = self.season_json_path(season_id)
            season_json_parsed = season_json_path.parsed_json()
            specific_season_json_parsed = self.parsed_specific_season_json(season_json_parsed)[1]
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
                    episode_info.add_timestamps_and_save(show_json_path)

    def update_movie(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        # For shows that have only a single season the show information is just not available in Show.json
        # Using Show.html is required here but it is more fragile and likely to break in the future
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            show_html_path = self.path_from_url(self.show_url())
            show_html_parsed = show_html_path.parsed_html()

            if self.show_id:
                season_info = Season().get_or_new(season_id=self.show_id, show=self.show_info)[0]
                episode_info = Episode().get_or_new(episode_id=self.show_id, season=season_info)[0]
            else:  # This is impossible but it fixes a Pylance type error
                raise Value("No show id found")

            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season_info.name = self.show_info.name
                season_info.thumbnail_url = self.show_info.thumbnail_url
                season_info.image_url = self.show_info.image_url
                season_info.number = "0"
                season_info.sort_order = 0

                season_info.add_timestamps_and_save(show_html_path)

            # Episode ID is literall the same as the show_id
            if not episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                episode_info.name = self.show_info.name
                episode_info.description = self.show_info.description
                episode_info.thumbnail_url = self.show_info.thumbnail_url
                episode_info.image_url = self.show_info.image_url = self.show_info.image_url
                episode_info.number = "0"
                episode_info.sort_order = 0
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
