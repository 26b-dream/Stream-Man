from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api._generated import Response, Page
    from typing import Optional, Any
    from playwright.sync_api._generated import Playwright

# Standard Library
from datetime import datetime

# Unknown
from functools import cache

# Common
import common.extended_re as re
from common.extended_path import ExtendedPath
from common.extended_playwright import sync_playwright
from common.scrapers.shared import ScraperShowShared

# Config
from config.config import CrunchyRollSecrets

# Apps
# Shows
from shows.models import Episode, Season

# Local
from .crunchyroll_base import CrunchyrollBase


class CrunchyrollShow(ScraperShowShared, CrunchyrollBase):
    OLD_DOMAIN = "https://crunchyroll.com"
    FAVICON_URL = OLD_DOMAIN + "/favicons/favicon-32x32.png"
    DOMAIN = "https://beta.crunchyroll.com"

    # Example show URLs
    #   https://beta.crunchyroll.com/series/G63VW2VWY
    #   https://beta.crunchyroll.com/series/G63VW2VWY/non-non-biyori
    SHOW_URL_REGEX = re.compile(r"^(?:https:\/\/beta\.crunchyroll\.com)?\/series\/*(?P<show_id>.*?)(?:\/|$)")

    def show_url(self) -> str:
        return f"{self.DOMAIN}/series/{self.show_id}"

    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/watch/{episode.episode_id}"

    # Login is required to access everything under the beta.crunchyroll.com domain
    def login(self, page: Page) -> None:
        page.goto("https://www.crunchyroll.com/login", wait_until="networkidle")
        page.type("input[id='login_form_name']", CrunchyRollSecrets.EMAIL)
        page.type("input[id='login_form_password']", CrunchyRollSecrets.PASSWORD)

        # For some reason clicking the sign in button doesn't work so just send an enter keypress instead
        page.keyboard.press("Enter")

        # After login, theu ser is redirected to the home page so wait for it to load
        page.wait_for_url("https://beta.crunchyroll.com/")

    def login_if_needed(self, page: Page, url: str) -> None:
        if page.url == "https://www.crunchyroll.com/":
            self.login(page)
            page.goto(self.show_url(), wait_until="networkidle")

    def go_to_page_logged_in(self, page: Page, url: str) -> None:
        page.goto(self.show_url(), wait_until="networkidle")
        self.login_if_needed(page, url)

    @cache  # Values only change when show_html file changes
    def show_html_season_names(self) -> list[str]:
        show_html = self.path_from_url(self.show_url()).parsed_html()
        seasons = show_html.select(
            "div[class='c-dropdown-content__scrollable'] div[role='button'] span[class='c-middle-truncation__text']"
        )

        if seasons:
            return [season.text for season in seasons]
        else:
            return [show_html.strict_select_one("h4.c-text--xl").text]

    # There is no seperate URL for seasons so make them a subdirectory of the show
    @cache  # Values should never change
    def season_html_path(self, season: str) -> ExtendedPath:
        return self.path_from_url(f"{self.show_url()}/{season}", ".html")

    # There is no simple way to connect the URL of the season with the Show
    # Instead just make a function that uses the name to connect the files
    @cache  # Values should never change
    def season_json_path(self, season: str) -> ExtendedPath:
        return self.path_from_url(f"{self.show_url()}/{season}", ".json")

    def download_show(self, playwright: Playwright, minimum_timestamp: Optional[datetime] = None) -> None:
        show_html_path = self.path_from_url(self.show_url())
        show_json_path = self.path_from_url(self.show_url(), ".json")

        if show_html_path.outdated(minimum_timestamp) or show_json_path.outdated(minimum_timestamp):
            page = self.playwright_browser(playwright).new_page()
            page.on("response", lambda request: self.download_show_response(request, show_json_path))
            self.go_to_page_logged_in(page, self.show_url())

            # Make sure the page is for the first season
            if page.click_if_exists("div[class='season-info']"):
                page.click("div[class='c-dropdown-content__scrollable'] div[role='button']")

            # Open season selector so it is saved in the html file if it exists
            page.click_if_exists("div[class='season-info']")

            # TODO: Verification
            show_html_path.write(page.content())
            page.close()
        self.download_seasons(playwright, minimum_timestamp)

    def download_show_response(self, response: Response, json_path: ExtendedPath) -> None:
        if f"series/{self.show_id}?" in response.url:
            # TODO: Verification
            json_path.write_json(response.json())

    def download_seasons(self, playwright: Playwright, minimum_timestamp: Optional[datetime] = None) -> None:
        page = None
        for season in self.show_html_season_names():
            season_html_path = self.season_html_path(season)
            season_json_path = self.season_json_path(season)

            if season_html_path.outdated(minimum_timestamp) or season_json_path.outdated(minimum_timestamp):
                # All season pages have to be downloaded from the show page so open the show page
                # Only do this the first time, al later pages can reuse existing page
                if not page:
                    page = self.playwright_browser(playwright).new_page()
                    page.on("response", lambda request: self.download_seasons_response(request, season_json_path))

                    self.go_to_page_logged_in(page, self.show_url())

                # Season selector only exists for shows with multiple seasons
                if page.click_if_exists("div[class='season-info']"):
                    # Loop throough all seasons until a matching one is found then click it
                    for page_thing in page.query_selector_all(
                        "div[class='c-dropdown-content__scrollable'] div[role='button'] span[class='c-middle-truncation__text']"
                    ):
                        if page_thing.text_content() == season:
                            page_thing.click()
                            # Waiting for networkidle sometimes has missing json files
                            # Trying documentloaded instead and seeing if it works any better
                            page.wait_for_load_state("domcontentloaded")
                            break

                # TODO: Verification
                season_html_path.write(page.content())
        # If the page was initilized close it
        if page:
            page.close()

    def download_seasons_response(self, response: Response, episode_json_path: ExtendedPath) -> None:
        if "episodes?" in response.url:
            # TODO: Verification
            episode_json_path.write_json(response.json())

    def update_all(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        self.update_show(minimum_info_timestamp, minimum_modified_timestamp)

    def update_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self.path_from_url(self.show_url(), ".json").parsed_json()

            self.show_info.name = parsed_show["title"]
            self.show_info.show_id_2 = parsed_show["slug_title"]
            self.show_info.description = parsed_show["description"]
            # poster_wide is an image with a 16x9 ratio (poster_tall is 6x9)
            # [0] is the first poster_wide design (as far as I can tell there is always just one)
            # [0][0] the first image listed is the lowest resolution
            # [0][1] the last image listed is the highest resolution
            self.show_info.thumbnail_url = parsed_show["images"]["poster_wide"][0][0]["source"]
            self.show_info.image_url = parsed_show["images"]["poster_wide"][0][-1]["source"]
            self.show_info.add_timestamps_and_save(self.path_from_url(self.show_url(), ".json"))
        self.update_season(minimum_info_timestamp, minimum_modified_timestamp)

    def update_season(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for i, season in enumerate(self.show_html_season_names()):
            parsed_season = self.season_json_path(season).parsed_json()

            # Season information is stored in each episode so just get information from the first episode
            parsed_episode = parsed_season["items"][0]

            season_id = parsed_episode["season_id"]
            season_info = Season().get_or_new(season_id=season_id, show=self.show_info)[0]

            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                # Sometimes season numbers are re-used (See: https://beta.crunchyroll.com/series/GRWEW95KR/laid-back-camp)
                # I prefer the different seasons with the same number to get mixed together instead of seperating them\
                season_info.number = parsed_episode["season_number"]
                # This format duplicates the format seen on Season.html pages
                season_info.name = parsed_episode["season_title"]
                season_info.sort_order = i
                season_info.add_timestamps_and_save(self.season_json_path(season))
            self.update_episode(season_info, parsed_season, minimum_info_timestamp, minimum_modified_timestamp)

    def update_episode(
        self,
        season_info: Season,
        episode_json_parsed: dict[str, Any],
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for i, episode in enumerate(episode_json_parsed["items"]):
            episode_info = Episode().get_or_new(episode_id=episode["id"], season=season_info)[0]

            if not episode_info.information_up_to_date(
                minimum_info_timestamp,
                minimum_modified_timestamp,
            ):
                episode_info.sort_order = i
                episode_info.name = episode["title"]
                episode_info.number = episode["episode"]
                episode_info.description = episode["description"]
                episode_info.duration = episode["duration_ms"] / 1000

                episode_info.release_date = datetime.strptime(episode["episode_air_date"], "%Y-%m-%dT%H:%M:%S%z")
                # [0] is the first thumbnail design (as far as I can tell there is always just one)
                # [0][0] the first image listed is the lowest resolution
                # [0][1] the last image listed is the highest resolution

                # Every now and then a show just won't have thumbnails
                # See: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri (May be updated later)
                if episode_images := episode.get("images"):
                    episode_info.thumbnail_url = episode_images["thumbnail"][0][0]["source"]
                    episode_info.image_url = episode_images["thumbnail"][0][-1]["source"]
                # No seperate file for episodes so just use the season file
                episode_info.add_timestamps_and_save(season_info.info_timestamp)
