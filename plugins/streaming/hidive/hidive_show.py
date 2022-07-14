from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Optional

# Standard Library
import json
from datetime import datetime
from functools import cache

# Third Party
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright.sync_api._generated import Page

# Common
import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_path import ExtendedPath

# Config
from config.config import HIDIVESecrets

# Apps
from shows.models import Episode, Season

# Local
from .hidive_base import HidiveBase

# Plugins
from plugins.streaming.shared import ScraperShowShared


class HidiveShow(ScraperShowShared, HidiveBase):
    FAVICON_URL = "https://www.hidive.com/favicon.ico"
    JUSTWATCH_PROVIDER_IDS = [430]

    # Two different URLs for movies and TV shows, but they use similiar structures
    # Example show URLs
    #   https://www.hidive.com/tv/teasing-master-takagi-san3
    #   https://www.hidive.com/movies/initial-d-legend-1-awakening
    SHOW_URL_REGEX = re.compile(r"^(?:https?:\/\/www\.hidive\.com)?\/(?:tv|movies)\/(?P<show_id>.*)")

    @cache
    def show_url(self) -> str:
        # This isn't the actual URL for movies, but it works
        return f"{self.DOMAIN}/tv/{self.show_id}"

    @cache
    def season_url(self, season_id: str) -> str:
        # This isn't the actual URL for movies, but it works
        return f"{self.DOMAIN}/tv/{season_id}"

    @cache
    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/stream/{episode.season.season_id}/{episode.episode_id}/"

    @cache
    def path_from_url(self, url: str, suffix: str = ".html") -> ExtendedPath:
        url = url.removeprefix(self.DOMAIN)
        url = url.removeprefix("/")
        return DOWNLOADED_FILES_DIR / self.WEBSITE / ExtendedPath(url.replace("?", "/")).legalize().with_suffix(suffix)

    def go_to_page_logged_in(self, page: Page, url: str) -> None:
        page.goto(url, wait_until="networkidle")
        if page.query_selector("a[href='/account/login']"):
            page.goto(f"{self.DOMAIN}/account/login", wait_until="networkidle")

            # If there is the accept cookies button click it
            # This is requried for clicking the button to login
            if page.click_if_exists("button >> text=Accept"):
                page.wait_for_load_state("networkidle")

            # Login
            page.type("input[id='Email']", HIDIVESecrets.EMAIL)
            page.type("input[id='Password']", HIDIVESecrets.PASSWORD)
            page.click("button[id='signInButton']")

            # When logging in user is redirected to the dashboard so wait for redirect to complete
            page.wait_for_url(f"{self.DOMAIN}/dashboard")
            page.goto(url, wait_until="networkidle")

    @cache
    def season_urls_from_show_html(self) -> list[str]:
        show_html_parsed = self.path_from_url(self.show_url()).parsed_html()
        if seasons := show_html_parsed.select("ul[class*='nav-tabs'] > li > a"):
            return [partial_url.strict_get("href") for partial_url in seasons]
        # Shows with only a single season don't have the season selector
        # For these shows just return the original show URL
        else:
            return [self.show_url()]

    @cache
    def episode_urls_from_season_html(self, season_path: ExtendedPath) -> list[str]:
        episodes_div = season_path.parsed_html().strict_select("div[class='slick-track']")[0]
        episodes = episodes_div.strict_select("div[class*='slick-slide'] a")
        return [partial_url.strict_get("data-playurl") for partial_url in episodes]

    @cache
    def json_from_html_file(self, path: ExtendedPath) -> dict[str, Any]:
        json_string = path.parsed_html().strict_select_one("script[type='application/ld+json']").text
        return json.loads(json_string)

    def show_is_valid(self, parsed_show: Page | BeautifulSoup) -> bool:
        # For simplicity convert PlayWright instances to BeautifulSoup instances
        # This makes it easier to verify pages before and after downloading
        # This is useful if verification requirements change
        if isinstance(parsed_show, Page):
            parsed_show = BeautifulSoup(parsed_show.content(), "html.parser")

        # Check if there are multipel seasons
        if season_selector := parsed_show.select_one("ul[class*='nav-tabs']"):
            first_season_url = season_selector.strict_select("a")[0].strict_get("href")
            partial_show_url = self.show_url().removeprefix(f"{self.DOMAIN}")

            # Check if this is the first season
            # This is done in case the URL for the second season was used instead of the first
            if first_season_url != partial_show_url:
                return False

        # All verifications passed assume file is good
        return True

    def any_file_is_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        # Check if any show files are outdated first that way the information on them can be used
        if self.path_from_url(self.show_url()).outdated(minimum_timestamp):
            return True

        for season_url in self.season_urls_from_show_html():
            if self.path_from_url(season_url).outdated(minimum_timestamp):
                return True
        return False

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.any_file_is_outdated(minimum_timestamp):
            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                self.download_show(page, minimum_timestamp)
                self.download_seasons(page, minimum_timestamp)
                # By default never update episodes because the information should be statitc
                self.download_episodes(page)
                page.close()

        if self.any_file_is_outdated(minimum_timestamp):
            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                self.download_show(page, minimum_timestamp)
                self.download_seasons(page, minimum_timestamp)
                self.download_episodes(page, minimum_timestamp)

    def download_show(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        show_html_path = self.path_from_url(self.show_url())
        if show_html_path.outdated(minimum_timestamp):
            self.go_to_page_logged_in(page, self.show_url())

            # Need to make sure this is the first season
            if not self.show_is_valid(page):
                raise Exception(f"Invalid page {self.show_url()}")

            show_html_path.write(page.content())

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        for partial_season_url in self.season_urls_from_show_html():
            season_html_path = self.path_from_url(partial_season_url)

            if season_html_path.outdated(minimum_timestamp):
                page.goto(self.DOMAIN + partial_season_url)
                season_html_path.write(page.content())

    # Download every episode because somwe information is only available on the episode pages
    #   For example, video duration is only showed on the episode page while logged in
    def download_episodes(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        for partial_season_url in self.season_urls_from_show_html():
            season_html_path = self.path_from_url(partial_season_url)

            for partial_episode_url in self.episode_urls_from_season_html(season_html_path):
                episode_html_path = self.path_from_url(partial_episode_url)
                if not episode_html_path.up_to_date(minimum_timestamp):
                    self.go_to_page_logged_in(page, self.DOMAIN + partial_episode_url)
                    episode_html_path.write(page.content())

    def update_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        parsed_show_html = self.path_from_url(self.show_url()).parsed_html()
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_json = self.json_from_html_file(self.path_from_url(self.show_url()))
            self.show_info.name = parsed_json["name"]
            self.show_info.description = parsed_show_html.strict_select("p[class='hidden-xs']")[0].text
            self.show_info.thumbnail_url = parsed_json["image"]
            # TODO: Is there a smaller image I can use?
            self.show_info.image_url = self.show_info.thumbnail_url
            self.show_info.add_timestamps_and_save(self.path_from_url(self.show_url()))

    def update_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for i, season_url in enumerate(self.season_urls_from_show_html()):
            # The Show & Season Regex are basically the same so re-using this even though names don't match
            season_id = re.strict_search(self.SHOW_URL_REGEX, season_url).group("show_id")
            season_info = Season().get_or_new(season_id=season_id, show=self.show_info)[0]

            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                parsed_season_json = self.json_from_html_file(self.path_from_url(season_url))
                season_info.name = parsed_season_json["name"]
                # TODO: Is there a value I can use for movies?
                season_info.number = parsed_season_json.get("partOfSeason", {}).get("seasonNumber", "Unknown")
                season_info.sort_order = i
                season_info.image_url = parsed_season_json["image"]
                season_info.thumbnail_url = season_info.image_url
                season_info.add_timestamps_and_save(self.path_from_url(season_url))

    def update_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        # Episode information must be imported after all seasons are imported
        # This is required because sometimes seasons include episodes from other seasons
        for season_url in self.season_urls_from_show_html():
            season_html_path = self.path_from_url(season_url)
            for i, episode_url in enumerate(self.episode_urls_from_season_html(season_html_path)):
                # Sometimes episodes are listed multiple times for different seasons
                # To compensate for this determine the season for each episode instead of assuming it is correct
                season_id = re.strict_search(self.EPISODE_URL_REGEX, episode_url).group("season_id")
                season_info = Season().get_or_new(season_id=season_id, show=self.show_info)[0]

                episode_id = re.strict_search(self.EPISODE_URL_REGEX, episode_url).group("episode_id")
                episode_info = Episode().get_or_new(episode_id=episode_id, season=season_info)[0]

                # If information is upt to date nothing needs to be done
                if episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                    return

                episode_json = self.json_from_html_file(self.path_from_url(episode_url))
                episode_html = self.path_from_url(episode_url).parsed_html()

                if episode_json["@type"] == "Movie":
                    # For movies jsut re-use the movie name for the episode
                    episode_info.name = episode_json["name"]
                else:
                    episode_info.name = episode_json["partOfTVSeries"]["name"]

                episode_info.name = episode_json.get("partOfTVSeries", episode_json)["name"]

                # This image seems consistent I guess
                img = episode_html.strict_select("div[class='default-img'] img")
                episode_info.thumbnail_url = img[i].strict_get("src")
                episode_info.image_url = episode_info.thumbnail_url.replace("256x144", "512x288")

                # HIDIVE lists episode airing dates in just this one location
                title_string = episode_html.strict_select("div[id='StreamTitleDescription']>h2")[0].text
                date_string = re.strict_search(r"Premiere: (\d{1,2}\/\d{1,2}\/\d{4})", title_string).group(1)
                episode_info.release_date = datetime.strptime(date_string, "%m/%d/%Y").astimezone()

                # Description is only on the html file
                episode_info.description = episode_html.strict_select_one("div[id='StreamTitleDescription'] p").text
                episode_info.number = episode_json.get("episodeNumber", "Unknown")

                # Duration is only available from the html file
                duration_string = episode_html.strict_select_one("div[class*='rmp-duration']").text
                split_values = duration_string.split(":")
                if len(split_values) == 3:
                    hours, minutes, seconds = split_values
                else:
                    hours = 0
                    minutes, seconds = split_values
                episode_info.duration = int(hours) * 60 * 60 + int(minutes) * 60 + int(seconds)

                episode_info.add_timestamps_and_save(self.path_from_url(episode_url))
