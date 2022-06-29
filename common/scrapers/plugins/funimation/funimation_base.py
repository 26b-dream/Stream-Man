# Common
import common.extended_re as re


class FunimationBase:
    WEBSITE = "Funimation"

    # Example episode URLs
    #   https://www.funimation.com/v/aria/that-wonderful-miracle
    EPISODE_URL_REGEX = re.compile(r"https:\/\/www\.funimation\.com\/v\/*(?P<show_id>.*?)\/*(?P<episode_id>.*)")
