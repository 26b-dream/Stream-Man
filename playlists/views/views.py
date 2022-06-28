from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

# Standard Library
import json

# Django
from django.shortcuts import render

# Apps
# Playlists
from playlists.forms import PlaylistHideSeasonFormSet, PlaylistSortForm
from playlists.models import Playlist, PlaylistSeason


def index(request: HttpRequest) -> HttpResponse:
    """Show all playlists"""
    return render(request, "playlists/index.html", {"playlists": Playlist.objects.all})


def playlist(request: HttpRequest, playlist_id: int) -> HttpResponse:
    """Show information for a playlist"""
    playlist = Playlist.objects.filter(id=playlist_id)[0]
    playlist_order_form = PlaylistSortForm(request.POST)

    # Get a json representation of the form data for filtering episodes
    #   This data is passed to the form modal so the filters used in the last result are shown
    playlist_filter_json = json.dumps(playlist_order_form.cleaned_data) if playlist_order_form.is_valid() else ""

    sorted_episodes = playlist.sorted_episodes(playlist_order_form)
    playlist_season_skip = (
        PlaylistSeason.objects.filter(playlist_show__playlist=playlist).all().select_related("playlist_show")
    )
    hide_season_formset = PlaylistHideSeasonFormSet(queryset=playlist_season_skip)

    return render(
        request,
        "playlists/playlist.html",
        {
            "playlist": playlist,
            "sorted_episodes": sorted_episodes,
            "playlist_filter_json": playlist_filter_json,
            "request_post_json": json.dumps(request.POST),
            "hide_season_formset": hide_season_formset,
        },
    )


# TODO: This is not actually implemented at all this is just a placeholder for a future idea
def playlist_shows(request: HttpRequest, playlist_id: int):
    pass
