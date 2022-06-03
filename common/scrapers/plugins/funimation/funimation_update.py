from __future__ import annotations

from typing import TYPE_CHECKING

# Common
from common.scrapers.plugins.funimation.funimation_base import FunimationBase

if TYPE_CHECKING:
    from typing import Any, Optional

    # Standard Library
    from datetime import date


# Standard Library
from datetime import datetime

# Common
import common.extended_re as re
from common.scrapers.shared import ScraperUpdateShared

# Apps
# Shows
from shows.models import Show

# Local
from .funimation_show import FunimationShow


class FunimationUpdate(ScraperUpdateShared, FunimationBase):
    JUSTWATCH_PROVIDER_IDS = [269]

    def check_for_updates(self, earliest_date: Optional[date] = None) -> None:
        """Not actuually implemented because I think Funimation is going to be shut down soon"""
        pass

    def justwatch_update(self, justwatch_entry: dict[str, Any], date: datetime) -> None:
        justwatch_url = justwatch_entry["offers"][0]["urls"]["standard_web"]
        show_id = re.strict_search(self.SHOW_URL_REGEX, justwatch_url).group("show_id")
        show = Show.objects.filter(website=self.WEBSITE, show_id=show_id)

        # If there is a show entry make sure the information is newer than the JustWatch entry
        if show:
            FunimationShow(show[0]).import_all(minimum_info_timestamp=date)
