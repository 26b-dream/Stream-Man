from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api._generated import Response
    from typing import Optional, Any

# Standard Library
from datetime import datetime
from functools import cache

# Third Party
from playwright.sync_api import sync_playwright
from playwright.sync_api._generated import Page

# Common
import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_path import ExtendedPath

# Config
from config.config import DiscoveryPlusSecrets

# Apps
from shows.models import Episode, Season

# Local
from .discoveryplus_base import DiscoveryplusBase

# Plugins
from plugins.streaming.shared import ScraperShowShared


class DiscoveryPlusShow(ScraperShowShared, DiscoveryplusBase):
    FAVICON_URL = "https://www.discoveryplus.com/favicon.png"
    API_URL = "https://us1-prod-direct.discoveryplus.com/"
    JUSTWATCH_PROVIDER_IDS = [520]
    SHOW_URL_REGEX = re.compile(r"^(?:https:\/\/www\.discoveryplus\.com)?\/show\/(?P<show_id>.*)")
    EPISODE_URL_REGEX = re.compile(r"^(?:https:\/\/www\.discoveryplus\.com)?\/video\/.*?\/(?P<episode_id>.*)")

    @cache
    def show_url(self) -> str:
        return f"{self.DOMAIN}/show/{self.show_id}"

    @cache
    # Canonical URL matches the html URL so just change the suffix
    def show_json_path(self) -> ExtendedPath:
        return self.path_from_url(self.show_url()).with_suffix(".json")

    @cache
    def season_json_path(self, season_id: str) -> ExtendedPath:
        show_hash = self.generic_show_episodes()["id"]  # I don't actually know waht this value represents
        show_id_2 = self.generic_show_episodes()["attributes"]["component"]["mandatoryParams"]
        url = f"{self.API_URL}/cms/collections/{show_hash}?include=default&decorators=viewingHistory,isFavorite,playbackAllowed&pf[seasonNumber]={season_id}&{show_id_2}"
        return self.path_from_url(url)

    @cache
    def season_html_path(self, season_id: str) -> ExtendedPath:
        directory = self.path_from_url(self.show_url()).with_suffix("")
        return (directory) / ExtendedPath(f"{season_id}.html").legalize()

    @cache
    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/video/{episode.season.show.show_id}/{episode.episode_id}/"

    @cache
    def any_file_is_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        if self.any_show_file_is_outdated(minimum_timestamp):
            return True

        for season in self.generic_show_episodes()["attributes"]["component"]["filters"][0]["options"]:
            if self.any_season_file_is_outdated(season["id"]):
                return True

        return False

    @cache
    def any_show_file_is_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        show_html_path = self.path_from_url(self.show_url())
        show_json_path = self.show_json_path()

        # Check if any show files are outdated first that way the information on them can be used
        return show_html_path.outdated(minimum_timestamp) or show_json_path.outdated(minimum_timestamp)

    @cache
    def any_season_file_is_outdated(self, season_id: str, minimum_timestamp: Optional[datetime] = None) -> bool:
        return self.season_json_path(season_id).outdated(minimum_timestamp) or self.season_html_path(
            season_id
        ).outdated((minimum_timestamp))

    def go_to_page_logged_in(self, page: Page, url: str) -> None:
        page.goto(url)

        # domcontentloaded and load do not wait long enough for some reason
        # network idle sometimes never happens due to the trailers being streamed prior to login
        # Wait for either the login button or the user selector to be visible
        page.wait_for_selector("a:has-text('Sign In'), div[id='navBar-user-menu']")

        if login_button := page.query_selector("a:has-text('Sign In')"):
            # Click sign in button
            login_button.click()

            # TODO: There is sometimes a captcha that needs to be solved
            page.type("input[id='email']", DiscoveryPlusSecrets.EMAIL)
            page.type("input[id='password']", DiscoveryPlusSecrets.PASSWORD)
            page.click("button[type='submit']")

            # After signing in a profile will always need to be selected
            # networkidle, domcontentloaded, and load do not work consistently
            # Wait for the profile selection div instead
            page.click(f"div:has-text('{DiscoveryPlusSecrets.NAME}')")

            # Wait for the correct page to completely load
            # Should be automatically redirected to the original page
            page.wait_for_load_state("networkidle")

    @cache
    def path_from_url(self, url: str) -> ExtendedPath:

        # JSON files are hosted behind this URL format
        if "cms/" in url:
            # Remove the different subdomain used by the JSON files
            url = url.removeprefix(self.API_URL)
            url = url.removeprefix("/")

            # The URL contains periods sometimes
            # Do not use .with_suffix because it will break the URL
            # .with_suffix("") will cause naming collisions
            legalized = ExtendedPath(url.replace("?", "/")).legalize()
            parent = legalized.parent
            name = legalized.name
            name = str(f"{name}.json")

            return DOWNLOADED_FILES_DIR / self.WEBSITE / parent / name
        else:
            url = url.removeprefix(self.DOMAIN)
            url = url.removeprefix("/")

            return (
                DOWNLOADED_FILES_DIR
                / self.WEBSITE
                / ExtendedPath(url.replace("?", "/")).legalize().with_suffix(".html")
            )

    @cache
    def generic_show_episodes(self) -> dict[str, Any]:
        show_json = self.show_json_path().parsed_json()
        for entry in show_json["included"]:
            if entry.get("attributes", {}).get("name", {}) == "generic-show-episodes":
                return entry

        raise ValueError("Could not find generic-show-episodes in {json}")

    @cache
    def generic_show_blueprint_page(self) -> dict[str, Any]:
        show_json = self.show_json_path().parsed_json()
        for entry in show_json["included"]:
            if entry.get("attributes", {}).get("name", {}) == "generic-show-blueprint-page":
                return entry
        raise ValueError("Could not find generic-show-blueprint-page in {json}")

    @cache
    def show_entry(self) -> dict[str, Any]:
        show_json = self.show_json_path().parsed_json()
        for entry in show_json["included"]:
            if entry.get("attributes", {}).get("alternateId", {}) == self.show_id:
                return entry

        raise ValueError(f"Could not find {self.show_id} in json")

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        # Check if files exist before creating a playwright instance
        # if self.any_file_is_outdated(minimum_timestamp):
        with sync_playwright() as playwright:
            browser = self.playwright_browser(playwright)
            page = browser.new_page()
            page.on("response", lambda request: self.download_response(request))
            self.download_show(page, minimum_timestamp)
            self.download_seasons(page, minimum_timestamp)

    def download_response(self, response: Response) -> None:
        if "/cms/" in response.url:
            parsed_json = response.json()
            # Show files have a consistent URL in the JSON body that can be used
            if show_url := parsed_json["data"]["attributes"].get("url"):
                season_path = self.path_from_url(show_url).with_suffix(".json")
                season_path.write_json(parsed_json)
            # Season files do not have a consistent URL so create a URL from the actual URL
            else:
                season_path = self.path_from_url(response.url)
                season_path.write_json(parsed_json)

    def download_show(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.any_show_file_is_outdated(minimum_timestamp):
            self.go_to_page_logged_in(page, self.show_url())

            # If there are multiple seasons open the season selector
            page.click_if_exists('div[data-testid="season-dropdown"]')

            self.wait_for_files(page, self.show_json_path())
            self.path_from_url(self.show_url()).write(page.content())

            # Close season selector so downloading seasons is more consistent
            page.click_if_exists('div[data-testid="season-dropdown"]')

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        for season in self.generic_show_episodes()["attributes"]["component"]["filters"][0]["options"]:
            season_number = season["id"]
            season_name = f"Season {season_number}"

            # if file is up to date nothing needs to be done
            if self.season_json_path(season_number).up_to_date(minimum_timestamp) and self.season_html_path(
                season_number
            ).up_to_date(minimum_timestamp):
                continue

            # Only go to page if required
            if not page.url.startswith(self.show_url()):
                self.go_to_page_logged_in(page, self.show_url())

            # Open season selector and click season if it exists
            if page.click_if_exists('div[data-testid="season-dropdown"]'):
                # Click the correct season
                page.click(f'div[data-testid="season-dropdown"] li >> text={season_name}')

            self.wait_for_files(page, self.season_json_path(season["id"]))
            self.season_html_path(season_number).write(page.content())

    def update_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        # Parse json outside of loop so it can be passed to update_seasons
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            self.show_info.name = self.show_entry()["attributes"]["name"]
            # Sometimes longDescription is not available so just use description instead
            self.show_info.description = (
                self.show_entry()["attributes"].get("longDescription") or self.show_entry()["attributes"]["description"]
            )
            self.show_info.image_url = self.show_image_url()
            self.show_info.thumbnail_url = self.show_info.image_url
            self.show_info.add_timestamps_and_save(self.show_json_path())

    def update_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for season in self.generic_show_episodes()["attributes"]["component"]["filters"][0]["options"]:
            season_info = Season().get_or_new(season_id=season["id"], show=self.show_info)[0]

            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                # Season number and sort order should match up unless proven otherwise
                season_info.sort_order = season_info.number = season["id"]
                # Values are always strings, so check if it's actually an integer as a string
                # If it's an integer as a string make a pretty season title like "Season 1"
                if re.match(r"^\d+$", season["value"]):
                    season_info.name = f'Season {season["value"]}'
                # Use exact strings for things that aren't integers as strings
                # This should only occur for movies when the season is listed as "Unknown"
                else:
                    season_info.name = season["value"]

                season_info.add_timestamps_and_save(self.season_json_path(season["id"]))

    def update_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for season in self.generic_show_episodes()["attributes"]["component"]["filters"][0]["options"]:
            season_info = Season().get_or_new(season_id=season["id"], show=self.show_info)[0]
            season_json_path = self.season_json_path(season["id"])
            season_json_parsed = season_json_path.parsed_json()
            print(season_json_path)

            for sort_id, episode in enumerate(season_json_parsed["included"]):
                # Ignore these entries because these are not for episodes
                if episode.get("attributes", {}).get("videoType") is None:
                    continue
                # For movies there is no season number so default to 0
                season_info = Season.objects.get(
                    show=self.show_info, season_id=episode["attributes"].get("seasonNumber", 0)
                )
                episode_info = Episode().get_or_new(
                    episode_id=episode["attributes"]["alternateId"], season=season_info
                )[0]

                if not episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                    episode_info.sort_order = sort_id
                    # Movies do not have an episode number so use episode_id as a unique identifier in case there is an edge case where a movie has multiple entries that I am not aware of
                    episode_info.number = episode["attributes"].get("episodeNumber", sort_id)
                    episode_info.name = episode["attributes"]["name"]
                    episode_info.description = episode["attributes"]["longDescription"]
                    # The first image listed under relationships is the main image for the episode
                    # This does not include any information for the image except the ID
                    image_id = episode["relationships"]["images"]["data"][0]["id"]
                    episode_info.image_url = self.episode_image_url(image_id, season_json_parsed)
                    episode_info.thumbnail_url = episode_info.image_url
                    episode_info.release_date = datetime.strptime(
                        episode["attributes"]["earliestPlayableStart"], "%Y-%m-%dT%H:%M:%S%z"
                    )
                    episode_info.number = episode["attributes"]["episodeNumber"]
                    # TODO: Is this good or should I use an enumerate
                    episode_info.sort_order = episode["attributes"]["episodeNumber"]
                    episode_info.duration = episode["attributes"]["videoDuration"] / 1000

                    episode_info.add_timestamps_and_save(self.season_json_path(season["id"]))

    def episode_image_url(self, image_id: str, season_json_parsed: dict[str, Any]) -> str:
        # Go through all the included images and find the image that matches
        for x in season_json_parsed["included"]:
            if x["id"] == image_id:
                return x["attributes"]["src"]
        raise ValueError("Unable to get episode_image_url")

    def show_image_url(self) -> str:
        for image_to_find in self.show_entry()["relationships"]["images"]["data"]:
            image_id = image_to_find["id"]

            # Go through every entry because some entries are iamges
            for x in self.show_json_path().parsed_json()["included"]:
                # If the entry is for the image and the image type is correct use that
                if x["id"] == image_id and x["attributes"]["kind"] == "poster_with_logo":
                    return x["attributes"]["src"]
        raise ValueError("Unable to get show_image_url from")
