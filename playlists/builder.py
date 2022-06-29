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
    def episodes_grouped_by_show_tuple(
        cls,
        episodes: QuerySet[Episode],
        episode_order: Callable[[QuerySet[Episode]], QuerySet[Episode]],
        reverse_episodes: bool,
    ) -> list[tuple[Show, list[Episode]]]:
        """Group a QuerySet of epsodes into a nested list that is grouped by the show"""
        # Sort episodes by show to make it easier to group them by show
        episodes = episode_order(episodes)
        if reverse_episodes:
            episodes = episodes.reverse()

        grouped_episodes_list: list[tuple[Show, list[Episode]]] = []
        grouped_episodes_dict: dict[Show, list[Episode]] = {}

        # It's easier just to check if there are episodes instead of integrating management of empty values
        if episodes:
            # Group episodes by show

            for episode in episodes:
                show = episode.season.show
                # If this is the first episode of the palylist or the show is different than the last one that was added
                if not grouped_episodes_dict.get(show):
                    grouped_episodes_dict[show] = [episode]
                else:
                    grouped_episodes_dict[show].append(episode)

        for show, episode_list in grouped_episodes_dict.items():
            grouped_episodes_list.append((show, episode_list))
        return grouped_episodes_list

    # TODO: Make other functions use this style of episodes list building to make code more DRY
    @classmethod
    def build_list(
        cls,
        episodes: QuerySet[Episode],
        sort_function: Callable[[list[tuple[Show, list[Episode]]]], None],
        reverse_shows: bool,
        episode_order_function: Callable[[QuerySet[Episode]], QuerySet[Episode]],
        reverse_episodes: bool,
        change_show_function: Callable[[list[tuple[Show, list[Episode]]]], bool],
        resort_function: Callable[[list[tuple[Show, list[Episode]]]], None],
    ) -> list[Episode]:
        output: list[Episode] = []

        # Check if the playlist has episodes so empty playlists are dealth with
        if episodes:
            grouped_episodes = cls.episodes_grouped_by_show_tuple(episodes, episode_order_function, reverse_episodes)
            sort_function(grouped_episodes)

            if reverse_shows:
                grouped_episodes.reverse()

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

    class ShowOrder:
        acceptable_functions: list[tuple[str, str]] = []

        @classmethod
        def random(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
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

    class EpisodeOrder:
        acceptable_functions: list[tuple[str, str]] = []

        @classmethod
        def random(cls, episodes: QuerySet[Episode]) -> QuerySet[Episode]:
            return episodes.order_by("?")

        @classmethod
        def chronological(cls, episodes: QuerySet[Episode]) -> QuerySet[Episode]:
            return episodes.order_by("season__sort_order", "sort_order")

    class ChangeShowIf:
        acceptable_functions: list[tuple[str, str]] = []

        @classmethod
        def after_every_episode(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> bool:
            return True

        @classmethod
        def when_show_is_complete(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> bool:
            return False

    class Resort:
        acceptable_functions: list[tuple[str, str]] = []

        @classmethod
        def rotate(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            grouped_episodes.append(grouped_episodes.pop(0))

        @classmethod
        def shuffle(cls, grouped_episodes: list[tuple[Show, list[Episode]]]) -> None:
            random.shuffle(grouped_episodes)


for x in [Builder.ShowOrder, Builder.Resort, Builder.ChangeShowIf, Builder.EpisodeOrder]:
    for method in [method for method in dir(x) if method.startswith("_") is False]:
        if method != "acceptable_functions":
            print(method)
            x.acceptable_functions.append((method, method.replace("_", " ").title()))  # type: ignore - This just throws errors because of the loop
