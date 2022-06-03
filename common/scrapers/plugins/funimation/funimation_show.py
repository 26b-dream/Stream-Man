from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from playwright.sync_api._generated import Response


# Standard Library
# StandardLibrary
import json
import time
from datetime import datetime

# Common
import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_path import ExtendedPath
from common.extended_playwright import sync_playwright
from common.scrapers.shared import ScraperShowShared

# Apps
from shows.models import Episode, Season

# Local
from .funimation_base import FunimationBase


class FunimationShow(ScraperShowShared, FunimationBase):
    DOMAIN = "https://www.funimation.com"
    FAVICON_URL = "https://static.funimation.com/static/img/favicon.ico"

    # Example episode URLs
    #   https://www.funimation.com/v/aria/that-wonderful-miracle
    EPISODE_URL_REGEX = re.compile(r"https:\/\/www\.funimation\.com\/v\/*(?P<show_id>.*?)\/*(?P<episode_id>.*)")

    def show_url(self) -> str:
        return f"{self.DOMAIN}/shows/{self.show_id}"

    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/v/{self.show_id}/{episode.episode_id}"

    # Information is the same logged in and logged out
    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if not self.directory.up_to_date(minimum_timestamp):
            # Temporary directory that all files will be downloaded into
            temp_path = ExtendedPath.temporary_file_path(DOWNLOADED_FILES_DIR)

            def handle_response(response: Response):
                if "v2/seasons" in response.url:
                    # Get the first episode because season identifier is only found inside of the episodes
                    body = response.json()
                    season_id = ExtendedPath(response.url).stem
                    season_path = temp_path / "Season" / f"{season_id}.json"
                    # print(season_path)
                    season_path.write(json.dumps(body))
                elif "v2/shows" in response.url:
                    body = response.json()
                    (temp_path / "Show" / f"{self.show_id}.json").write(json.dumps(body))

            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    DOWNLOADED_FILES_DIR / "cookies/Chrome", headless=False, accept_downloads=True, channel="chrome"
                )
                page = browser.new_page()

                page.on("response", handle_response)
                page.goto(self.show_url(), wait_until="networkidle")

                # TODO: Autoamtically login to Funimation

                # Click the button to see all seasons
                page.click("div[class='v-select__slot']")

                # Count the number of seasons
                number_of_seasons = len(page.query_selector_all("div[class='v-list-item__title']"))
                # # If additional seasons exist get information for them
                if number_of_seasons > 1:
                    # Click on the first season to close the season selector (and get the first season in the process)
                    page.click("div[class='v-list-item__title']")
                    # .query_selector("xpath=..").find_element_by_xpath("..").click()
                    for i in range(number_of_seasons):
                        # Click to show list of seasons
                        page.click("div[class='v-select__slot']")

                        # Click the next season
                        page.click(f"div[class='v-list-item__title'] >> nth={i}")

                        # Don't hammer on the site too much at once
                        time.sleep(5)

                # Get rid of old information and insert new information
                self.clean_up_download(browser, p, number_of_seasons, temp_path)

    def update_show_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_season = self.parsed_files("Show", ".json")[0]
            self.show_info.name = parsed_season["name"]["en"]
            self.show_info.description = parsed_season["longSynopsis"]["en"]

            for image in parsed_season["images"]:
                if image["key"] == "Apple Square Cover":
                    self.show_info.thumbnail_url = image["path"]
                    self.show_info.image_url = image["path"]
            self.show_info.add_timestamps_and_save(self.directory)

    def update_season_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for sort_order, season in enumerate(self.parsed_files("Season", ".json")):
            season_id = season["id"]
            season_info = Season().get_or_new(season_id=season_id, show=self.show_info)[0]

            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season_info.number = season["number"]
                season_info.name = season["name"]["en"]
                season_info.sort_order = sort_order
                season_info.add_timestamps_and_save(self.directory)

    def update_episode_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for season in self.parsed_files("Season", ".json"):
            season_id = season["id"]
            season_info = Season.objects.get(season_id=season_id, show=self.show_info)

            for sort_id, episode in enumerate(season["episodes"]):
                episode_info = Episode().get_or_new(episode_id=episode["id"], season=season_info)[0]

                if not episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                    episode_info.sort_order = sort_id
                    episode_info.name = episode["name"]["en"]
                    episode_info.number = episode["episodeNumber"]
                    episode_info.description = episode["synopsis"]["en"]
                    episode_info.duration = episode["duration"]
                    # Some episodes do not have a release date so check if it exists first
                    #   See: https://www.funimation.com/shows/gal-dino/
                    # Some episodes have a release date that makes no sense and shows 29679264000000 as the timestamp
                    #   See: https://www.funimation.com/shows/steinsgate/
                    raw_date = episode["releaseDate"]
                    if raw_date and raw_date != 29679264000000:
                        # Timestamp is has 3 extra zeroes so divide by 100
                        episode_info.release_date = datetime.fromtimestamp(raw_date / 1000).astimezone()
                    else:
                        # Go through all audio track release datges and keep only the oldest one
                        for start_date in episode["videoOptions"]["audioLanguages"]["US"]["all"]:
                            date_string = start_date["start"].removesuffix(".000Z")
                            parsed_date = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S").astimezone()
                            if episode_info.release_date is None or parsed_date < episode_info.release_date:
                                episode_info.release_date = parsed_date

                    for image in episode["images"]:
                        if image["key"] == "Episode Thumbnail":
                            episode_info.image_url = image["path"]
                            # This thumbnail is kinda big at 720p, but it's the one used while browsing Funimation's actual site
                            episode_info.thumbnail_url = episode_info.image_url.replace(
                                "/upload/", "/upload/w_1280,q_60,c_fill/"
                            )

                    episode_info.add_timestamps_and_save(self.directory)
