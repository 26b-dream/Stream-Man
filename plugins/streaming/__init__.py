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
from common.constants import BASE_DIR
from common.extended_path import ExtendedPath

# Plugins
from plugins.streaming.shared import (
    MissingShowClass,
    ScraperShowShared,
    ScraperUpdateShared,
)

# Import all plugins
plugins_dir = ExtendedPath(__file__).parent
for plugin in plugins_dir.glob("*"):
    # Plugins should be in a golder
    # Ignore __pycahce _- files
    if plugin.is_dir() and plugin.name != "__pycache__":
        relative_path = plugin.remove_parent(BASE_DIR.depth())
        dot_name = str(relative_path).replace("\\", ".")
        module_name = dot_name.removesuffix(".py")
        module = importlib.import_module(module_name)

SHOW_SUBCLASSES: dict[str, type[ScraperShowShared]] = {}
"""All real fully implemented subclasses"""
for subclass in ScraperShowShared.__subclasses__():
    if subclass.WEBSITE != MissingShowClass.WEBSITE:
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
        print(1111111111111111111111111)
        return MissingShowClass(show)


def Scraper(show_identifier: Show | str) -> ScraperShowShared:
    if isinstance(show_identifier, str):
        return __url_to_class(show_identifier)
    else:
        return __show_to_class(show_identifier)


class InvalidURL(Exception):
    pass
