from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models.query import QuerySet

    from typing import Callable

# Standard Library
import random

# Apps
from shows.models import Episode, Show


class Builder:
    @classmethod
    def episodes_grouped_by_show_tuple(cls, episodes: QuerySet[Episode]) -> list[tuple[Show, list[Episode]]]:
        """Group a QuerySet of epsodes into a nested list that is grouped by the show"""
        # Sort episodes by show to make it easier to group them by show
        episodes = episodes.order_by("season__show")
        grouped_episodes: list[tuple[Show, list[Episode]]] = []

        # It's easier just to check if there are episodes instead of integrating management of empty values
        if episodes:
            # Group episodes by show

            for episode in episodes:
                # If this is the first episode of the palylist or the show is different than the last one that was added
                if not grouped_episodes or grouped_episodes[-1][0] != episode.season.show:
                    grouped_episodes.append((episode.season.show, [episode]))
                else:
                    grouped_episodes[-1][1].append(episode)
        return grouped_episodes

    # TODO: Make other functions use this style of episodes list building to make code more DRY
    @classmethod
    def build_list(
        cls,
        episodes: QuerySet[Episode],
        sort_function: Callable[[list[tuple[Show, list[Episode]]]], None],
        change_show_function: Callable[[list[tuple[Show, list[Episode]]]], bool],
        resort_function: Callable[[list[tuple[Show, list[Episode]]]], None],
    ) -> list[Episode]:
        output: list[Episode] = []
        output: list[Episode] = []
        if episodes:
            grouped_episodes = cls.episodes_grouped_by_show_tuple(episodes)
            # Shows may be in the playlist and have no episodes watched yet so use lazy last_watched_date
            sort_function(grouped_episodes)

            # Loop until every episode has been sorted
            while grouped_episodes:
                show_episodes = grouped_episodes[0][1]
                # Shows may be in the playlist and have no episodes watched yet so use lazylast_watched_date
                output.append(show_episodes.pop(0))
                # If all the episodes are used up from a show, remove the show from the list
                if not show_episodes:
                    grouped_episodes.pop(0)
                # Check if show need to be reorganized after one episode is used and do so if required
                elif change_show_function(grouped_episodes):
                    resort_function(grouped_episodes)

        return output

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

        @classmethod
        def finish_up(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            grouped_episodes.sort(key=cls.__finish_up_value)

        @classmethod
        def __finish_up_value(cls, show: tuple[Show, list[Episode]]) -> int:
            total = 0
            for episode in show[1]:
                total += episode.duration
            return total

    class ChangeShowIf:
        @classmethod
        def always(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> bool:
            return True

        @classmethod
        def never(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> bool:
            return False

        @classmethod
        def more_than_one_show(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> bool:
            return len(grouped_episodes) > 1

    class Resort:
        @classmethod
        def rotate(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            grouped_episodes.append(grouped_episodes.pop(0))

        @classmethod
        def swap_1_and_2(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            grouped_episodes[0], grouped_episodes[1] = grouped_episodes[1], grouped_episodes[0]

        pass
