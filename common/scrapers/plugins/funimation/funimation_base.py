from __future__ import annotations

# Common
import common.extended_re as re


class FunimationBase:
    WEBSITE = "Funimation"
    # Example URL: https://www.funimation.com/shows/kaguya-sama-love-is-war/
    SHOW_URL_REGEX = re.compile(r"https:\/\/www\.funimation\.com\/shows\/*(?P<show_id>.*?)(?:\/|$)")
