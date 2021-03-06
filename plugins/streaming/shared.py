from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Pattern, Optional
    from playwright.sync_api._generated import BrowserContext, Playwright, Page
    from shows.models import Episode


# Standard Library
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from functools import cache
from time import sleep

# Django
from django.db import transaction

# Common
import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_path import ExtendedPath

# Apps
from shows.models import Show


class ScraperShared(ABC):
    directory: ExtendedPath
    WEBSITE: str
    DOMAIN: str

    def playwright_browser(self, playwright: Playwright) -> BrowserContext:
        # Browser seem to suck when headless=False
        #   Firefox will just show a white screen if using cookies that already exist
        #   Chrome constantly crashes when closing the web browser
        # Chrome constantly has crashes when not running in headless mode
        # Firefox seems to be more stable
        return playwright.chromium.launch_persistent_context(
            user_data_dir=DOWNLOADED_FILES_DIR / "cookies/chrome",
            headless=False,
            channel="chrome",
            slow_mo=100,
        )


class ScraperUpdateShared(ScraperShared, ABC):
    JUSTWATCH_PROVIDER_IDS: list[int]

    @abstractmethod
    def check_for_updates(self, earliest_date: Optional[date] = None) -> None:
        ...

    @abstractmethod
    def justwatch_update(self, justwatch_entry: dict[str, Any], date: datetime) -> None:
        ...


class ScraperShowShared(ScraperShared, ABC):
    WEBSITE: str
    DOMAIN: str
    JUSTWATCH_PROVIDER_IDS: list[int]  # This is a list because some websites pull fronm multiple websites
    SHOW_URL_REGEX: Pattern[str]
    FAVICON_URL: str

    def __init__(self, show_identifier: Show | str) -> None:
        # Construct information from str (URL)
        if isinstance(show_identifier, str):
            self.get_id_from_show_url(show_identifier)

        # Construct information from Show (database entry)
        else:
            self.get_id_from_show_oobject(show_identifier)

    def get_id_from_show_url(self, show_url: str) -> None:
        temp = re.strict_search(self.SHOW_URL_REGEX, show_url).group("show_id")
        if isinstance(temp, str):
            self.show_id = str(temp)
        else:  # TODO: This is actually impossible but this is here for pylance
            raise ValueError("No show ID found")

        self.show_info = Show().get_or_new(show_id=self.show_id, website=self.WEBSITE)[0]

    def get_id_from_show_oobject(self, show_identifier: Show) -> None:
        self.show_info = show_identifier

        self.show_id = show_identifier.show_id

    @transaction.atomic
    def import_all(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        self.download_all(minimum_timestamp=minimum_info_timestamp)
        self.update_all(minimum_info_timestamp, minimum_modified_timestamp)
        self.set_weekly_update()

    def set_weekly_update(self) -> None:
        """Set a show to automatically update one week after the last episode aired\n
        This generic function can do a decent job of replacing website specific updating functions"""
        # Because some websites like CrunchyRol have dubs and subs listed as seperate seasons extra work must be done
        # It must be determined what is the closest date that a new episode is predicted to air at
        for episode in self.show_info.latest_episode_dates():
            update_at = episode.release_date + timedelta(days=7)
            # If the update_at time is newer than the info_timestamp and less than the pervious update_at value set it
            if not self.set_update_at(update_at):
                break

    def update_at_is_outdated(self, update_at: datetime) -> bool:
        # If there isn't an update_at value set it
        if self.show_info.update_at is None:
            return True

        # If the old update_at value is outdated update it
        if self.show_info.update_at < self.show_info.info_timestamp:
            return True

        # If the new update_at value is newer update the old one
        if update_at > self.show_info.update_at:
            return True

        return False

    def set_update_at(self, update_at: datetime) -> bool:
        # If the old update_at value is outdated update it
        if return_value := self.update_at_is_outdated(update_at):
            self.show_info.update_at = update_at
            self.show_info.save()
        return return_value

    def update_all(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        # Ignore the types here because these will be implemebted in the subclasses if they are used
        self.update_show(minimum_info_timestamp, minimum_modified_timestamp)  # type: ignore
        self.update_seasons(minimum_info_timestamp, minimum_modified_timestamp)  # type: ignore
        self.update_episodes(minimum_info_timestamp, minimum_modified_timestamp)  # type: ignore

    def wait_for_files(self, page: Page, *files: ExtendedPath) -> None:
        for file in files:
            while not file.exists():
                # Executing a query_selector will keep the download form randomly hanging while waiting for the file to exist
                page.query_selector("html")
                sleep(1)

    @abstractmethod
    @cache
    def episode_url(self, episode: Episode) -> str:
        return "Missing Episode URL"

    @abstractmethod
    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        pass

    @abstractmethod
    @cache
    def show_url(self) -> str:
        return "Missing Show URL"


class MissingShowClass(ScraperShowShared):
    WEBSITE = "WEBSITE NAME"

    def __init__(self, show_identifier: Show | str) -> None:
        pass

    def import_all(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        pass

    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        pass

    @cache
    def episode_url(self, episode: Episode) -> str:
        return "Missing Episode URL"

    @cache
    def show_url(self) -> str:
        return "Missing Show URL"
