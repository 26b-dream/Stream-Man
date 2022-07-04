# Common
import common.extended_re as re


class NetflixBase:
    WEBSITE = "Netflix"
    DOMAIN = "https://www.netflix.com"
    # Example show URLs
    #   https://www.netflix.com/title/80156387
    SHOW_URL_REGEX = re.compile(r"https?:\/\/www\.netflix\.com\/title\/*(?P<show_id>.*?)(?:\?|$)")
    # Example episode URLs
    #   https://www.netflix.com/watch/80156389
    EPISODE_URL_REGEX = re.compile(r"https:\/\/www\.netflix\.com\/watch\/*(?P<show_id>.*?)(?:\/|$)")
