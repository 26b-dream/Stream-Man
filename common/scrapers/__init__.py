from __future__ import annotations

#  __init__.py is used to avoid circular imports
# Circular imports naturally occur when trying to get a list of all subclasses
# A list of all subclasses is required to match up instances with the source website
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shows.models import Show

# Standard Library
import importlib

# Common
from common.extended_path import ExtendedPath
from common.scrapers.shared import (
    MissingShowClass,
    ScraperShowShared,
    ScraperUpdateShared,
)

# Import all plugins
plugins_dir = ExtendedPath(__file__).parent / "plugins"
for plugin in plugins_dir.glob("*"):
    module_name = f"common.scrapers.plugins.{plugin.stem}"
    module = importlib.import_module(module_name)

# Lists of subclasses are static so they can be constants
SHOW_SUBCLASSES: dict[str, type[ScraperShowShared]] = {}
for subclass in ScraperShowShared.__subclasses__():
    SHOW_SUBCLASSES[f"{subclass.WEBSITE}"] = subclass

UPDATE_SUBSCLASSES: dict[str, type[ScraperUpdateShared]] = {}
for subclass in ScraperUpdateShared.__subclasses__():
    UPDATE_SUBSCLASSES[f"{subclass.WEBSITE}"] = subclass


def __url_to_class(url: str) -> ScraperShowShared:
    for subclass in SHOW_SUBCLASSES.values():
        if hasattr(subclass, "DOMAIN"):
            if url.startswith(subclass.DOMAIN):
                return subclass(url)

    raise InvalidURL(f"Invalid url {url}")


def __show_to_class(show: Show) -> ScraperShowShared:
    try:
        return SHOW_SUBCLASSES[show.website](show)
    except KeyError:
        return MissingShowClass(show)


def Scraper(show_identifier: Show | str) -> ScraperShowShared:
    if isinstance(show_identifier, str):
        return __url_to_class(show_identifier)
    else:
        return __show_to_class(show_identifier)


class InvalidURL(Exception):
    pass
