from __future__ import annotations

# Common
import common.extended_re as re


class FunimationBase:
    WEBSITE = "Funimation"
    # Example URL: https://www.funimation.com/shows/kaguya-sama-love-is-war/
    # Example URL: https://www.funimation.com/shows/kaguya-sama-love-is-war/
    SHOW_URL_REGEX = re.compile(r"https:\/\/www\.funimation\.com\/shows\/*(?P<show_id>.*?)(?:\/|$)")

    # Example episode URLs
    #   https://www.funimation.com/v/aria/that-wonderful-miracle
    EPISODE_URL_REGEX = re.compile(r"https:\/\/www\.funimation\.com\/v\/*(?P<show_id>.*?)\/*(?P<episode_id>.*)")
