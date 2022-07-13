from __future__ import annotations

# Standard Library
from datetime import datetime

# Common
import common.configure_django  # type: ignore # noqa: F401 - Modified global values

# Apps
from shows.models import Show

# Plugins
import plugins.show_scrapers as scrapers

if __name__ == "__main__":
    for show in Show.objects.all():
        print(f"Reimporting: {show.website} - {show}")
        show_scraper = scrapers.Scraper(show)

        show_scraper.import_all(minimum_modified_timestamp=datetime.now().astimezone())
