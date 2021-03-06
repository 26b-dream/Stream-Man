from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Optional

# Standard Library
from datetime import date, datetime

# Common
import common.extended_re as re

# Apps
from shows.models import Show

# Local
from .hidive_base import HidiveBase
from .hidive_show import HidiveShow

# Plugins
from plugins.streaming.shared import ScraperUpdateShared


class HidiveUpdate(HidiveBase, ScraperUpdateShared):
    JUSTWATCH_PROVIDER_IDS = [283]

    def justwatch_update(self, justwatch_entry: dict[str, Any], date: datetime) -> None:
        justwatch_url = justwatch_entry["offers"][0]["urls"]["standard_web"]
        # Sometimes the URL from JustWatch is for an episode, sometimes it's for a movie which are completely different formats
        # TODO: Manage this format
        season_id = re.search(self.EPISODE_URL_REGEX, justwatch_url)
        if season_id:
            season_id = season_id.group("season_id")
            show = Show.objects.filter(website=self.WEBSITE, season__season_id=season_id)

            # If there is a show entry make sure the information is newer than the JustWatch entry
            if show:
                HidiveShow(show[0]).import_all(minimum_info_timestamp=date)

    # TODO: Implement this function
    def check_for_updates(self, earliest_date: Optional[date] = None) -> None:
        pass
