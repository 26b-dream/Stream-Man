from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Optional

# Standard Library
from datetime import date, datetime

# Common
import common.extended_re as re
from common.scrapers.plugins.netflix.netflix_base import NetflixBase
from common.scrapers.plugins.netflix.netflix_show import NetflixShow
from common.scrapers.shared import ScraperUpdateShared

# Apps
from shows.models import Show


class NetflixUpdate(NetflixBase, ScraperUpdateShared):
    JUSTWATCH_PROVIDER_IDS = [8]

    def justwatch_update(self, justwatch_entry: dict[str, Any], date: datetime) -> None:
        justwatch_url = justwatch_entry["offers"][0]["urls"]["standard_web"]
        show_id = re.strict_search(self.SHOW_URL_REGEX, justwatch_url).group("show_id")
        show = Show.objects.filter(website=self.WEBSITE, show_id=show_id)
        # If there is a show entry make sure the information is newer than the JustWatch entry
        if show:
            NetflixShow(show[0]).import_all(minimum_info_timestamp=date)

    # Netflix doesn't have any calendar of sorts for this function
    def check_for_updates(self, earliest_date: Optional[date] = None) -> None:
        pass
