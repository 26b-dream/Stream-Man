from __future__ import annotations

from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from playwright.sync_api._generated import Response
    from playwright.sync_api._generated import Playwright
    from typing import Optional, Any


# Standard Library
from datetime import datetime

# StandardLibrary
from functools import cache

# Third Party
from playwright.sync_api import sync_playwright

# Common
from common.extended_path import ExtendedPath
from common.scrapers.shared import ScraperShowShared

# Apps
from shows.models import Episode, Season

# Local
from .funimation_base import FunimationBase


class FunimationShow(FunimationBase, ScraperShowShared):
    DOMAIN = "https://www.funimation.com"
    FAVICON_URL = "https://static.funimation.com/static/img/favicon.ico"

    @cache
    def show_url(self) -> str:
        return f"{self.DOMAIN}/shows/{self.show_id}"

    @cache
    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/v/{self.show_id}/{episode.episode_id}"

    @cache  # Values should never change
    def season_json_path(self, season: str) -> ExtendedPath:
        return self.path_from_url(f"{self.show_url()}/{season}", ".json")

    @cache  # Values should never change
    def season_html_path(self, season: str) -> ExtendedPath:
        return self.path_from_url(f"{self.show_url()}/{season}", ".html")

    def download_show_response(self, response: Response) -> None:
        if "v2/shows" in response.url:
            # There is no direct path to the json file form the html file
            # The path is virtually the same though with a different domain and prefixes
            # For simplicity merge these two and have the names match
            self.path_from_url(self.show_url(), ".json").write_json(response.json())

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        with sync_playwright() as playwright:
            self.download_show(playwright, minimum_timestamp)

    def download_show(self, playwright: Playwright, minimum_timestamp: Optional[datetime] = None) -> None:
        html_path = self.path_from_url(self.show_url())
        json_path = self.path_from_url(self.show_url(), ".json")

        if html_path.outdated(minimum_timestamp) or json_path.outdated(minimum_timestamp):
            page = self.playwright_browser(playwright).new_page()
            page.on("response", self.download_show_response)
            page.goto(self.show_url(), wait_until="networkidle")

            # Click the button to see all seasons
            page.click("div[class='v-select__slot']")

            # Even if a show only has 1 season it still has the season selector
            number_of_seasons = len(page.query_selector_all("div[class='v-list-item__title']"))

            # If there is more than oen season make sure the page is for thefirst season
            if number_of_seasons > 1:
                # Get the first season
                page.click("div[class='v-list-item__title']")
                page.wait_for_load_state("networkidle")

                # Open season selector so it is on the saved page
                page.click("div[class='v-select__slot']")

            html_path.write(page.content())
        self.download_seasons(playwright, minimum_timestamp)

    def download_season_response(self, response: Response, season_json_path: ExtendedPath) -> None:
        if "/v2/seasons/" in response.url:
            # json file includes the season anme which is the only way to cross reference the html file
            parsed_json = response.json()
            season_json_path.write_json(parsed_json)

    def download_seasons(self, playwright: Playwright, minimum_timestamp: Optional[datetime] = None) -> None:
        page = None
        parsed_show_json = self.path_from_url(self.show_url()).parsed_html()
        for season_div in parsed_show_json.strict_select("div[class='v-list-item__title']"):
            season = season_div.get_text()
            season_html_path = self.season_html_path(season)
            season_json_path = self.season_json_path(season)

            if season_html_path.outdated(minimum_timestamp) or season_json_path.outdated(minimum_timestamp):
                # All season pages have to be downloaded from the show page so open the show page
                # Only do this the first time, al later pages can reuse existing page
                if not page:
                    page = self.playwright_browser(playwright).new_page()
                    page.on("response", lambda request: self.download_season_response(request, season_json_path))

                    page.goto(self.show_url(), wait_until="networkidle")
                # Click the button to see all seasons
                page.click("div[class='v-select__slot']")

                # Go throgh every season
                for season_choice in page.query_selector_all("div[class='v-list-item__title']"):
                    # Find button that matches season I am looking for
                    if season_choice.text_content() == season:
                        season_choice.click()
                        # Waiting for networkidle sometimes has missing json files
                        # Trying documentloaded instead and seeing if it works any better
                        page.wait_for_load_state("networkidle")
                        break

                # TODO: Verification
                season_html_path.write(page.content())
        # If the page was initilized close it
        if page:
            page.close()

    def update_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        # Parse json outside of loop so it can be passed to update_seasons
        show_json_path = self.path_from_url(self.show_url(), ".json")
        parsed_show_json = show_json_path.parsed_json()
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):

            self.show_info.name = parsed_show_json["name"]["en"]
            self.show_info.description = parsed_show_json["longSynopsis"]["en"]

            for image in parsed_show_json["images"]:
                if image["key"] == "Apple Square Cover":
                    self.show_info.thumbnail_url = image["path"]
                    self.show_info.image_url = image["path"]

            self.show_info.add_timestamps_and_save(show_json_path)
        self.update_seasons(parsed_show_json, minimum_info_timestamp, minimum_modified_timestamp)

    def update_seasons(
        self,
        parsed_show_json: Dict[str, Any],
        minimum_info_timestamp: Optional[datetime],
        minimum_modified_timestamp: Optional[datetime],
    ):
        for i, season in enumerate(parsed_show_json["index"]["seasons"]):
            season_title = season["title"]["en"]

            # TODO: Do I actually need anythign in extras?
            # TODO: For now just ignore it
            if season_title == "Extras":
                continue
            season_json_path = self.season_json_path(season_title)
            season_json_parsed = season_json_path.parsed_json()

            season_info = Season().get_or_new(season_id=season_json_parsed["id"], show=self.show_info)[0]
            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season_info.number = season_json_parsed["number"]
                season_info.name = season_json_parsed["name"]["en"]
                season_info.sort_order = i
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
                        # This thumbnail is kinda big at 720p, but it's the one used while browsing Funimation's actual site
                        episode_info.thumbnail_url = episode_info.image_url.replace(
                            "/upload/", "/upload/w_1280,q_60,c_fill/"
                        )

                # No seperate file for episodes so just use the season timestamp
                episode_info.add_timestamps_and_save(season_info.info_timestamp)
