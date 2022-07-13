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

# Plugins
from plugins.show_scrapers.shared import (
    MissingShowClass,
    ScraperShowShared,
    ScraperUpdateShared,
)

# Import all plugins
plugins_dir = ExtendedPath(__file__).parent
for plugin in plugins_dir.glob("*"):
    module_name = f"plugins.show_scrapers.{plugin.stem}"
    module = importlib.import_module(module_name)

SUBCLASSES: dict[str, type[ScraperShowShared]] = {}
"""All real fully implemented subclasses"""
for subclass in ScraperShowShared.__subclasses__():
    if subclass.WEBSITE != MissingShowClass.WEBSITE:
        SUBCLASSES[f"{subclass.WEBSITE}"] = subclass

UPDATE_SUBSCLASSES: dict[str, type[ScraperUpdateShared]] = {}
for subclass in ScraperUpdateShared.__subclasses__():
    UPDATE_SUBSCLASSES[f"{subclass.WEBSITE}"] = subclass


def __url_to_class(url: str) -> ScraperShowShared:
    for subclass in SUBCLASSES.values():
        if hasattr(subclass, "DOMAIN"):
            if url.startswith(subclass.DOMAIN):
                return subclass(url)

    raise InvalidURL(f"Invalid url {url}")


def __show_to_class(show: Show) -> ScraperShowShared:
    try:
        return SUBCLASSES[show.website](show)
    except KeyError:
        print(1111111111111111111111111)
        return MissingShowClass(show)


def Scraper(show_identifier: Show | str) -> ScraperShowShared:
    if isinstance(show_identifier, str):
        return __url_to_class(show_identifier)
    else:
        return __show_to_class(show_identifier)


class InvalidURL(Exception):
    pass
