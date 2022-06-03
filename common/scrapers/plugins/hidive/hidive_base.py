from __future__ import annotations

# Common
import common.extended_re as re


class HidIveBase:
    WEBSITE = "HIDIVE"
    DOMAIN = "https://www.hidive.com"
    EPISODE_URL_REGEX = re.compile(r"^(?:https?:\/\/www\.hidive\.com)?\/stream\/(?P<season_id>.*?)\/(?P<episode_id>.*)")
