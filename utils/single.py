from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Standard Library
from datetime import datetime

# Common
import common.configure_django  # type: ignore # noqa: F401 - Modified global values
import common.scrapers as scrapers

if __name__ == "__main__":
    current_time = datetime.now().astimezone()
    scraper_instance = scrapers.Scraper(input("Input URL: "))
    scraper_instance.import_all(minimum_modified_timestamp=current_time)
