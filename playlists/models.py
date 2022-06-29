from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models.query import QuerySet
    from playlists.forms import PlaylistSortForm
    from typing import Optional
    from typing_extensions import Self


# Django
from django.db import models

# Apps
from shows.models import Episode, Season, Show

# Local
from .builder import Builder


class Playlist(models.Model):
    objects: QuerySet[Self]

    class Meta:  # type: ignore - class Meta always throws errors
        db_table = "playlist"

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=64, unique=True)
    shows: models.ManyToManyField[Show, Playlist] = models.ManyToManyField(Show, through="PlaylistShow")

    def __str__(self) -> str:
        return self.name

    def episodes(self) -> QuerySet[Episode]:
        """Get a QuerySet for all of the episodes in this playlist"""
        # Get all of the shows in the playlist
        show_ids = Show.objects.filter(show_id__in=self.shows.values_list("show_id"))

        # Get the seasns to skip
        seasons_to_skip = PlaylistSeason.objects.filter(playlist_show__playlist=self, skip=True).values_list("season")

        # Get episodes that are in the playlist and not set to be skipped
        return (
            Episode.objects.filter(season__show__in=show_ids)
            .exclude(season__in=seasons_to_skip)
            .select_related("season__show", "season")
        )

    # This needs to be return an an optional value because playlists start with no shows
    def random_episode(self) -> Optional[Episode]:
        """Returns a random episode from the playlist or None if there are no episodes"""
        return self.episodes().order_by("?").first()

    # TODO: Should this be offloaded to Builder?
    def sorted_episodes(self, playlist_order_form: PlaylistSortForm) -> list[Episode] | QuerySet[Episode]:
        episodes = self.episodes()

        # Validate form first so default values can be more easily set
        if playlist_order_form.is_valid():
            options: dict[str, list[str] | str] = playlist_order_form.cleaned_data
        # Invalid forms will always exist when the page is loaded with no filtering
        else:
            options = {}
            options["episode_filter"] = []

        # By default only show unwatched episodes
        #   Have the option to show watched episodes as well
        if "include_watched" not in options["episode_filter"]:
            episodes = episodes.filter(episodewatch__isnull=True)

        # By default show all shows
        #   Have the option to only show shows that have been started
        if "only_started_shows" in options["episode_filter"]:
            # Find all shows that have been started
            shows = Show.objects.filter(season__episode__episodewatch__isnull=False).distinct()
            episodes = episodes.filter(season__show__in=shows)

        # By default show all shows
        #   Have the option to only show shows that have been started
        if "only_new_shows" in options["episode_filter"]:
            # Find all shows that have been started
            shows = Show.objects.filter(season__episode__episodewatch__isnull=False).distinct()
            episodes = episodes.exclude(season__show__in=shows)

        # Filter by website
        if options.get("websites"):
            websites = [x for x in options["websites"]]
            episodes = episodes.filter(season__show__website__in=websites)

        episodes = Builder.build_list(
            episodes,
            getattr(Builder.ShowOrder, str(options.get("show_order")), Builder.ShowOrder.random),
            "shows" in options.get("reverse", []),
            getattr(Builder.EpisodeOrder, str(options.get("episode_order")), Builder.EpisodeOrder.chronological),
            "episodes" in options.get("reverse", []),
            getattr(Builder.ChangeShowIf, str(options.get("change_show")), Builder.ChangeShowIf.after_every_episode),
            getattr(Builder.Resort, str(options.get("rotate_type")), Builder.Resort.rotate),
        )

        # If no number of episodes are given default to 100
        number_of_episodes = options.get("number_of_episodes", playlist_order_form["number_of_episodes"].initial)
        return episodes[:number_of_episodes]


class PlaylistShow(models.Model):
    """Track what shows are in a playlist"""

    objects: QuerySet[Self]

    class Meta:  # type: ignore - class Meta always throws errors
        db_table = "playlist_show"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "playlist_id",
                    "show_id",
                ],
                name="playlist_id show_id",
            )
        ]

    id = models.AutoField(primary_key=True)
    show = models.ForeignKey(Show, on_delete=models.CASCADE)
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE)
    playlist_season: models.ManyToManyField[Season, PlaylistShow] = models.ManyToManyField(
        Season, through="PlaylistSeason"
    )

    def __str__(self) -> str:
        return f"{self.playlist} - {self.show}"


# CrunchyRoll has dubs as seperate seasons so sometimes an entire season needs to be ignored
# Example: https://www.crunchyroll.com/miss-kobayashis-dragon-maid
# For simplicity this is set up where if a value exists skip that season
# This way I don't need to have an entry for every season in the playlists that needs to be kept in sync with the show's information
class PlaylistSeason(models.Model):
    """Tracks what seasons should be used for a playlist"""

    objects: QuerySet[Self]

    class Meta:  # type: ignore - class Meta always throws errors
        db_table = "playlist_season_skip"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "playlist_show",
                    "season_id",
                ],
                name="playlist_show season_id",
            )
        ]

    id = models.AutoField(primary_key=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    playlist_show = models.ForeignKey(PlaylistShow, on_delete=models.CASCADE)
    skip = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.playlist_show.playlist} - {self.season.show} - {self.season}"


# A simple que of URLs to import for a playlist
class PlaylistImportQueue(models.Model):
    """Tracks URLs that need to be imported for a playlist"""

    objects: QuerySet[Self]

    class Meta:  # type: ignore - class Meta always throws errors
        db_table = "playlist_que"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "playlist",
                    "url",
                ],
                name="playlist url",
            )
        ]

    id = models.AutoField(primary_key=True)
    url = models.CharField(max_length=256)
    playlist: Playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE)  # type: ignore

    def __str__(self) -> str:
        return f"{self.playlist} - {self.url}"
