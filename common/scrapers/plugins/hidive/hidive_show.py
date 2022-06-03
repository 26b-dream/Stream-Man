from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from playwright.sync_api._generated import Page, BrowserContext

# Standard Library
from datetime import datetime

# Common
import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_path import ExtendedPath
from common.extended_playwright import sync_playwright
from common.scrapers.plugins.hidive.hidive_base import HidIveBase
from common.scrapers.shared import ScraperShowShared

# Config
# Unknown
from config.config import HIDIVESecrets

# Apps
# Shows
from shows.models import Episode, Season


class HidIveShow(ScraperShowShared, HidIveBase):
    JUSTWATCH_PROVIDER_IDS = [430]

    # Two different URLs for movies and TV shows, but they use similiar structures
    # Example show URLs
    #   https://www.hidive.com/tv/teasing-master-takagi-san3
    #   https://www.hidive.com/movies/initial-d-legend-1-awakening
    SHOW_URL_REGEX = re.compile(r"^(?:https?:\/\/www\.hidive\.com)?\/(?:tv|movies)\/(?P<show_id>.*)")

    # Example episode URLs
    #   https://www.netflix.com/watch/80156389
    FAVICON_URL = "https://www.hidive.com/favicon.ico"

    def show_url(self) -> str:
        # This isn't the actual URL for movies, but it works
        return f"{self.DOMAIN}/tv/{self.show_id}"

    def season_url(self, season_id: str) -> str:
        # This isn't the actual URL for movies, but it works
        return f"{self.DOMAIN}/tv/{season_id}"

    def episode_url(self, episode: Episode) -> str:
        return f"{self.DOMAIN}/stream/{episode.season.season_id}/{episode.episode_id}/"

    def login(self, page: Page) -> None:
        # Once the browser cloeses HIDIVE completely logs you out
        # Being logged in is required to get the duration of an episode
        page.goto(f"{self.DOMAIN}/account/login", wait_until="networkidle")

        # If there is the accept cookies button click it
        # This is requried for clicking the button to login
        if page.click_if_exists("button >> text=Accept"):
            page.wait_for_load_state("networkidle")

        # Login
        page.type("input[id='Email']", HIDIVESecrets.EMAIL)
        page.type("input[id='Password']", HIDIVESecrets.PASSWORD)
        page.click("button[id='signInButton']")
        page.wait_for_url(f"{self.DOMAIN}/dashboard")

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        if not self.directory.up_to_date(minimum_timestamp):

            # Copnvert self.show_info.info_timestamp to unix timestamp
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    DOWNLOADED_FILES_DIR / "cookies/Chrome",
                    headless=False,
                    accept_downloads=True,
                    channel="chrome",
                )
                page = browser.new_page()

                page.goto(self.show_url(), wait_until="networkidle")

                # Login if required
                if page.query_selector("a[href='/account/login']"):
                    self.login(page)
                    page.goto(self.show_url(), wait_until="networkidle")

                # Get the number of seasons on the page
                # Shows that are just a single season don't have the buttons for season navigation
                # Number of seasons should be set to 1 when the season selector is not present
                season_buttons = page.query_selector_all("ul[class*='nav-tabs'] > li")
                number_of_seasons = len(season_buttons) or 1

                # Get information for each season if there are multiple seasons
                if number_of_seasons != 1:
                    for i in range(0, number_of_seasons):
                        # Click the next season
                        page.click(f"ul[class*='nav-tabs'] > li >> nth={i}")
                        page.wait_for_load_state("networkidle")

                        # Save all files for this season
                        self.save_files(browser, page, i)
                # If there is only 1 season import that one season
                else:
                    self.save_files(browser, page, 0)

                self.clean_up_download(browser, p, number_of_seasons * 2, self.temp_show_directory)

    def save_files(self, browser: BrowserContext, page: Page, season_number: int) -> None:
        # Pages for each episode need to be downloaded to get airing dates
        # Content on the episode pages should be static, so re-use old files
        if (self.directory / "Episode").exists() and not (self.temp_show_directory / "Episode").exists():
            (self.directory / "Episode").copy_dir(self.temp_show_directory / "Episode")

        # Save all season information
        json_file = page.strict_query_selector("script[type='application/ld+json']").strict_text_content()
        (self.temp_show_directory / "Season" / f"{season_number}.html").write(page.content())
        (self.temp_show_directory / "Season" / f"{season_number}.json").write(json_file)

        # Save the first season as the show page to make accessing data simpler
        if season_number == 0:
            (self.temp_show_directory / "Show" / "Show.html").write(page.content())
            (self.temp_show_directory / "Show" / "Show.json").write(json_file)

        # Download every episode because somwe information is only available on the episode pages
        episodes_div = page.strict_query_selector("div[class='slick-track'] >> nth=0")
        for episode_url in episodes_div.query_selector_all("div[class*='slick-slide'] a"):
            partial_url = episode_url.strict_get_attribute("data-playurl")
            path_name = ExtendedPath(partial_url).relative_to("/stream/").with_suffix(".json")
            episode_json_path = self.temp_show_directory / "Episode" / path_name
            episode_html_path = self.temp_show_directory / "Episode" / path_name

            if not episode_json_path.exists() or not episode_html_path.exists():
                # Open episode in new tab
                episode_page = browser.new_page()
                episode_page.goto(f"{self.DOMAIN}{partial_url}", wait_until="networkidle")

                # Save everything
                episode_json = episode_page.strict_query_selector(
                    "script[type='application/ld+json']"
                ).strict_text_content()
                episode_html_path.write(episode_page.content())
                episode_json_path.write(episode_json)
                episode_page.close()

    def update_show_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        parsed_show = self.parsed_files("Show", ".html")[0]
        self.show_info.name = (
            parsed_show.strict_select("title")[0]
            .text.removeprefix("Stream ")
            .removesuffix(" on HIDIVE")
            .removesuffix(" Season 1")
        )
        self.show_info.description = parsed_show.strict_select("p[class='hidden-xs']")[0].text
        self.show_info.thumbnail_url = parsed_show.strict_select("meta[property='og:image']")[0].text
        # TODO: Is there a smaller image I can use?
        self.show_info.image_url = self.show_info.thumbnail_url
        self.show_info.add_timestamps_and_save(self.directory)

    def update_season_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        for sort_id, season_json in enumerate(self.parsed_files("Season", ".json")):

            # The Show & Season Regex are basically the same so re-using this even though names don't match
            regexed_url = re.strict_search(self.SHOW_URL_REGEX, season_json["url"])
            season_id = regexed_url.group("show_id")
            season_info = Season().get_or_new(season_id=season_id, show=self.show_info)[0]

            if not season_info.information_up_to_date(minimum_info_timestamp, minimum_modified_timestamp):
                season_info.name = season_json["name"]
                # TODO: Is there a value I can use for movies?
                season_info.number = season_json.get("partOfSeason", {}).get("seasonNumber", "Unknown")
                season_info.sort_order = sort_id
                season_info.image_url = season_json["image"]
                season_info.thumbnail_url = season_info.image_url
                season_info.add_timestamps_and_save(self.directory)

    def update_episode_info(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        offset_index = 0
        prev_episode_json = {}
        for i, episode in enumerate(
            zip(
                self.parsed_files("Episode", ".json"),
                self.parsed_files("Episode", ".html"),
            )
        ):
            episode_json = episode[0]
            episode_html = episode[1]

            # The Show & Season Regex are basically the same so re-using this even though names don't match
            regexed_url = re.strict_search(self.EPISODE_URL_REGEX, episode_json["url"])
            season_id = regexed_url.group("season_id")
            season_info = Season().get_or_new(season_id=season_id, show=self.show_info)[0]

            html_url = episode_html.strict_select_one("meta[property='og:url']").strict_get("content")

            regexed_url = re.strict_search(self.EPISODE_URL_REGEX, html_url)
            episode_id = regexed_url.group("episode_id")

            episode_info = Episode().get_or_new(episode_id=episode_id, season=season_info)[0]

            if episode_json["@type"] == "Movie":
                # For movies jsut re-use the movie name for the episode
                episode_info.name = episode_json["name"]
            else:
                episode_info.name = episode_json["partOfTVSeries"]["name"]

            episode_info.name = episode_json.get("partOfTVSeries", episode_json)["name"]

            # When a new season or movie occurs the index for the image is reset
            prev_season = prev_episode_json.get("partOfSeason", {}).get("seasonNumber")
            current_season = episode_json.get("partOfSeason", {}).get("seasonNumber")
            if prev_season is None or prev_season != current_season:
                offset_index = i

            # This image seems consistent I guess
            img = episode[1].strict_select("div[class='default-img'] img")
            episode_info.thumbnail_url = img[i - offset_index].strict_get("src")
            episode_info.image_url = episode_info.thumbnail_url.replace("256x144", "512x288")

            # HiDive does not actually list dates for episodes there is just one single date for the entire season used on every episode
            # Can work around this by just assuming episodes air weekly and incremeneting the date by a week for every episode

            title_string = episode_html.strict_select("div[id='StreamTitleDescription']>h2")[0].text

            # Pull date from string in this format Premiere: 10/16/2004
            date_string = re.strict_search(r"Premiere: (\d{1,2}\/\d{1,2}\/\d{4})", title_string).group(1)
            episode_info.release_date = datetime.strptime(date_string, "%m/%d/%Y").astimezone()

            # Description is only on the html file
            episode_info.description = episode_html.strict_select_one("div[id='StreamTitleDescription'] p").text

            if episode_json.get("episodeNumber"):
                # This has to be converted to a float to an integer, I have no idea why
                episode_info.sort_order = int(float(episode_json["episodeNumber"]))
            # As far as I know, movies only have 1 episode ever but nothing listed in the json
            else:
                episode_info.sort_order = 0
            episode_info.number = str(episode_info.sort_order)

            # Duration is only available fon the html file
            duration_string = episode_html.strict_select_one("div[class*='rmp-duration']").text
            split_values = duration_string.split(":")
            if len(split_values) == 3:
                hours, minutes, seconds = split_values
            else:
                hours = 0
                minutes, seconds = split_values

            episode_info.duration = int(hours) * 60 * 60 + int(minutes) * 60 + int(seconds)
            episode_info.add_timestamps_and_save(self.directory)
            prev_episode_json = episode_json
