from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models.query import QuerySet
    from playlists.forms import PlaylistSortForm
    from typing import Optional
    from typing_extensions import Self


# Standard Library
import random
from datetime import datetime

# Django
from django.db import models

# Apps
# Shows
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

        # By default sort by picking a random show and picking the first episode chronologically
        #   Any other fun order I can think of will also be added
        if options.get("order") == "random":
            episodes = episodes.order_by("?")
        elif options.get("order") == "newest":
            episodes = episodes.order_by("-release_date")
        elif options.get("order") == "smart_newest_straight":
            episodes = self.__smart_newest_straight(episodes)
        elif options.get("order") == "smart_newest_mixed":
            episodes = self.__smart_newest_mixed(episodes)
        elif options.get("order") == "least_recently_watched":
            episodes = self.__least_recently_watched(episodes)
        else:
            episodes = self.__episodes_normal_order(episodes)

        # Have the option to reverse the order of the episodes
        #   This is most useful when sorting by episode dates
        if options.get("reverse"):
            # list.reverse() and QuerySet.reverse() are different
            #   list.reverse() modifies existing list
            #   QuerySet.reverse() returns a new QuerySet
            #   Therefore they need different function calls
            #   Functionall, you can use episodes = reversed(episodes) but that returns a weird type
            #   TODO: Figure out how to work with the return type of reversed()
            if isinstance(episodes, list):
                episodes.reverse()
            else:
                episodes = episodes.reverse()
        # If no number of episodes are given default to 100
        number_of_episodes = options.get("number_of_episodes", playlist_order_form["number_of_episodes"].initial)
        return episodes[:number_of_episodes]

    # TODO: Should this be offloaded to Builder?
    # TODO: Add support for correctly sorting watched episodes
    def __least_recently_watched(self, episodes: QuerySet[Episode]) -> list[Episode]:
        """Sort episodes based on least recently watched, kind of...\n
        Does not yhet support properly sorting previously watched episodes, just new episodes\n
        Supporting least recently watched on a per episode basis should be easy I just don't have the time"""

        return Builder.build_list(
            episodes, Builder.Sort.least_recently_watched, Builder.Check.more_than_one_show, Builder.Resort.rotate
        )

    # TODO: Should this be offloaded to Builder?
    def __smart_newest_straight(self, episodes: QuerySet[Episode]) -> list[Episode]:
        """Sort episodes based on newest first but keep episodes order\n
        This version will let one show exist for multiple episodes in row\n
        This is useful when watching multiple shows that are all airing at the same time"""
        return Builder.build_list(
            episodes, Builder.Sort.newest_episodes_first, Builder.Check.newer_episode, Builder.Resort.swap_1_and_2
        )

    # TODO: Should this be offloaded to Builder?
    def __smart_newest_mixed(self, episodes: QuerySet[Episode]) -> list[Episode]:
        """Sort episodes based on newest first but keep episodes order\n
        This version will let one show exist multiple times in a row"""
        return Builder.build_list(
            episodes, Builder.Sort.newest_episodes_first, Builder.Check.always, Builder.Resort.rotate
        )

    # TODO: Should this be offloaded to Builder?
    def __episodes_normal_order(self, episodes: QuerySet[Episode]) -> list[Episode]:
        return Builder.build_list(episodes, Builder.Sort.shuffle, Builder.Check.always, Builder.Sort.shuffle)

    class Builder:
        class Sort:
            @classmethod
            def shuffle(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
                random.shuffle(grouped_episodes)

            @classmethod
            def least_recently_watched(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
                grouped_episodes.sort(key=lambda episode: episode[0].last_watched_date(lazy=True))

            @classmethod
            def newest_episodes_first(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
                grouped_episodes.sort(key=lambda episode: episode[0].latest_episode_date(), reverse=True)

        class Check:
            @classmethod
            def always(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> bool:
                return True

            @classmethod
            def more_than_one_show(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> bool:
                return len(grouped_episodes) > 1

            # TODO: Move to builder class (requires possibly moving latest_episode_date as well)
            @classmethod
            def newer_episode(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> bool:
                return len(grouped_episodes) > 1 and cls.latest_episode_date(
                    grouped_episodes[0][1]
                ) < cls.latest_episode_date(grouped_episodes[1][1])

            @classmethod
            def latest_episode_date(cls, episodes: list[Episode]) -> datetime:
                """Get the newest episode date from a list of episodes"""
                sorted_episodes: list[Episode] = sorted(episodes, key=lambda episode: episode.release_date)
                return sorted_episodes[-1].release_date

        class Resort:
            @classmethod
            def rotate(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
                grouped_episodes.append(grouped_episodes.pop(0))

            @classmethod
            def swap_1_and_2(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
                grouped_episodes[0], grouped_episodes[1] = grouped_episodes[1], grouped_episodes[0]

            pass


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
