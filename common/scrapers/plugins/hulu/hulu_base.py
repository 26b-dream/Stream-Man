from __future__ import annotations

# Common
import common.extended_re as re


class HuluBase:
    WEBSITE = "Hulu"
    DOMAIN = "https://www.hulu.com"
    EPISODE_URL_REGEX = re.compile(r"^(?:https:\/\/www\.hulu\.com)?\/watch\/(?P<episode_id>.*)")
