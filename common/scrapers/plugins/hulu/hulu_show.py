from __future__ import annotations

from typing import TYPE_CHECKING, Literal

# Standard Library
from time import sleep

# Config
from config.config import HuluSecrets

if TYPE_CHECKING:
    from playwright.sync_api._generated import Response
    from playwright.sync_api._generated import Playwright
    from typing import Optional
    from common.extended_path import ExtendedPath

# Standard Library
from datetime import datetime
from functools import cache

# Third Party
from playwright.sync_api._generated import Page

# Common
import common.extended_re as re
from common.scrapers.plugins.hulu.hulu_base import HuluBase
from common.scrapers.shared import ScraperShowShared

# Apps
# Shows
from shows.models import Episode, Season

# Unknown


class HuluShow(ScraperShowShared, HuluBase):
    FAVICON_URL = "https://assetshuluimcom-a.akamaihd.net/h3o/icons/favicon.ico.png"
    SHOW_URL_REGEX = re.compile(r"^(?:https:\/\/www\.hulu\.com)?\/series\/(?P<show_id>.*)-.*-.*-.*-.*-.*$")

    @cache
    def show_url(self) -> str:
        return f"{self.DOMAIN}/series/{self.show_id}"

    @cache
    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/watch/{episode.episode_id}/"

    def login_if_needed(self, page: Page, url: str) -> None:
        # Login
        if page.query_selector("span:has-text('Log In')"):
            page.goto("https://auth.hulu.com/web/login", wait_until="networkidle")

            # If there is the accept cookies button click it
            # This is requried for clicking the button to login
            if page.click_if_exists("button >> text=Accept"):
                page.wait_for_load_state("networkidle")

            # Login
            page.type("input[data-automationid='email-field']", HuluSecrets.EMAIL)
            page.type("input[data-automationid='password-field']", HuluSecrets.PASSWORD)
            page.click("button[data-automationid='login-button']")

            # After logging in there is a redirect to choose the user
            page.wait_for_url("{self.DOMAIN}/profiles?next=/", wait_until="networkidle")
            page.click(f"a[aria-label='Switch profile to {HuluSecrets.NAME}']")

            # Final redirect after choosing the user
            page.wait_for_url("https://www.hulu.com/hub/home", wait_until="networkidle")
            page.goto(url, wait_until="networkidle")

        # Choose user
        if page.query_selector(f"a[aria-label='Switch profile to {HuluSecrets.NAME}']"):
            page.click(f"a[aria-label='Switch profile to {HuluSecrets.NAME}']")
            page.wait_for_load_state("networkidle")
            page.goto(url, wait_until="networkidle")

    def go_to_page_logged_in(self, page: Page, url: str) -> None:
        page.goto(url, wait_until="networkidle")
        self.login_if_needed(page, url)

    def season_path(self, season_name: str, extension: Literal[".html", ".json"]) -> ExtendedPath:
        return self.path_from_url(self.show_url() + f"/{season_name}", extension)

    def season_files_up_to_date(self, minimum_timestamp: Optional[datetime] = None) -> bool:
        show_json_path = self.path_from_url(self.show_url(), ".json")
        for season in show_json_path.parsed_json()["components"][0]["items"]:
            season_name = season["name"]
            season_json_path = self.season_path(season_name, ".json")
            season_html_path = self.season_path(season_name, ".html")

            if season_json_path.outdated(minimum_timestamp) or season_html_path.outdated(minimum_timestamp):
                return False
        return True

    def download_show(self, playwright: Playwright, minimum_timestamp: Optional[datetime] = None) -> None:

        show_html_path = self.path_from_url(self.show_url())
        show_json_path = self.path_from_url(self.show_url(), ".json")
        if show_html_path.outdated(minimum_timestamp) or show_json_path.outdated(minimum_timestamp):
            page = self.playwright_browser(playwright).new_page()
            page.on("response", lambda request: self.download_show_response(request, show_json_path))
            self.go_to_page_logged_in(page, self.show_url())
            show_html_path.write(page.content())
            page.close()

        self.download_seasons(playwright, minimum_timestamp)

    def download_show_response(self, response: Response, json_path: ExtendedPath) -> None:
        if "content/v5/hubs/series/" in response.url:
            # TODO: Verification
            json_path.write_json(response.json())

    def download_seasons(self, playwright: Playwright, minimum_timestamp: Optional[datetime] = None) -> None:
        # If all of the season files are up to date nothing needs to be done
        # Returning early here prevents from opening the webpage pointlessly
        if self.season_files_up_to_date(minimum_timestamp):
            return

        page = self.playwright_browser(playwright).new_page()
        page.on("response", lambda request: self.download_season_response(request))

        # Open Show page to get season information
        self.go_to_page_logged_in(page, self.show_url())

        # Open season selector
        if page.click_if_exists("div[data-automationid='detailsdropdown-selectedvalue']"):
            # Get all of the seasons for the show
            season_selection_list = page.query_selector_all("ul[data-automationid='detailsdropdown-list'] > li")
            number_of_seasons = len(season_selection_list)

            for season_number in range(number_of_seasons):
                season = season_selection_list[season_number]
                season_name = season.strict_text_content()
                season_json_path = self.season_path(season_name, ".json")
                season_html_path = self.season_path(season_name, ".html")

                if season_html_path.outdated(minimum_timestamp) or season_json_path.outdated(minimum_timestamp):
                    season.click()

                    # Response doesn't trigger consistently to download season json file
                    # Do a pointless query selector until the file exists to cause response to trigger
                    while not season_json_path.exists():
                        page.query_selector("html")
                        sleep(1)

                    season_html_path.write(page.content())

                    # Re-open season selector for the next loop
                    page.click("div[data-automationid='detailsdropdown-selectedvalue']")

                    # This value needs to be updated every time the div is re-opened otherwise the click will fail
                    season_selection_list = page.query_selector_all("ul[data-automationid='detailsdropdown-list'] > li")

    def download_season_response(self, response: Response) -> None:
        # All json files include this in the URL
        if "content/v5/hubs/series/" in response.url:
            # Check if this is a season specific URL
            if "season" in response.url:
                season_json_path = self.season_path(response.json()["name"], ".json")
                season_json_path.write_json(response.json())
            # Other URLs are for the show itself
            else:
                # The initial season information is stored with the show information so it must be extracted
                # All seasons are listed but only the initial season has an items entry
                for season in response.json()["components"][0]["items"]:
                    # If if has an items entry the initials season is found
                    if season["items"]:
                        season_json_path = self.season_path(season["name"], ".json")
                        season_json_path.write_json(season)
                        break

    def update_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        if not self.show_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
            parsed_show_json = self.path_from_url(self.show_url(), ".json").parsed_json()

            self.show_info.name = parsed_show_json["name"]
            self.show_info.description = parsed_show_json["details"]["entity"]["description"]

            base_img_url = parsed_show_json["artwork"]["detail.horizontal.hero"]["path"]
            # These image resolutions are used by Hulu and shoulod already be generated
            self.show_info.image_url = base_img_url + '&operations=[{"resize":"1920x1920|max"},{"format":"webp"}]'
            self.show_info.thumbnail_url = base_img_url + '&operations=[{"resize":"1024x1024|max"},{"format":"webp"}]'
            self.show_info.show_id_2 = parsed_show_json["id"]
            self.show_info.add_timestamps_and_save(self.path_from_url(self.show_url()))

        self.update_seasons(minimum_info_timestamp, minimum_modified_timestamp)

    def update_seasons(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        print(minimum_modified_timestamp)
        show_json_path = self.path_from_url(self.show_url(), ".json")
        for season in show_json_path.parsed_json()["components"][0]["items"]:
            season_name = season["name"]
            season_json_path = self.season_path(season_name, ".json")
            parsed_season_json = season_json_path.parsed_json()
            season_id = parsed_season_json["id"].split("::")[1]
            season_info = Season().get_or_new(season_id=season_id, show=self.show_info)[0]
            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season_info.name = parsed_season_json["name"]
                season_info.number = season_id
                season_info.sort_order = season_id

                # Shows do not have specific images so just keep it blank
                season_info.add_timestamps_and_save(season_json_path)

            self.update_episodes(season_info, season_json_path, minimum_info_timestamp, minimum_modified_timestamp)

    def update_episodes(
        self,
        season_info: Season,
        season_json_path: ExtendedPath,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        parsed_season_json = season_json_path.parsed_json()
        for episode in parsed_season_json["items"]:
            episode_id = episode["id"]
            episode_info = Episode().get_or_new(episode_id=episode_id, season=season_info)[0]

            # If information is upt to date nothing needs to be done
            if episode_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                return

            episode_info.name = episode["name"]
            episode_info.description = episode["description"]

            base_img_url = episode["artwork"]["video.horizontal.hero"]["path"]
            # The only image resolutions used by Hulu that is auto-generated is 600x600
            episode_info.thumbnail_url = base_img_url + '&operations=[{"resize":"600x600|max"},{"format":"webp"}]'
            episode_info.image_url = base_img_url + '&operations=[{"resize":"600x600|max"},{"format":"webp"}]'
            episode_info.release_date = datetime.strptime(episode["premiere_date"], "%Y-%m-%dT%H:%M:%SZ").astimezone()
            episode_info.number = episode["number"]
            episode_info.duration = episode["duration"]

            episode_info.add_timestamps_and_save(season_json_path)
