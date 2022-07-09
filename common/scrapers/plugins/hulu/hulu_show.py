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
from common.scrapers.plugins.hulu.hulu_base import HuluBase
from common.scrapers.shared import ScraperShowShared

# Config
from config.config import HuluSecrets

# Apps
from shows.models import Episode, Season, Show


class HuluShow(ScraperShowShared, HuluBase):
    FAVICON_URL = "https://assetshuluimcom-a.akamaihd.net/h3o/icons/favicon.ico.png"
    SHOW_URL_REGEX = re.compile(
        r"^(?:https:\/\/www\.hulu\.com)?\/(?P<media_type>series|movie)\/(?P<show_slug>.*)-(?P<show_id>.*-.*-.*-.*-.*)$"
    )
    API_URL = "https://discover.hulu.com"

    # Override shared function to get media_type and slug
    def get_id_from_show_url(self, show_url: str) -> None:
        self.show_id = re.strict_search(self.SHOW_URL_REGEX, show_url).group("show_id")
        self.show_slug = re.strict_search(self.SHOW_URL_REGEX, show_url).group("show_slug")
        self.media_type = re.strict_search(self.SHOW_URL_REGEX, show_url).group("media_type")
        self.show_info = Show().get_or_new(show_id=self.show_id, website=self.WEBSITE)[0]

        # Stick the show_slug and media_type values here since they are required for generating URLs
        self.show_info.show_id_2 = self.show_slug
        self.show_info.media_type = self.media_type

    # Override shared function to get media_type and slug
    def get_id_from_show_oobject(self, show_identifier: Show) -> None:
        self.show_info = show_identifier
        self.show_id = show_identifier.show_id
        self.show_slug = show_identifier.show_id_2
        self.media_type = show_identifier.media_type

    # This is not the exact URL because the parameters are different which changes the result format
    @cache
    def show_json_url(self) -> str:
        return f"{self.API_URL}/content/v5/hubs/{self.media_type}/{self.show_id}?schema=1"

    @cache
    def season_json_url(self, season: str) -> str:
        return f"{self.API_URL}/content/v5/hubs/{self.media_type}/{self.show_id}/season/{season}?schema=1"

    @cache
    def show_url(self) -> str:
        return f"{self.DOMAIN}/series/{self.show_slug}-{self.show_id}"

    @cache
    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/watch/{episode.episode_id}/"

    @cache
    def path_from_url(self, url: str) -> ExtendedPath:
        url = url.removeprefix(self.DOMAIN)
        url = url.removeprefix("/")
        # JSON files are hosted behind this URL format
        if "content/v5/" in url:
            # Remove the different subdomain used by the JSON files
            # TODO: Move domain to constant
            url = url.removeprefix(self.API_URL)
            url = url.removeprefix("/")

            url = url.split("?")[0]
            url += "?schema=1"

            return (
                DOWNLOADED_FILES_DIR
                / self.WEBSITE
                / ExtendedPath(url.replace("?", "/")).legalize().with_suffix(".json")
            )
        else:
            return (
                DOWNLOADED_FILES_DIR
                / self.WEBSITE
                / ExtendedPath(url.replace("?", "/")).legalize().with_suffix(".html")
            )

    @cache
    def season_html_path(self, season: str) -> ExtendedPath:
        """There is no such thing as a URL for a season so just create a season specific path directly"""
        return self.path_from_url(self.show_url() + f"/{season}")

    def download_response(self, response: Response) -> None:
        if "/content/v5/hubs/" in response.url:
            parsed_json = response.json()
            # Save show files
            if self.show_json_url() in response.url:
                self.save_response_json(parsed_json)

                for component in parsed_json["components"]:
                    # Split the first season information from the show file
                    for item in component["items"]:
                        if item.get("items"):
                            self.save_response_json(item)
                        # Split extra from the season file
                    if component["name"] == "Extras":
                        self.save_response_json(component)

            # Save season files
            else:
                self.save_response_json(parsed_json)

    def save_response_json(self, parsed_json: Any) -> None:
        season_url = parsed_json["href"]
        season_path = self.path_from_url(season_url)
        season_path.write_json(parsed_json)

    def go_to_page_logged_in(self, page: Page, url: str) -> None:
        page.goto(url, wait_until="networkidle")
        if page.query_selector("span:has-text('Log In')"):
            page.goto("https://auth.hulu.com/web/login", wait_until="networkidle")

            # If there is the accept cookies button click it
            # This is requried to login to Hulu
            if page.click_if_exists("button >> text=Accept"):
                page.wait_for_load_state("networkidle")

            # Login
            page.type("input[data-automationid='email-field']", HuluSecrets.EMAIL)
            page.type("input[data-automationid='password-field']", HuluSecrets.PASSWORD)
            page.click("button[data-automationid='login-button']")

            # After logging in there is a redirect to choose the user
            # This may also appear after being logged on so choose the user in an if statement
            page.wait_for_url("{self.DOMAIN}/profiles?next=/", wait_until="networkidle")

        # User choice always appears when logging it, but it MIGHT appear on old sessions as well
        # TODO: Does it actually ever appear on old sessions
        if page.query_selector(f"a[aria-label='Switch profile to {HuluSecrets.NAME}']"):
            page.click(f"a[aria-label='Switch profile to {HuluSecrets.NAME}']")
            page.wait_for_load_state("networkidle")
            page.goto(url, wait_until="networkidle")

    def season_list(self) -> list[Any]:
        """ "Get a list of all season from the json file"""
        show_json_parsed = self.path_from_url(self.show_json_url()).parsed_json()
        for component in show_json_parsed["components"]:
            if component["name"] == "Episodes":
                return component["items"]

        # If no seasons are found return an empty list that is falsey
        return []

    def any_file_is_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        if self.any_show_file_is_outdated(minimum_timestamp):
            return True

        for season in self.season_list():
            if self.any_season_file_is_outdated(season, minimum_timestamp):
                return True
        return False

    def any_show_file_is_outdated(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        show_html_path = self.path_from_url(self.show_url())
        show_json_path = self.path_from_url(self.show_json_url())

        # Check if any show files are outdated first that way the information on them can be used
        return show_html_path.outdated(minimum_timestamp) or show_json_path.outdated(minimum_timestamp)

    def any_season_file_is_outdated(self, season: Any, minimum_timestamp: Optional[datetime] = None) -> bool:
        season_json_path = self.path_from_url(season["href"])
        return season_json_path.outdated(minimum_timestamp)

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        # Check if files exist before creating a playwright instance
        if self.any_file_is_outdated(minimum_timestamp):
            with sync_playwright() as playwright:
                page = self.playwright_browser(playwright).new_page()
                page.on("response", lambda request: self.download_response(request))
                self.download_show(page, minimum_timestamp)
                self.download_seasons(page, minimum_timestamp)
                page.close()

    def download_show(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        if self.any_show_file_is_outdated(minimum_timestamp):
            self.go_to_page_logged_in(page, self.show_url())
            # Re-open season selector for the next loop and to embed it into the html
            # Movies do not have a season selector so only click it if it exists
            page.click_if_exists("div[data-automationid='detailsdropdown-selectedvalue']")

            self.wait_for_files(page, self.path_from_url(self.show_json_url()))
            show_html_path = self.path_from_url(self.show_url())
            show_html_path.write(page.content())

            # Close season selector for a clean slate for season downloading
            page.click_if_exists("div[data-automationid='detailsdropdown-selectedvalue']")

    def download_seasons(self, page: Page, minimum_timestamp: Optional[datetime] = None) -> None:
        # Go through each season
        for season in self.season_list():

            # Is the season is up to date do nothing
            if not self.any_season_file_is_outdated(season, minimum_timestamp):
                continue

            # Only open the URL if it's not already open
            if page.url != self.show_url():
                self.go_to_page_logged_in(page, self.show_url())

            # Open season selector
            if page.click_if_exists("div[data-automationid='detailsdropdown-selectedvalue']"):
                season_name = season["name"]
                season_number = season["series_grouping_metadata"]["season_number"]
                season_html_path = self.season_html_path(season_number)
                season_json_path = self.path_from_url(self.season_json_url(season_number))

                if season_html_path.outdated(minimum_timestamp) or season_json_path.outdated(minimum_timestamp):
                    page.strict_query_selector(
                        f"ul[data-automationid='detailsdropdown-list'] >> li >> text={season_name}"
                    ).click()

                    self.wait_for_files(page, season_json_path)

                    season_html_path.write(page.content())

    def update_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show_json = self.path_from_url(self.show_json_url()).parsed_json()

            self.show_info.name = parsed_show_json["name"]
            self.show_info.description = parsed_show_json["details"]["entity"]["description"]

            base_img_url = parsed_show_json["artwork"]["program.tile"]["path"]
            # These image resolutions are used by Hulu and should already be generated
            # The images are the one returned in Google image searches
            self.show_info.image_url = base_img_url + "&size=1200x630&format=jpeg"
            self.show_info.thumbnail_url = base_img_url + "&size=600x338&format=jpeg"
            self.show_info.add_timestamps_and_save(self.path_from_url(self.show_url()))

    def update_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for i, season in enumerate(self.season_list()):
            season_id = season["series_grouping_metadata"]["season_number"]
            season_json_path = self.path_from_url(self.season_json_url(season_id))
            season_info = Season().get_or_new(season_id=season_id, show=self.show_info)[0]
            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season_info.name = season["name"]
                # This sometimes leads to wacky numbers for things like specials, but it works fine
                season_info.number = season_id
                season_info.sort_order = i
                # Hulu does not have season specific images so keep them blank

                season_info.add_timestamps_and_save(season_json_path)
        # Movies don't have any seasons so just copy information from the show
        if not self.season_list():
            season_info = Season().get_or_new(season_id=self.show_id, show=self.show_info)[0]
            season_info.name = "Movie"
            # This sometimes leads to wacky numbers for things like specials, but it works fine
            season_info.number = "0"
            season_info.sort_order = 0

            show_json_path = self.path_from_url(self.show_json_url())
            season_info.add_timestamps_and_save(show_json_path)

    def update_episodes(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for season in self.season_list():
            season_number = season["series_grouping_metadata"]["season_number"]
            season_json_path = self.path_from_url(self.season_json_url(season_number))
            parsed_season_json = season_json_path.parsed_json()
            season_id = parsed_season_json["id"].split("::")[1]
            season_info = Season().get_or_new(season_id=season_id, show=self.show_info)[0]
            parsed_season_json = season_json_path.parsed_json()

            for episode in parsed_season_json["items"]:
                episode_info = Episode().get_or_new(episode_id=episode["id"], season=season_info)[0]

                # If information is up to date nothing needs to be done
                if episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                    return

                self.add_shared_episode_info(episode_info, episode)

                episode_info.name = episode["name"]
                episode_info.number = episode["number"]
                # TODO: Is this good or should I use the index of the episode instead?
                episode_info.sort_order = episode["number"]

                episode_info.add_timestamps_and_save(season_json_path)
        # Movies only have 1 episodes so just copy information from the show
        if not self.season_list():
            season_info = Season().get_or_new(season_id=self.show_id, show=self.show_info)[0]
            episode_info = Episode().get_or_new(episode_id=0, season=season_info)[0]

            show_json_path = self.path_from_url(self.show_json_url())
            show_json_parsed = show_json_path.parsed_json()

            # If information is upt to date nothing needs to be done
            if episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                return

            self.add_shared_episode_info(episode_info, show_json_parsed["details"]["entity"])

            episode_info.name = "Movie"
            episode_info.sort_order = 0
            episode_info.number = "0"

            episode_info.add_timestamps_and_save(show_json_path)

    def add_shared_episode_info(self, episode_info: Episode, episode_json: dict[str, Any]) -> None:
        episode_info.description = episode_json["description"]

        base_img_url = episode_json["artwork"]["video.horizontal.hero"]["path"]
        # This is the only image resolution that Hulu automatically generates as far as I can tell
        # This URL format was found by inspecting the URLs that are loaded when loading the web page
        episode_info.image_url = base_img_url + '&operations=[{"resize":"600x600|max"},{"format":"webp"}]'
        episode_info.thumbnail_url = episode_info.image_url
        episode_info.release_date = datetime.strptime(episode_json["premiere_date"], "%Y-%m-%dT%H:%M:%SZ").astimezone()
        episode_info.duration = episode_json["duration"]
