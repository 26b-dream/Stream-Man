from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, Any

# Standard Library
from datetime import date, datetime, timedelta

# Common
import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_path import ExtendedPath
from common.extended_playwright import sync_playwright

# Apps
from shows.models import Show

# Local
from .crunchyroll_base import CrunchyrollBase
from .crunchyroll_show import CrunchyrollShow

# Plugins
from plugins.streaming.shared import ScraperUpdateShared


class CrunchyrollUpdate(CrunchyrollBase, ScraperUpdateShared):
    DOMAIN = "https://crunchyroll.com"
    BASE_CALENDAR_URL = DOMAIN + "/simulcastcalendar"
    OLD_EPISODE_URL_REGEX = re.compile(r"https:\/\/www\.crunchyroll\.com\/(?P<show_id>.*?)\/")
    JUSTWATCH_PROVIDER_IDS = [283]

    def path_from_url(self, url: str, suffix: str = ".html") -> ExtendedPath:
        url = url.removeprefix(self.DOMAIN)
        url = url.removeprefix("/")
        return DOWNLOADED_FILES_DIR / self.WEBSITE / ExtendedPath(url.replace("?", "/")).legalize().with_suffix(suffix)

    def check_for_updates(self, earliest_date: Optional[date] = None) -> None:
        last_show = Show.objects.filter(website=self.WEBSITE).order_by("info_timestamp").first()

        # If there are no shows for this website don't bother updating information
        if not last_show:
            return

        # If there is no date create one based on the oldest show for this website
        if not earliest_date:
            timestamp_as_date = last_show.info_timestamp.date()

            # Subtract the weekday value from timestamp_ad_date so all dates fall on a Monday
            earliest_date = timestamp_as_date - timedelta(days=timestamp_as_date.weekday())

        # Download calendar file if required
        if self.calendar_file_outdated(earliest_date):
            self.download_calendar_page(earliest_date)

        # Download calendars until the one for the current week is downloaded
        next_week = earliest_date + timedelta(days=7)
        if next_week < date.today():
            self.check_for_updates(next_week)

        # Import information from calendar
        self.import_calendar(earliest_date)

    def calendar_url(self, date: date) -> str:
        return self.BASE_CALENDAR_URL + "?date=" + date.strftime("%Y-%m-%d")

    # TODO: Maybe move some of this to an ExtendedPath function as it seems like it could be useful
    def calendar_file_outdated(self, date: date) -> bool:
        calendar_path = self.path_from_url(self.calendar_url(date))
        # If the file does not exist it must be out of date
        if not calendar_path.exists():
            return True

        # The file's minimum timestamp must be after the week ends to make sure it gets the entire schedule
        one_week_timestamp = datetime.combine(date + timedelta(days=7), datetime.min.time())
        file_timestamp = datetime.fromtimestamp(calendar_path.stat().st_mtime)

        # If the file was downloaded after the week was over the file is good
        if file_timestamp > one_week_timestamp:
            return False

        # If the file is older than 6 hours it's ok to update it
        if file_timestamp + timedelta(hours=6) < datetime.now():
            return True
        # If the file is newer than 6 hours do not bother updating it
        else:
            return False

    def download_calendar_page(self, date: date) -> None:
        print(f"Downloading: {self.calendar_url(date)}")
        with sync_playwright() as playwright:
            page = self.playwright_browser(playwright).new_page()
            # networkidle just hangs sometimes so try load
            page.goto(self.calendar_url(date), wait_until="load")

            # Download file
            # TODO: File verification
            self.path_from_url(self.calendar_url(date)).write(page.content())

            self.playwright_browser(playwright).close()

    def import_calendar(self, date: date) -> None:
        parsed_calendar = self.path_from_url(self.calendar_url(date)).parsed_html()
        for day in parsed_calendar.strict_select("div[class='day-content']"):
            # Don't use strict select here because the schedule may not be completely filled
            for episode in day.select("ol>li"):
                # For episode.select_one there are sometimes multiple time entries
                #   The first one is good
                #   The second one is an ETA until the episode airs
                release_date = datetime.strptime(
                    episode.strict_select("time")[0].strict_get("datetime"), "%Y-%m-%dT%H:%M:%S%z"
                )
                slug = episode.strict_select("article")[0].strict_get("data-slug")
                show = Show.objects.filter(show_id_2=slug, info_timestamp__lte=release_date).last()
                if show:
                    print(f"Found Outdated via calendar: {self.WEBSITE} - {show.name} - {release_date}")
                    show_instance = show.scraper_instance()
                    show_instance.set_update_at(release_date)

    def justwatch_update(self, justwatch_entry: dict[str, Any], date: datetime) -> None:
        justwatch_url = justwatch_entry["offers"][0]["urls"]["standard_web"]
        show_id = re.strict_search(self.OLD_EPISODE_URL_REGEX, justwatch_url).group("show_id")
        show = Show.objects.filter(website=self.WEBSITE, show_id_2=show_id)

        # If there is a show entry make sure the information is newer than the JustWatch entry
        if show:
            CrunchyrollShow(show[0]).import_all(minimum_info_timestamp=date)
