from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Optional

# Standard Library
from datetime import date, datetime

# Common
from common.scrapers.plugins.discoveryplus.discoveryplus_base import DiscoveryplusBase
from common.scrapers.plugins.discoveryplus.discoveryplus_show import DiscoveryPlusShow
from common.scrapers.shared import ScraperUpdateShared

# Apps
from shows.models import Show


class DiscoveryPlusUpdate(DiscoveryplusBase, ScraperUpdateShared):
    JUSTWATCH_PROVIDER_IDS = [15]

    def justwatch_update(self, justwatch_entry: dict[str, Any], date: datetime) -> None:
        # Only information on JustWatch that can be cross referenced is the title
        # TODO: This is supposed to be a temporary workaround...
        show_title = justwatch_entry.get("show_title")
        show = Show.objects.filter(website=self.WEBSITE, name=show_title)
        if show:
            DiscoveryPlusShow(show[0]).import_all(minimum_info_timestamp=date)

    # Hulu doesn't have any calendar of sorts for this function
    def check_for_updates(self, earliest_date: Optional[date] = None) -> None:
        return
