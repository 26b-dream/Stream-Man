from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Standard Library
from datetime import datetime

# Common
import common.configure_django  # type: ignore # noqa: F401 - Modified global values
import common.scrapers as scrapers

# Apps
from shows.models import Show

if __name__ == "__main__":
    for show in Show.objects.all():
        print(f"Reimporting: {show}")
        show_scraper = scrapers.Scraper(show)

        show_scraper.import_all(minimum_modified_timestamp=datetime.now().astimezone())
