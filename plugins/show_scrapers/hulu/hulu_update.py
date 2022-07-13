from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Optional

# Standard Library
from datetime import date, datetime

# Apps
from shows.models import Show

# Plugins
from plugins.show_scrapers.hulu.hulu_base import HuluBase
from plugins.show_scrapers.hulu.hulu_show import HuluShow
from plugins.show_scrapers.shared import ScraperUpdateShared


class HuluUpdate(HuluBase, ScraperUpdateShared):
    JUSTWATCH_PROVIDER_IDS = [15]

    def justwatch_update(self, justwatch_entry: dict[str, Any], date: datetime) -> None:
        # Only information on JustWatch that can be cross referenced is the title
        # List all keys for justwatch_entry
        # TODO: This is supposed to be a temporary workaround...
        show_title = justwatch_entry.get("show_title") or justwatch_entry.get("title")
        show = Show.objects.filter(website=self.WEBSITE, name=show_title)
        if show:
            HuluShow(show[0]).import_all(minimum_info_timestamp=date)

    # Netflix doesn't have any calendar of sorts for this function
    def check_for_updates(self, earliest_date: Optional[date] = None) -> None:
        return
