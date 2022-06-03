from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from playwright.sync_api._generated import Response
    from typing import Any

# Standard Library
import json
import time
from datetime import datetime

# Common
import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_playwright import sync_playwright
from common.scrapers.shared import ScraperShowShared

# Config
# Unknown
from config.config import NetflixSecrets

# Apps
# Shows
from shows.models import Episode, Season, Show


class Netflix(ScraperShowShared):
    WEBSITE = "Netflix"
    DOMAIN = "https://www.netflix.com"
    FAVICON_URL = "https://assets.nflxext.com/ffe/siteui/common/icons/nficon2016.ico"
    JUSTWATCH_PROVIDER_IDS = [284]

    # Example show URLs
    #   https://www.netflix.com/title/80156387
    SHOW_URL_REGEX = re.compile(r"https:\/\/www\.netflix\.com\/title\/*(?P<show_id>.*?)(?:\?|$)")
    # Example episode URLs
    #   https://www.netflix.com/watch/80156389
    EPISODE_URL_REGEX = re.compile(r"https:\/\/www\.netflix\.com\/watch\/*(?P<show_id>.*?)(?:\/|$)")

    def show_url(self) -> str:
        return f"{self.DOMAIN}/title/{self.show_id}"

    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/watch/{episode.episode_id}"

    file_number = 0

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if not self.directory.up_to_date(minimum_timestamp):

            def handle_response(response: Response):
                if "pathEvaluator?" in response.url:
                    body = response.json()
                    # Files for TV shows
                    if body["jsonGraph"].get("seasons"):
                        if all("summary" in value.keys() for value in body["jsonGraph"]["seasons"].values()):
                            (self.temp_show_directory / "Show" / f"{self.file_number}.json").write(json.dumps(body))
                            (self.temp_show_directory / "Season" / f"{self.file_number}.json").write(json.dumps(body))
                        elif list(body["jsonGraph"]["seasons"].values())[0]["episodes"].get("0", {}):
                            (self.temp_show_directory / "Season" / f"{self.file_number}.json").write(json.dumps(body))
                    else:
                        (self.temp_show_directory / "Unknown" / f"{self.file_number}.json").write(json.dumps(body))
                self.file_number += 1

            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    DOWNLOADED_FILES_DIR / "cookies/Chrome", headless=False, accept_downloads=True, channel="chrome"
                )
                page = browser.new_page()

                page.on("response", handle_response)
                page.goto(self.show_url(), wait_until="networkidle")

                # TODO: Autoamtically login to Netflix

                # Deal with Netflix user selector
                if page.click_if_exists(f"span[class='profile-name'] >> text={NetflixSecrets.NAME}"):
                    # Wait for pin prompt
                    page.wait_for_load_state("networkidle")

                    # Entry is more reliable one character at a time for some reason so loop through each character in the PIN
                    for number in str(NetflixSecrets.PIN):
                        page.type("div[class='pin-input-container']", number)
                    page.wait_for_load_state("networkidle")

                # Open episode selector if it exists
                # Single season shows will not have this button
                number_of_seasons = 0
                if page.click_if_exists("button[data-uia='dropdown-toggle']"):
                    # Get the number of seasons
                    number_of_seasons = len(page.query_selector_all("ul[data-uia='dropdown-menu'] li")) - 1
                    # Click on the first season to close the season selector (and get the first season in the process)
                    page.click("ul[data-uia='dropdown-menu'] li")

                    # Show.html is actually required to get all information
                    # Make sure to get the show page for the first season
                    (self.temp_show_directory / "Show" / "Show.html").write(page.content())

                    for i in range(number_of_seasons + 1):
                        # Click to show list of seasons
                        page.click("button[data-uia='dropdown-toggle']")

                        # Click the next season
                        page.click(f"ul[data-uia='dropdown-menu'] li  >> nth={i}")

                        # Don't hammer on the site too much at once
                        page.wait_for_load_state("networkidle")
                        time.sleep(5)

                        (self.temp_show_directory / "Season" / f"{i}.html").write(page.content())

                # If there is no season page just save whatver page there is
                else:
                    (self.temp_show_directory / "Show" / "Show.html").write(page.content())

                if number_of_seasons == 0:
                    (self.temp_show_directory / "Show" / "Show.html").copy(
                        self.temp_show_directory / "Season" / "Season.html"
                    )

                # Get rid of old information and insert new information
                self.clean_up_download(browser, p, int(number_of_seasons * 2 + 1), self.temp_show_directory)

    def update_show_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        # For shows that have only a single season the show information is just not available in Show.json
        # Using Show.html is required here but it is more fragile and likely to break in the future
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self.parsed_files("Show", ".html")[0]
            self.show_info.name = parsed_show.strict_select("h3[class=previewModal--section-header] strong")[0].text

            # Some shows do not have descriptions
            #   https://www.netflix.com/title/81364944
            maybe_description = parsed_show.select("p[class*='preview-modal-synopsis']")
            if maybe_description:
                self.show_info.description = maybe_description[0].text
            self.show_info.thumbnail_url = parsed_show.strict_select(
                "img[class='boxart-image boxart-image-in-padded-container']"
            )[0].strict_get("src")
            # TODO: Is there a bigger image I can use?
            self.show_info.image_url = self.show_info.thumbnail_url
            self.show_info.add_timestamps_and_save(self.directory)

    def update_season_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        show_json_files = self.parsed_files("Show", ".json")
        if show_json_files:
            parsed_show = show_json_files[0]
            for sort_order, season in enumerate(parsed_show["jsonGraph"]["seasons"].items()):
                season_info = Season().get_or_new(season_id=season[0], show=self.show_info)[0]

                if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                    # TODO: Does shortName work as a season number for most shows?
                    season_info.number = season[1]["summary"]["value"]["shortName"]
                    season_info.name = season[1]["summary"]["value"]["name"]
                    season_info.sort_order = sort_order
                    season_info.add_timestamps_and_save(self.directory)
        # Movies don't have any json files so all information needs to be scraped from the html file instead
        else:
            parsed_show = self.parsed_files("Show", ".html")[0]
            season_info = Season().get_or_new(season_id=self.show_id, show=self.show_info)[0]

            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                # Movies are always single entries so set them to 1 for the number and sort_order
                season_info.sort_order = 1
                season_info.number = "1"

                # Just re-use the name from the show because it should be the same
                season_info.name = season_info.show.name
                season_info.add_timestamps_and_save(self.directory)

    def update_episode_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        season_json_files = self.parsed_files("Show", ".json")
        if season_json_files:
            for parsed_season in season_json_files:
                for season in parsed_season["jsonGraph"]["seasons"].items():
                    season_info = Season().get_or_new(season_id=season[0], show=self.show_info)[0]

                    # Ignore season entries that are not a list of episodes
                    episodes = season[1].get("episodes")
                    if not episodes:
                        continue

                    for episode in episodes.items():
                        # Ignore entries that aren't references to episodes
                        # Not sure what entries labeled as current is but ignore that as well
                        if episode[1]["$type"] != "ref" or episode[0] == "current":
                            continue

                        episode_id = episode[1]["value"][1]
                        episode_entry = parsed_season["jsonGraph"]["videos"][episode_id]

                        episode_info = Episode().get_or_new(episode_id=episode_id, season=season_info)[0]
                        if not episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                            episode_info.name = episode_entry["title"]["value"]
                            episode_info.number = episode_entry["summary"]["value"]["episode"]
                            episode_info.sort_order = episode_info.number
                            # Some entries use synopsis, some use contextualSynopsis
                            # TODO: Determine why
                            episode_info.description = episode_entry.get("synopsis", {}).get(
                                "value"
                            ) or episode_entry.get("contextualSynopsis", {}).get("value")
                            # TODO: Is this more accurate than the value given in the html?
                            episode_info.duration = episode_entry["runtime"]["value"]
                            episode_info.release_date = datetime.fromtimestamp(
                                episode_entry["availability"]["value"]["availabilityStartTime"] / 1000
                            ).astimezone()

                            # TODO: Find a bigger image for image_url
                            # TODO: Can technically get it from the episode page, but it's wasteful to download the page just for that
                            episode_info.image_url = episode_entry["interestingMoment"]["_342x192"]["webp"]["value"][
                                "url"
                            ]
                            episode_info.thumbnail_url = episode_info.image_url
                            episode_info.add_timestamps_and_save(self.directory)
        # Movies don't have any json files so all information needs to be scraped from the html file instead
        else:
            season_info = Season().get_or_new(season_id=self.show_id, show=self.show_info)[0]
            episode_info = Episode().get_or_new(episode_id=self.show_id, season=season_info)[0]
            parsed_episode = self.parsed_files("Show", ".html")[0]
            if not episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                episode_info.name = season_info.show.name
                episode_info.number = "1"
                episode_info.sort_order = 1
                # Some entries use synopsis, some use contextualSynopsis
                # TODO: Determine why
                episode_info.description = season_info.show.description

                duration = parsed_episode.strict_select("span[class='duration']")[0].text

                split_duration = duration.split(" ")
                if len(split_duration) == 2:
                    hours = int(split_duration[0].removesuffix("h"))
                else:
                    hours = 0

                minutes = int(split_duration[1].removesuffix("m"))

                episode_info.duration = hours * 60 * 60 + minutes * 60

                # Only gives the year, no more exact value
                # This is the main reason json is preferred over html values
                # For episodes Season.json does not include any release date information so json is absolutely required for them
                episode_info.release_date = datetime.strptime(
                    parsed_episode.strict_select("div[class='year']")[0].text, "%Y"
                ).astimezone()

                # TODO: Find a bigger image for image_url
                # TODO: Can technically get it from the episode page, but it's wasteful to download the page just for that
                episode_info.image_url = parsed_episode.strict_select_one(
                    "img[class*='playerModel--player__storyArt ']"
                ).strict_get("src")
                episode_info.thumbnail_url = episode_info.image_url
                episode_info.add_timestamps_and_save(self.directory)

    @classmethod
    def justwatch_update(cls, justwatch_entry: dict[str, Any], date: datetime) -> None:
        justwatch_url = justwatch_entry["offers"][0]["urls"]["standard_web"]
        season_id = re.strict_search(cls.EPISODE_URL_REGEX, justwatch_url).group("season_id")
        show = Show.objects.filter(website=cls.WEBSITE, season__season_id=season_id)

        # If there is a show entry make sure the information is newer than the JustWatch entry
        if show:
            cls(show[0]).import_all(minimum_info_timestamp=date)
