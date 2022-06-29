from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api._generated import Response, Page
    from typing import Optional, Any


# Standard Library
from datetime import datetime
from functools import cache

# Third Party
from playwright.sync_api import sync_playwright

# Common
import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_path import ExtendedPath
from common.scrapers.shared import ScraperShowShared

# Apps
from shows.models import Episode, Season

# Local
from .funimation_base import FunimationBase


class FunimationShow(FunimationBase, ScraperShowShared):
    API_DOMAIN = "https://d33et77evd9bgg.cloudfront.net"
    FAVICON_URL = "https://static.funimation.com/static/img/favicon.ico"
    DOMAIN = "https://www.funimation.com"

    # Example URL: https://www.funimation.com/shows/kaguya-sama-love-is-war/
    # Example URL: https://www.funimation.com/shows/kaguya-sama-love-is-war/
    SHOW_URL_REGEX = re.compile(r"https:\/\/www\.funimation\.com\/shows\/*(?P<show_id>.*?)(?:\/|$)")

    @cache
    def show_url(self) -> str:
        return f"{self.DOMAIN}/shows/{self.show_id}"

    @cache
    def show_json_url(self) -> str:
        return f"https://d33et77evd9bgg.cloudfront.net/data/v2/shows/{self.show_id}.json"

    @cache
    def season_json_url(self, season_id: str) -> str:
        return f"https://d33et77evd9bgg.cloudfront.net/data/v2/seasons/{season_id}.json"

    @cache
    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/v/{self.show_id}/{episode.episode_id}"

    @cache
    def season_html_path(self: FunimationShow, season: str) -> ExtendedPath:
        return self.path_from_url(f"{self.show_url()}/{season}")

    @cache
    def path_from_url(self: FunimationShow, url: str) -> ExtendedPath:
        url = url.removeprefix(self.DOMAIN)
        url = url.removeprefix(self.API_DOMAIN)
        url = url.removeprefix("/")
        path_without_suffix = DOWNLOADED_FILES_DIR / self.WEBSITE / ExtendedPath(url.replace("?", "/")).legalize()

        # URLs that end with .json are JSON files
        if url.endswith(".json"):
            return path_without_suffix.with_suffix(".json")
        # All other files are html files
        else:
            return path_without_suffix.with_suffix(".html")

    def any_file_is_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        # Check if any show files are outdated first that way the information on them can be used
        if self.any_show_file_outdated(minimum_timestamp):
            return True

        show_json_parsed = self.path_from_url(self.show_json_url()).parsed_json()
        for season in show_json_parsed["index"]["seasons"]:
            # Ignore seasons with no episodes
            if season["episodes"] == []:
                continue

            if self.any_season_file_is_outdated(season["contentId"], minimum_timestamp):
                return True

        return False

    @cache
    def any_show_file_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        # Check if any files are out of date before launching the browser
        show_html_path = self.path_from_url(self.show_url())
        show_json_path = self.path_from_url(self.show_json_url())

        # Check if any show files are outdated first that way the information on them can be used
        return show_html_path.outdated(minimum_timestamp) or show_json_path.outdated(minimum_timestamp)

    @cache
    def any_season_file_is_outdated(self, season_id: str, minimum_timestamp: Optional[datetime] = None) -> bool:
        season_html_path = self.season_html_path(season_id)
        season_json_path = self.path_from_url(self.season_json_url(season_id))

        # If the files are up to date nothing needs to be done
        return season_html_path.outdated(minimum_timestamp) or season_json_path.outdated(minimum_timestamp)

    def download_response(self, response: Response) -> None:
        if response.url.endswith(".json"):
            self.path_from_url(response.url).write_json(response.json())

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        # Check if files exist before creating a playwright instance
        if self.any_file_is_outdated(minimum_timestamp):
            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                page.on("response", lambda request: self.download_response(request))
                self.download_show(page, minimum_timestamp)
                page.close()

    def download_show(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.any_show_file_outdated(minimum_timestamp):
            page.goto(self.show_url(), wait_until="networkidle")

            # Click button to see episodes tab
            page.click("div[data-test='content-details-tabs__episodes']")

            # Click the button to see all seasons
            page.click("div[class='v-select__slot']")

            # Even if a show only has 1 season it still has the season selector
            number_of_seasons = len(page.query_selector_all("div[class='v-list-item__title']"))

            # If there is more than oen season make sure the page is for the first season
            # TODO: Is this actually required?
            if number_of_seasons > 1:

                # Click the button to go to the first season listed
                page.click("div[class='v-list-item__title']")
                page.wait_for_load_state("networkidle")

                # Open season selector so it is on the saved page
                page.click("div[class='v-select__slot']")

                show_json_url = self.path_from_url(self.show_json_url())
                self.wait_for_files(page, show_json_url)

            html_path = self.path_from_url(self.show_url())
            html_path.write(page.content())

            # Click this button to close the season selector
            page.click("div[data-test='content-details-tabs__episodes']")
        self.download_seasons(page, minimum_timestamp)

    def download_matching_season(self, page: Page, season_id: str, season_name: str) -> bool:
        page.wait_for_load_state("networkidle")

        # Extras titles doesn't exactly match
        if season_name == "Extras":
            season_name = "All Video Extras"

        # Click the button to see all seasons
        for season_choice in page.query_selector_all("div[class='v-list-item__title']"):
            # Find button for the season that matches the season I am looking for
            if season_choice.text_content() == season_name:
                season_choice.click()
                season_json_url = self.season_json_url(season_id)
                season_json_path = self.path_from_url(season_json_url)
                self.wait_for_files(page, season_json_path)
                html_path = self.season_html_path(season_id)
                html_path.write(page.content())

                return True
        return False

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        show_json_path = self.path_from_url(self.show_json_url())
        show_json_parsed = show_json_path.parsed_json()
        for season in show_json_parsed["index"]["seasons"]:
            # Ignore seasons with no episodes
            if season["episodes"] == []:
                continue

            season_id = season["contentId"]
            season_name = season["title"]["en"]

            if self.any_season_file_is_outdated(season_id, minimum_timestamp):
                # only open URL if it is requried
                if not page.url == self.show_url():
                    page.goto(self.show_url(), wait_until="networkidle")

                # Click tab to see main episodes
                page.click("div[data-test='content-details-tabs__episodes']")
                page.click("div[class='v-select__slot']")

                if self.download_matching_season(page, season_id, season_name):
                    continue

                # Click tab to see extras
                page.click("div[data-test='content-details-tabs__extras']")
                page.click("div[class='v-select__slot'] >> nth=1")

                if self.download_matching_season(page, season_id, season_name):
                    continue

                raise ValueError(f"Unable to find matching season for {season_id}, {season_name}")

    def update_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        # Parse json outside of loop so it can be passed to update_seasons
        show_json_path = self.path_from_url(self.show_json_url())
        parsed_show_json = show_json_path.parsed_json()
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            self.show_info.name = parsed_show_json["name"]["en"]
            self.show_info.description = parsed_show_json["longSynopsis"]["en"]

            for image in parsed_show_json["images"]:
                if image["key"] == "Apple Square Cover":
                    self.show_info.thumbnail_url = image["path"]
                    self.show_info.image_url = image["path"]

            self.show_info.add_timestamps_and_save(show_json_path)
        self.update_seasons(minimum_info_timestamp, minimum_modified_timestamp)

    def update_seasons(
        self,
        minimum_info_timestamp: Optional[datetime],
        minimum_modified_timestamp: Optional[datetime],
    ):
        show_json_path = self.path_from_url(self.show_json_url())
        parsed_show_json = show_json_path.parsed_json()
        for season in parsed_show_json["index"]["seasons"]:
            season_id = season["contentId"]

            # Ignore entries with no episodes
            if season["episodes"] == []:
                continue

            season_json_url = self.season_json_url(season_id)
            season_json_path = self.path_from_url(season_json_url)
            season_json_parsed = season_json_path.parsed_json()

            season_info = Season().get_or_new(season_id=season_json_parsed["id"], show=self.show_info)[0]
            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season_info.number = season_json_parsed["number"]
                season_info.name = season_json_parsed["name"]["en"]
                season_info.sort_order = season["order"]
                season_info.add_timestamps_and_save(season_json_path)

            self.update_episodes(season_info, season_json_parsed, minimum_info_timestamp, minimum_modified_timestamp)

    def update_episodes(
        self,
        season_info: Season,
        season_json_parsed: dict[str, Any],
        minimum_info_timestamp: Optional[datetime],
        minimum_modified_timestamp: Optional[datetime],
    ):
        # Import episodes
        for i, episode in enumerate(season_json_parsed["episodes"]):
            episode_info = Episode().get_or_new(episode_id=episode["id"], season=season_info)[0]
            if not episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                episode_info.sort_order = i
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
                        # This thumbnail is kinda big at 720p, but it's the size used on Funimation's actual site
                        episode_info.thumbnail_url = image["path"].replace("/upload/", "/upload/w_1280,q_60,c_fill/")

                # No seperate file for episodes so just use the season timestamp
                episode_info.add_timestamps_and_save(season_info.info_timestamp)
