from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from playwright.sync_api._generated import Response, Page

# Standard Library
from datetime import datetime

# Common
import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_playwright import sync_playwright
from common.scrapers.shared import ScraperShowShared

# Config
# Unknown
from config.config import CrunchyRollSecrets

# Apps
# Shows
from shows.models import Episode, Season

# Local
from .crunchyroll_base import CrunchyrollBase


class CrunchyrollShow(ScraperShowShared, CrunchyrollBase):
    FAVICON_URL = CrunchyrollBase.OLD_DOMAIN + "/favicons/favicon-32x32.png"
    DOMAIN = "https://beta.crunchyroll.com"

    # Example show URLs
    #   https://beta.crunchyroll.com/series/G63VW2VWY
    #   https://beta.crunchyroll.com/series/G63VW2VWY/non-non-biyori
    SHOW_URL_REGEX = re.compile(r"https:\/\/beta\.crunchyroll\.com\/series\/*(?P<show_id>.*?)(?:\/|$)")

    def show_url(self) -> str:
        return f"{self.DOMAIN}/series/{self.show_id}"

    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/watch/{episode.episode_id}"

    def login(self, page: Page) -> None:
        page.goto("https://www.crunchyroll.com/login", wait_until="networkidle")
        page.type("input[id='login_form_name']", CrunchyRollSecrets.EMAIL)
        page.type("input[id='login_form_password']", CrunchyRollSecrets.PASSWORD)

        # For some reason clicking the sign in button doesn't work so just send an enter keypress instead
        page.keyboard.press("Enter")
        page.wait_for_url("https://beta.crunchyroll.com/")

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        # If files are up to date nothing needs to be done
        if self.directory.up_to_date(minimum_timestamp):
            return

        # Watch for json files and download them
        def handle_response(response: Response):
            if "episodes?" in response.url:
                body = response.json()
                season_id = body["items"][0]["season_id"]
                (self.temp_show_directory / "Season" / f"{season_id}.json").write_json(body)
            elif f"series/{self.show_id}?" in response.url:
                body = response.json()
                (self.temp_show_directory / "Show" / f"{self.show_id}.json").write_json(body)

        with sync_playwright() as playwright:
            # Start PlayWright
            browser = playwright.chromium.launch_persistent_context(
                DOWNLOADED_FILES_DIR / "cookies/Chrome", headless=False, accept_downloads=True, channel="chrome"
            )
            page = browser.new_page()
            page.on("response", handle_response)

            # First attempt to reach desirted page
            page.goto(self.show_url(), wait_until="load")

            # If redirected to the homepage log in
            # When not logged in will be redirected to the homepage
            # TODO: Why does networkidle not work when redirected?
            if page.url == "https://www.crunchyroll.com/":
                self.login(page)
                page.goto(self.show_url(), wait_until="networkidle")

            # If there is a season selector there are multiple seasons for the show
            number_of_seasons = 1
            if page.click_if_exists("div[class='season-info']"):
                # Get the number of seasons
                number_of_seasons = len(
                    page.query_selector_all("div[class='c-dropdown-content__scrollable'] div[role='button']")
                )

                # Click to go to the first season
                page.click("div[class='c-dropdown-content__scrollable'] div[role='button']")

                # Click through seasons
                page.click_while_exists("div[data-t='next-season'][class='cta-wrapper']")

                # This is repeated on purpose, sometimes JSON files aren't caught for the first season so this will double check for it
                page.click("div[class='season-info']")
                page.click("div[class='c-dropdown-content__scrollable'] div[role='button']")

            self.clean_up_download(browser, playwright, number_of_seasons, self.temp_show_directory)

    def update_show_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_season = self.parsed_files("Show", ".json")[0]
            self.show_info.name = parsed_season["title"]
            self.show_info.show_id_2 = parsed_season["slug_title"]
            self.show_info.description = parsed_season["description"]
            # poster_wide is an image with a 16x9 ratio (poster_tall is 6x9)
            # [0] is the first poster_wide design (as far as I can tell there is always just one)
            # [0][0] the first image listed is the lowest resolution
            # [0][1] the last image listed is the highest resolution
            self.show_info.thumbnail_url = parsed_season["images"]["poster_wide"][0][0]["source"]
            self.show_info.image_url = parsed_season["images"]["poster_wide"][0][-1]["source"]
            self.show_info.add_timestamps_and_save(self.directory)

    def update_season_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for sort_order, season in enumerate(self.parsed_files("Season", ".json")):
            # Season itself is never listed directly (checked Show.json, Season.json & Season.html for the information)
            # Luckily all episodes on Season.json includes season information so get the season information from the first episode
            episode = season["items"][0]
            season_id = episode["season_id"]
            season_info = Season().get_or_new(season_id=season_id, show=self.show_info)[0]

            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                # Sometimes season numbers are re-used (See: https://beta.crunchyroll.com/series/GRWEW95KR/laid-back-camp)
                # I prefer the different seasons with the same number to get mixed together instead of seperating them\
                season_info.number = episode["season_number"]
                # This format duplicates the format seen on Season.html pages
                season_info.name = episode["season_title"]
                season_info.sort_order = sort_order
                season_info.add_timestamps_and_save(self.directory)

    def update_episode_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for season in self.parsed_files("Season", ".json"):
            # Season itself is never listed directly (checked Show.json, Season.json & Season.html for the information)
            # Luckily all episodes on Season.json includes season information so get the season information from the first episode
            season_id = season["items"][0]["season_id"]
            season_info = Season.objects.get(season_id=season_id, show=self.show_info)

            for sort_id, episode in enumerate(season["items"]):
                episode_info = Episode().get_or_new(episode_id=episode["id"], season=season_info)[0]

                if not episode_info.information_up_to_date(
                    minimum_info_timestamp,
                    minimum_modified_timestamp,
                ):
                    episode_info.sort_order = sort_id
                    episode_info.name = episode["title"]
                    episode_info.number = episode["episode"]
                    episode_info.description = episode["description"]
                    episode_info.duration = episode["duration_ms"] / 1000

                    episode_info.release_date = datetime.strptime(episode["episode_air_date"], "%Y-%m-%dT%H:%M:%S%z")
                    # [0] is the first thumbnail design (as far as I can tell there is always just one)
                    # [0][0] the first image listed is the lowest resolution
                    # [0][1] the last image listed is the highest resolution
                    episode_info.thumbnail_url = episode["images"]["thumbnail"][0][0]["source"]
                    episode_info.image_url = episode["images"]["thumbnail"][0][-1]["source"]
                    episode_info.add_timestamps_and_save(self.directory)
