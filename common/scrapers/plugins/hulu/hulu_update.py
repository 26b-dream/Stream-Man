from __future__ import annotations

from typing import TYPE_CHECKING

# Standard Library
from unicodedata import name

if TYPE_CHECKING:
    from typing import Any, Optional

# Standard Library
from datetime import date, datetime

# Common
import common.extended_re as re
from common.scrapers.plugins.hulu.hulu_base import HuluBase
from common.scrapers.plugins.hulu.hulu_show import HuluShow
from common.scrapers.shared import ScraperUpdateShared

# Apps
from shows.models import Show


class HuluUpdate(HuluBase, ScraperUpdateShared):
    JUSTWATCH_PROVIDER_IDS = [15]

    def justwatch_update(self, justwatch_entry: dict[str, Any], date: datetime) -> None:
        # Only information on JustWatch that can be cross referenced is the title
        show_title = justwatch_entry["show_title"]
        show = Show.objects.filter(website=self.WEBSITE, name=show_title)
        if show:
            HuluShow(show[0]).import_all(minimum_info_timestamp=date)

    # Netflix doesn't have any calendar of sorts for this function
    def check_for_updates(self, earliest_date: Optional[date] = None) -> None:
        return
