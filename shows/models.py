from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional
    from django.db.models.query import QuerySet
    from shows.forms import EpisodeWatchForm
    from common.scrapers.shared import ScraperShowShared

# Standard Library
from datetime import date
from functools import cache

# Third Party
from typing_extensions import Self

# Django
from django.db import models

# Common
from common.model_helper import GetOrNew
from common.model_templates import ModelWithIdAndTimestamp


class Show(ModelWithIdAndTimestamp, GetOrNew):  # type: ignore - Composing abstract models always throws type errors
    objects: QuerySet[Self]
    season_set: QuerySet[Season]

    class Meta:  # type: ignore - Meta class always throws type errors
        db_table = "show"
        ordering = ["name"]
        unique_together = [["website", "show_id"], ["website", "show_id_2"]]

    website = models.CharField(max_length=64)  # Website the show is from

    show_id = models.CharField(max_length=64)
    # Alternative show_id used for cross referencing CrunchyRoll and Justwatch
    show_id_2 = models.CharField(max_length=64, null=True)
    name = models.CharField(max_length=256)
    media_type = models.CharField(max_length=256, null=True)
    description = models.TextField()
    image_url = models.CharField(max_length=256)
    thumbnail_url = models.CharField(max_length=255)
    update_at = models.DateTimeField(null=True)

    def __str__(self) -> str:
        return self.name

    def scraper_instance(self) -> ScraperShowShared:
        # Import this here as an easy work-a-around for circular imports
        # Common
        from common import scrapers

        return scrapers.Scraper(self)

    def last_watched_date(self, lazy: bool = False) -> date:
        if episode := EpisodeWatch.objects.filter(episode__season__show=self).order_by("watch_date").last():
            return episode.watch_date
        elif lazy:
            return date.fromtimestamp(0)
        else:
            raise ValueError("Show has no watched date")

    def latest_episode_date(self) -> date:
        if episode := Episode.objects.filter(season__show=self).order_by("release_date").last():
            return episode.release_date
        else:
            raise ValueError("Show has no airing date")

    def latest_episode_dates(self) -> QuerySet[Episode]:
        if episode := Episode.objects.filter(season__show=self).order_by("release_date").reverse():
            return episode
        else:
            raise ValueError(f"Show {self.name} {self.id} has no airing date")


class Season(ModelWithIdAndTimestamp, GetOrNew):  # type: ignore - Composing abstract models always throws type errors
    objects: QuerySet[Self]
    episode_set: QuerySet[Episode]

    class Meta:  # type: ignore - Meta class always throws type errors
        db_table = "season"
        unique_together = [["show", "season_id"]]
        ordering = ["show", "sort_order"]

    show = models.ForeignKey(Show, on_delete=models.CASCADE)  # Parent show

    name = models.CharField(max_length=500)
    # Netflix uses a string for season numbers like S1, P1
    # HIDIVE uses a float for season numbers likme 1.0, 2.0 etc
    # TODO: It may be possible to just convert these all to integers but I need more test data and websites
    number = models.CharField(max_length=255)
    # Add a sort_order field to compensate for number being a character field
    sort_order = models.PositiveSmallIntegerField(null=True)
    season_id = models.CharField(max_length=64)
    image_url = models.CharField(max_length=255)
    thumbnail_url = models.CharField(max_length=255)

    def __str__(self) -> str:
        return self.name


class Episode(ModelWithIdAndTimestamp, GetOrNew):  # type: ignore - Composing abstract models always throws type errors
    objects: QuerySet[Self]
    episode_watch_set: QuerySet[EpisodeWatch]

    class Meta:  # type: ignore - Meta class always throws type errors
        db_table = "episode"
        unique_together = [["season", "episode_id"]]
        ordering = ["season", "sort_order"]

    season = models.ForeignKey(Season, on_delete=models.CASCADE)  # Parent season

    # Values take directly from the website
    name = models.CharField(max_length=500)
    # CrunchyRoll has weird episode numbering sometime
    #   See Gintama Season 3: https://beta.crunchyroll.com/series/GYQ4MKDZ6/gintama
    #       Has episode 136C right after 256
    #   Episode number must be stored as a string to store things like episode 136C (see below)
    number = models.CharField(max_length=64)
    #   Because number is a string having an easy to sort value is nice
    sort_order = models.PositiveSmallIntegerField(null=True)
    episode_id = models.CharField(max_length=64)
    image_url = models.CharField(max_length=256)
    thumbnail_url = models.CharField(max_length=255)
    description = models.TextField()
    release_date = models.DateTimeField()
    duration = models.PositiveSmallIntegerField()

    def __str__(self) -> str:
        return self.name

    def is_watched(self) -> bool:
        return EpisodeWatch.objects.filter(episode=self).exists()

    def watch_count(self) -> int:
        return EpisodeWatch.objects.filter(episode=self).count()

    def last_watched(self) -> date:
        episode_info = EpisodeWatch.objects.filter(episode=self).order_by("watch_date").last()
        if episode_info:
            return episode_info.watch_date
        else:
            raise ValueError("Episode has no watched date")

    def unsafe_last_watched(self) -> Optional[date]:
        episode_info = EpisodeWatch.objects.filter(episode=self).order_by("watch_date").last()
        if episode_info:
            return episode_info.watch_date

    def duration_string(self) -> str:
        minutes = self.duration // 60
        seconds = self.duration % 60
        # Pad with an extra 0 so 23:5 becomes 23:05
        seconds_str = str(seconds).rjust(2, "0")

        return f"{minutes}:{seconds_str}"

    def url(self) -> str:
        # TODO: Clean this circular import garbage up
        # Import this here as an easy work-a-around for circular imports
        # Common
        from common import scrapers

        return scrapers.Scraper(self.season.show).episode_url(self)

    @cache  # Should never change and is safe to cache
    def scraper_instance(self) -> ScraperShowShared:
        # TODO: Clean this circular import garbage up
        # Import this here as an easy work-a-around for circular imports
        # Common
        from common import scrapers

        return scrapers.Scraper(self.season.show)

    def watch_form(self) -> EpisodeWatchForm:
        # TODO: Clean this circular import garbage up
        # Apps
        from shows.forms import EpisodeWatchForm

        return EpisodeWatchForm(initial={"episode": self, "watch_date": date.today()})


class EpisodeWatch(models.Model):
    """Tracks every time an episode is watched"""

    objects: QuerySet[Self]

    class Meta:  # type: ignore - Meta class always throws type errors
        db_table = "episode_watch"
        # Technically you can watch an episode more than once in a single day
        # It's far more likely to accidently mark an episode as watched twice in the same day
        # Adding a unique constraint here will avoid the possibility of accidently double-watching an episode
        unique_together = [["episode", "watch_date"]]
        ordering = ["watch_date"]

    episode = models.ForeignKey(Episode, on_delete=models.CASCADE)
    watch_date = models.DateField()

    def __str__(self) -> str:
        return f"{self.watch_date} - {self.episode}"
