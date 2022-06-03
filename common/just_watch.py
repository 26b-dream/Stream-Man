from __future__ import annotations

# Standard Library
import json

# Generic
import urllib.request
from datetime import date, datetime, timedelta

# Common
# Utils
from common.constants import DOWNLOADED_FILES_DIR
from common.extended_path import ExtendedPath
from common.scrapers import UPDATE_SUBSCLASSES


class JustWatch:
    NEW_DIR = DOWNLOADED_FILES_DIR / "JustWatch"

    def __init__(self, days_ago: int = 1) -> None:
        self.days_ago = days_ago
        self.date = date.today() - timedelta(days=days_ago)
        self.page = days_ago + 1

    def file_path(self, parsed_date: date) -> ExtendedPath:
        # Write the current day's file to temp because it may be an incomplete file
        if self.days_ago == 0:
            return self.NEW_DIR / "temp.json"
        # If a date was passed create a new file
        else:
            return self.NEW_DIR / ExtendedPath.convert_to_path(parsed_date).with_suffix(".json")

    def download(self) -> None:
        # If file already exists nothing needs to be downloaded
        if self.file_path(self.date).exists():
            return
        # Download file
        with urllib.request.urlopen(self.url()) as response:
            json_content = response.read()

        # Get date from file and save it using the date
        parsed_json = json.loads(json_content)
        date_from_json = parsed_json["days"][0]["date"]
        parsed_date = date.fromisoformat(date_from_json)
        self.file_path(parsed_date).write(json_content)

    def update(self):
        # Download page
        self.download()

        # Update information
        if self.file_path(self.date).exists():
            self.parsed_json = self.file_path(self.date).parsed_json()

            # Go through every website listed on JustWatch
            for provider in self.parsed_json["days"][0]["providers"]:

                # Go through every supported JustWatch website
                for subclass in UPDATE_SUBSCLASSES.values():
                    # If the website is not supported by ignore it
                    if int(provider["provider_id"]) not in subclass.JUSTWATCH_PROVIDER_IDS:
                        continue

                    # GO through each show and update local information if required
                    for show in provider["items"]:
                        subclass().justwatch_update(
                            show, datetime.fromtimestamp(self.file_path(self.date).stat().st_mtime).astimezone()
                        )

    def url(self) -> str:
        return (
            "https://apis.justwatch.com/content/titles/en_US/new?body="
            '{"providers":["nfx","amp","dnp","fuv","atp","itu","hlu","hbm","pct","pcp","amz","ply","yot","ytr","yfr","hbn","pmp","fmn","fdg","ifd","rkc","hop","tcw","cws","vdu","vuf","stz","crc","sho","pbs","pfx","fxn","tbv","knp","com","msf","cru","rbx","snx","mxg","abc","drv","crk","amc","fnd","cts","hst","nbc","epx","ffm","his","sfy","aae","lft","shd","scb","act","sdn","pcf","gdc","bbo","rlz","mbi","nfk","pty","bmg","umc","hvt","dvc","ytv","ern","mns","wwe","mot","anh","ang","htv","lol","ssc","pux","hmm","lmc","apk","abo","acn","apa","ahm","apm","avt","ame","sfx","stv","ptv","ahb","ash","hdv","vix","nfp","tpc","mtv","rtc","ast","cla","dkk","sft","chf","ovi","mhz","tfd","koc","vtv","asd","amu","aac","abb","afa","asb","asn","ctw","ads","usn","fus","fxf","bpc","azp","vik","amo","dkm","tcm","brv","tnt","fnw","bca","ind","ahc","tlc","hgt","diy","inv","sci","dea","apl","dil","dis","mtr","coo","tra","pnw","hrv","tvl","ltv","vho","fpm","adw","cgt","tus","asc","flr","rvy","dsv","rst","sod","oxy","hyh","vrv","tru","dnw","wet","dpu","awp","arg","plx","wow","alm","mgl","bhd","own","fmz","mvt","dog","trs","mst","daf","bph","kor","hoc","fmp"],'
            '"enable_provider_filter":false,'
            '"titles_per_provider":999999,'
            '"monetization_types":["ads","buy","flatrate","rent","free"],'
            f'"page":{self.page},'
            '"page_size":1,'
            '"fields":["full_path","id","jw_entity_id","object_type","offers","poster","scoring","season_number","show_id","show_title","title","tmdb_popularity","backdrops"]}'
            "&filter_price_changes=false&language=en"
        )
