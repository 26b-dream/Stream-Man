from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

# Django
from django.shortcuts import render

# Apps
# Playlists
from playlists.forms import (
    PlaylistHideSeasonFormSet,
    PlaylistnewForm,
    PlaylistQueFormSet,
    PlaylistRemoveShowFormSet,
    PlaylistSortForm,
)
from playlists.models import (
    Playlist,
    PlaylistImportQueue,
    PlaylistSeason,
    PlaylistShow,
    Season,
)


def new_playlist(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "playlists/modal_new_playlist.html",
        {"new_playlist_form": PlaylistnewForm()},
    )


def filter_episodes(request: HttpRequest, playlist_id: int) -> HttpResponse:
    """Show modal to filter episodes in a playlist"""
    playlist = Playlist.objects.filter(id=playlist_id)[0]

    # If playlist is invalid create a new form that will have the default values set
    #   This is done to set the default number of episodes shown at 100
    playlist_order_form = PlaylistSortForm(request.POST)
    if not playlist_order_form.is_valid():
        print(playlist_order_form.errors)
        print("INVALID")
        print("INVALID")
        print("INVALID")
        print("INVALID")
        print("INVALID")
        print("INVALID")
        print("INVALID")
        print("INVALID")
        print("INVALID")
        print("INVALID")
        print("INVALID")
        print("INVALID")
        print("INVALID")
        print("INVALID")
        playlist_order_form = PlaylistSortForm()

    # TODO: Form validation
    return render(
        request,
        "playlists/modal_filter_episodes.html",
        {
            "playlist": playlist,
            "playlist_order_form": playlist_order_form,
        },
    )


def add_show(request: HttpRequest, playlist_id: int) -> HttpResponse:
    playlist = Playlist.objects.filter(id=playlist_id)[0]
    playlist_que_form_set = PlaylistQueFormSet(
        initial=[{"url": x.url} for x in PlaylistImportQueue.objects.filter(playlist=playlist)]
    )

    return render(
        request,
        "playlists/modal_add_show.html",
        {"playlist": playlist, "playlist_que_form_set": playlist_que_form_set},
    )


def hide_season(request: HttpRequest, playlist_id: int) -> HttpResponse:
    playlist = Playlist.objects.filter(id=playlist_id).first()
    playlist_shows = PlaylistShow.objects.filter(playlist=playlist).select_related("show")

    # Update all season entries for this playlist
    # TODO: This can probably be heavily optimized
    bulk_create_entries: list[PlaylistSeason] = []
    for playlist_show in playlist_shows:
        seasons = Season.objects.filter(show=playlist_show.show)
        for season in seasons:
            bulk_create_entries.append(PlaylistSeason(playlist_show=playlist_show, season=season))

    PlaylistSeason.objects.bulk_create(bulk_create_entries, ignore_conflicts=True)

    playlist_season_skip = (
        PlaylistSeason.objects.filter(playlist_show__playlist=playlist)
        .all()
        .select_related("playlist_show")
        .order_by("playlist_show__show__name")
    )
    hide_season_formset = PlaylistHideSeasonFormSet(queryset=playlist_season_skip)

    return render(
        request,
        "playlists/modal_hide_season.html",
        {"playlist": playlist, "hide_season_formset": hide_season_formset},
    )


def remove_show(request: HttpRequest, playlist_id: int) -> HttpResponse:
    playlist = Playlist.objects.filter(id=playlist_id)[0]
    remove_show_formset = PlaylistRemoveShowFormSet(
        queryset=PlaylistShow.objects.filter(playlist=playlist).all().select_related("show").order_by("show__title")
    )

    return render(
        request,
        "playlists/modal_remove_show.html",
        {"playlist": playlist, "remove_show_formset": remove_show_formset},
    )
