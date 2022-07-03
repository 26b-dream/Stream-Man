from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api._generated import Response, Page, ElementHandle
    from typing import Optional, Literal

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

# Config
from config.config import CrunchyrollSecrets

# Apps
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

    @cache
    def show_url(self) -> str:
        return f"{self.DOMAIN}/series/{self.show_id}"

    @cache
    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/watch/{episode.episode_id}"

    @cache
    def show_json_url(self) -> str:
        return f"{self.DOMAIN}/cms/v2/US/M2/crunchyroll/series/{self.show_id}"

    @cache
    def show_seasons_json_url(self) -> str:
        return f"{self.DOMAIN}/cms/v2/US/M2/crunchyroll/seasons?series_id={self.show_id}"

    @cache
    def season_json_url(self, season_id: str) -> str:
        return f"{self.DOMAIN}/cms/v2/US/M2/crunchyroll/episodes?season_id={season_id}"

    @cache
    def season_html_path(self, season: str) -> ExtendedPath:
        # There is no seperate URL for seasons so make them a subdirectory of the show
        return self.path_from_url(f"{self.show_url()}/{season}")

    @cache
    def path_from_url(self, url: str) -> ExtendedPath:
        url = url.removeprefix(self.DOMAIN)
        url = url.removeprefix("/")
        path_without_suffix = DOWNLOADED_FILES_DIR / self.WEBSITE / ExtendedPath(url.replace("?", "/")).legalize()

        # URLs with /cms/ in them are json files straight from the api
        if url.startswith("cms/"):
            return path_without_suffix.with_suffix(".json")
        # All other files are html files
        else:
            return path_without_suffix.with_suffix(".html")

    def go_to_page_logged_in(
        self,
        page: Page,
        url: str,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "networkidle",
    ) -> None:
        page.goto(self.show_url(), wait_until=wait_until)
        if page.url == "https://www.crunchyroll.com/":

            # Go to login URL and login
            page.goto("https://www.crunchyroll.com/login", wait_until="networkidle")
            page.type("input[id='login_form_name']", CrunchyrollSecrets.EMAIL)
            page.type("input[id='login_form_password']", CrunchyrollSecrets.PASSWORD)
            page.keyboard.press("Enter")

            # After login, the user is redirected to the home page so wait for it to load
            page.wait_for_url("https://beta.crunchyroll.com/")

            # Go to the actual page
            page.goto(self.show_url(), wait_until="networkidle")

    def any_file_is_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        # Check if any show files are outdated first that way the information on them can be used
        if self.any_show_file_outdated(minimum_timestamp):
            return True

        show_seasons_json_parsed = self.path_from_url(self.show_seasons_json_url()).parsed_json()
        for season in show_seasons_json_parsed["items"]:
            if self.any_season_file_is_outdated(season["id"], minimum_timestamp):
                return True

        return False

    @cache
    def any_show_file_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        # Check if any files are out of date before launching the browser
        show_html_path = self.path_from_url(self.show_url())
        show_json_path = self.path_from_url(self.show_json_url())
        show_seasons_json_path = self.path_from_url(self.show_seasons_json_url())

        # Check if any show files are outdated first that way the information on them can be used
        return (
            show_html_path.outdated(minimum_timestamp)
            or show_json_path.outdated(minimum_timestamp)
            or show_seasons_json_path.outdated(minimum_timestamp)
        )

    @cache
    def any_season_file_is_outdated(self, season_id: str, minimum_timestamp: Optional[datetime] = None) -> bool:
        season_html_path = self.season_html_path(season_id)
        season_json_path = self.path_from_url(self.season_json_url(season_id))

        # If the files are up to date nothing needs to be done
        return season_html_path.outdated(minimum_timestamp) or season_json_path.outdated(minimum_timestamp)

    def download_response(self, response: Response) -> None:
        if (
            "episodes?" in response.url
            or f"/seasons?series_id={self.show_id}" in response.url
            or f"series/{self.show_id}?" in response.url
        ):
            raw_json = response.json()
            season_json_path = self.path_from_url(raw_json["__href__"])
            season_json_path.write_json(raw_json)

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
            self.go_to_page_logged_in(page, self.show_url())

            # Make sure the page is for the first season
            # TODO: Is this actually required?
            if page.click_if_exists("div[class='season-info']"):
                page.click("div[class='c-dropdown-content__scrollable'] div[role='button']")

            # Open season selector so it is saved in the html file if it exists
            page.click_if_exists("div[class='season-info']")

            show_html_path = self.path_from_url(self.show_url())
            show_html_path.write(page.content())

            show_json_path = self.path_from_url(self.show_json_url())
            show_seasons_json_path = self.path_from_url(self.show_seasons_json_url())
            self.wait_for_files(page, show_json_path, show_seasons_json_path)

            # Close season selector to make season downloadnig more consistent
            page.click_if_exists("div[class='season-info']")

        self.download_seasons(page, minimum_timestamp)

    def find_matching_season(self, page: Page, season_name: str) -> ElementHandle:
        """Finding matches season can sometimes give problems so make this a seperate function for easier debugging"""
        # There are 2 selectors here
        # The first one is for season names that are not truncated
        # The second one is for season names that are truncated
        seasons = page.query_selector_all(
            "div[class='c-dropdown-content__scrollable'] div[role='button'] span[class='c-middle-truncation__text'],"
            + "div[class='c-dropdown-content__scrollable'] div[role='button'] span[class='c-middle-truncation__text c-middle-truncation__text--hidden']"
        )
        matching_seasons: list[ElementHandle] = []
        for season in seasons:
            if season.strict_text_content().endswith(season_name):
                matching_seasons.append(season)
        if len(matching_seasons) == 0:
            season_names = [x.strict_text_content() for x in seasons]
            raise ValueError(f"No matching seasons found for {season_name}\nOptions: {season_names}")
        elif len(matching_seasons) > 1:
            season_names = [x.strict_text_content() for x in matching_seasons]
            raise ValueError(f"Too many matching seasons found for {season_name}\nFound {season_names}")
        else:
            return matching_seasons[0]

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        show_seasons_json_parsed = self.path_from_url(self.show_seasons_json_url()).parsed_json()
        for season in show_seasons_json_parsed["items"]:
            # If all of the season files are up to date nothing needs to be done
            if self.any_season_file_is_outdated(season["id"], minimum_timestamp):
                # All season pages have to be downloaded from the show page so open the show page
                # Only do this one time, all later pages can reuse existing page
                if not self.show_url() in page.url:
                    self.go_to_page_logged_in(page, self.show_url())
                # Season selector only exists for shows with multiple seasons
                if page.click_if_exists("div[class='season-info']"):
                    matching_season = self.find_matching_season(page, season["title"])
                    matching_season.click()
                    # Waiting for networkidle/load/domcontentloaded sometimes has missing json files
                    # Just wait until the file exists as a work around
                    season_json_path = self.path_from_url(self.season_json_url(season["id"]))

                    self.wait_for_files(page, season_json_path)

                self.season_html_path(season["id"]).write(page.content())

    def update_all(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        self.update_show(minimum_info_timestamp, minimum_modified_timestamp)
        self.update_seasons(minimum_info_timestamp, minimum_modified_timestamp)
        self.update_episodes(minimum_info_timestamp, minimum_modified_timestamp)

    def update_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show = self.path_from_url(self.show_json_url()).parsed_json()

            self.show_info.name = parsed_show["title"]
            self.show_info.show_id_2 = parsed_show["slug_title"]
            self.show_info.description = parsed_show["description"]
            # poster_wide is an image with a 16x9 ratio (poster_tall is 6x9)
            # [0] is the first poster_wide design (as far as I can tell there is always just one)
            # [0][0] the first image listed is the lowest resolution
            # [0][1] the last image listed is the highest resolution
            self.show_info.thumbnail_url = parsed_show["images"]["poster_wide"][0][0]["source"]
            self.show_info.image_url = parsed_show["images"]["poster_wide"][0][-1]["source"]
            self.show_info.add_timestamps_and_save(self.path_from_url(self.show_url()))

    def update_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        show_seasons_json_path = self.path_from_url(self.show_seasons_json_url())
        show_seasons_json_parsed = show_seasons_json_path.parsed_json()
        for sort_order, season in enumerate(show_seasons_json_parsed["items"]):
            season_json_path = self.path_from_url(self.season_json_url(season["id"]))
            season_json_parsed = season_json_path.parsed_json()
            parsed_episode = season_json_parsed["items"][0]

            season_info = Season().get_or_new(season_id=season["id"], show=self.show_info)[0]

            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season_info.number = parsed_episode["season_number"]
                season_info.name = parsed_episode["season_title"]
                season_info.sort_order = sort_order
                season_info.add_timestamps_and_save(season_json_path)

    def update_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        show_seasons_json_path = self.path_from_url(self.show_seasons_json_url())
        show_seasons_json_parsed = show_seasons_json_path.parsed_json()
        for season in show_seasons_json_parsed["items"]:
            season_json_path = self.path_from_url(self.season_json_url(season["id"]))
            season_json_parsed = season_json_path.parsed_json()
            parsed_episode = season_json_parsed["items"][0]
            season_info = Season().get_or_new(season_id=season["id"], show=self.show_info)[0]

            for i, episode in enumerate(parsed_episode["items"]):
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
                    # Every now and then a show just won't have thumbnails
                    # See: https://beta.crunchyroll.com/series/G79H23VD4/im-kodama-kawashiri (May be updated later)
                    if episode_images := episode.get("images"):
                        # [0] is the first thumbnail design (as far as I can tell there is always just one)
                        # [0][0] the first image listed is the lowest resolution
                        # [0][1] the last image listed is the highest resolution
                        episode_info.thumbnail_url = episode_images["thumbnail"][0][0]["source"]
                        episode_info.image_url = episode_images["thumbnail"][0][-1]["source"]
                    # No seperate file for episodes so just use the season file
                    episode_info.add_timestamps_and_save(season_info.info_timestamp)
