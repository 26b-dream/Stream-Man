from __future__ import annotations

# Common
import common.extended_re as re


class FunimationBase:
    WEBSITE = "Funimation"
    SHOW_URL_REGEX = re.compile(r"https:\/\/www\.funimation\.com\/(?:show|v)\/*(?P<show_id>.*?)(?:\/|$)")
