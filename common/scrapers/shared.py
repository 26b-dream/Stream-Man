from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Literal, Pattern, Optional
    from playwright.sync_api._generated import BrowserContext, Playwright, Page
    from shows.models import Episode

from typing import overload

# Standard Library
import glob
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from functools import cache
from time import sleep

# Django
from django.db import transaction

# Common
import common.extended_re as re
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_bs4 import BeautifulSoup
from common.extended_path import ExtendedPath

# Apps
from shows.models import Show


class ScraperShared(ABC):
    directory: ExtendedPath
    WEBSITE: str
    DOMAIN: str

    @cache
    def files(self, type: str, extension: Literal[".html", ".json"]) -> list[ExtendedPath]:
        """Return a list of all of the files of a given type and extension"""
        output: list[ExtendedPath] = []
        for pathname in self.__actual_file_list():

            # Get the parent most directory that is a child of the show_directory
            # This directory should be the tytpe of file
            relative_dir = pathname.relative_to(self.directory)
            while len(relative_dir.parts) > 1:
                relative_dir = relative_dir.parent

            # Find files that are the matching type and file extension
            if str(relative_dir) == type and pathname.suffix == extension:
                output.append(pathname)

        # By default sort files by mtime
        # This just helps importing seasons in the correct order even if doing so is unnecessary
        return sorted(output, key=lambda x: x.stat().st_mtime)

    # Cache values so drive is only scanned once
    # This is a seperate function so the file list can be cached regardless of type and extension
    # This makes it so the directory only needs to be scanned once no matter what
    @cache
    def __actual_file_list(self) -> list[ExtendedPath]:
        return [ExtendedPath(x) for x in glob.iglob(str(self.directory / "**"), recursive=True)]

    @overload
    def parsed_files_tuple(self, type: str, extension: Literal[".json"]) -> list[tuple[ExtendedPath, dict[Any, Any]]]:
        ...

    @overload
    def parsed_files_tuple(self, type: str, extension: Literal[".html"]) -> list[tuple[ExtendedPath, BeautifulSoup]]:
        ...

    def parsed_files_tuple(self, type: str, extension: Literal[".html", ".json"]):
        """Return a list of tuples of the file path and parsed file\n
        Useful if the file name is needed at the same time as the parsed file"""
        return self.__parsed_files_tuple(type, extension)

    @cache
    def __parsed_files_tuple(self, type: str, extension: Literal[".html", ".json"]) -> Any:
        return tuple(zip(self.files(type, extension), self.parsed_files(type, extension)))

    @overload
    def parsed_files(self, type: str, extension: Literal[".json"]) -> list[dict[Any, Any]]:
        ...

    @overload
    def parsed_files(self, type: str, extension: Literal[".html"]) -> list[BeautifulSoup]:
        ...

    def parsed_files(self, type: str, extension: Literal[".html", ".json"]):
        return self.__parsed_files(type, extension)

    # Using @cache and @overload on the same method causes pylance to return the wrong type
    # To fix his cache a private method and then call that from the other method
    # See: https://github.com/microsoft/pyright/issues/2414
    # Return type here doesn't matter because overloads give the real return type
    @cache
    def __parsed_files(self, type: str, extension: Literal[".html", ".json"]) -> Any:
        output: list[dict[Any, Any] | BeautifulSoup] = []
        for pathname in self.files(type, extension):
            if extension == ".json":
                output.append(pathname.parsed_json())
            elif extension == ".html":
                output.append(pathname.parsed_html())
        return output

    @cache  # Values should never change
    def path_from_url(self, url: str, suffix: str = ".html") -> ExtendedPath:
        url = url.removeprefix(self.DOMAIN)
        url = url.removeprefix("/")
        return DOWNLOADED_FILES_DIR / self.WEBSITE / ExtendedPath(url.replace("?", "/")).legalize().with_suffix(suffix)


class ScraperUpdateShared(ScraperShared, ABC):
    JUSTWATCH_PROVIDER_IDS: list[int]

    @abstractmethod
    def check_for_updates(self, earliest_date: Optional[date] = None) -> None:
        ...

    @abstractmethod
    def justwatch_update(self, justwatch_entry: dict[str, Any], date: datetime) -> None:
        ...


class ScraperShowShared(ScraperShared, ABC):

    # Constants
    WEBSITE: str
    DOMAIN: str
    JUSTWATCH_PROVIDER_IDS: list[
        int
    ]  # This is a list because VRV pulls from CrunchyRoll, so to keep it up to date CrunchyRoll and VRV need to be updated
    SHOW_URL_REGEX: Pattern[str]
    FAVICON_URL: str

    def __init__(self, show_identifier: Show | str) -> None:
        # Construct information from str (URL)
        if isinstance(show_identifier, str):
            self.get_id_from_show_url(show_identifier)

        # Construct information from Show (database entry)
        else:
            self.show_info = show_identifier
            self.show_id = show_identifier.show_id

    def get_id_from_show_url(self, show_url: str) -> None:
        self.show_id = re.strict_search(self.SHOW_URL_REGEX, show_url).group("show_id")
        self.show_info = Show().get_or_new(show_id=self.show_id, website=self.WEBSITE)[0]

    @cache  # Re-use the same browser instance to download everything
    def playwright_browser(self, p: Playwright) -> BrowserContext:
        return p.chromium.launch_persistent_context(
            DOWNLOADED_FILES_DIR / "cookies/Chrome",
            headless=False,
            accept_downloads=True,
            channel="chrome",
        )

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

    @cache  # Values should never change
    @abstractmethod
    def episode_url(self, episode: Episode) -> str:
        ...

    @abstractmethod
    def download_all(self, minimum_timestamp: Optional[datetime] = None) -> None:
        ...

    @cache  # Values should never change
    @abstractmethod
    def show_url(self) -> str:
        ...

    def update_all(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        self.update_show(minimum_info_timestamp, minimum_modified_timestamp)

    @abstractmethod
    def update_show(
        self,
        minimum_info_timestamp: Optional[datetime] = None,
        minimum_modified_timestamp: Optional[datetime] = None,
    ) -> None:
        ...

    def wait_for_files(self, page: Page, *files: ExtendedPath) -> None:
        for file in files:
            while not file.exists():
                # Executing a query_selector will keep the download form randomly hanging while waiting for the file to exist
                page.query_selector("html")
                sleep(1)
