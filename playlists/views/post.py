from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

# Standard Library
from datetime import date, datetime

# Django
from django.db.models import F
from django.http import HttpResponseRedirect

# Common
from common.just_watch import JustWatch

# Apps
# Shows
from shows.models import Show

# Apps
# Playlists
from playlists.forms import (
    PlaylistHideSeasonFormSet,
    PlaylistnewForm,
    PlaylistQueFormSet,
    PlaylistRemoveShowFormSet,
    PlaylistRenameForm,
)
from playlists.functions import update_form, update_queue
from playlists.models import Playlist, PlaylistImportQueue, PlaylistShow

# Plugins
from plugins import show_scrapers


# TODO: This code is not optimized at all, and should probably be moved into a separate function
def playlist_que_formset(request: HttpRequest, playlist_id: int) -> HttpResponse:
    """Updates and imports shows for a playlist"""
    playlist = Playlist.objects.get(id=playlist_id)
    formset = PlaylistQueFormSet(request.POST)

    # Update the queue
    update_queue(playlist, formset)

    # If required import the queue
    if request.POST.get("import_queue") == "Import Queue":
        shows_in_que = PlaylistImportQueue.objects.filter(playlist=playlist).all()
        for show_in_que in shows_in_que:
            # Import show information
            show_scraper = show_scrapers.Scraper(show_in_que.url)

            # Import information
            show_scraper.import_all()

            # Link show to playlist
            # get_or_create in case the show is already in the playlist
            PlaylistShow.objects.get_or_create(playlist=playlist, show=show_scraper.show_info)

            # Delete show from que
            show_in_que.delete()

    return HttpResponseRedirect(f"/playlists/{playlist_id}")


def new_playlist_form(request: HttpRequest) -> HttpResponse:
    """Create a new playlist"""
    form = PlaylistnewForm(request.POST)

    if form.is_valid():
        playlist = form.save()
        return HttpResponseRedirect(f"/playlists/{playlist.id}")
    else:
        return HttpResponseRedirect("/playlists")


def hide_season_formset(request: HttpRequest, playlist_id: int) -> HttpResponse:
    return update_form(PlaylistHideSeasonFormSet(request.POST), playlist_id)


def rename_playlist_form(request: HttpRequest, playlist_id: int) -> HttpResponse:
    return update_form(PlaylistRenameForm(request.POST), playlist_id)


def remove_show_formset(request: HttpRequest, playlist_id: int) -> HttpResponse:
    return update_form(PlaylistRemoveShowFormSet(request.POST), playlist_id)


# TODO: This is a mess
def update_shows(request: HttpRequest, playlist_id: int) -> HttpResponseRedirect:
    for website in show_scrapers.UPDATE_SUBSCLASSES.values():
        # TODO: For some reason scrapers.UPDATE_SUBSCLASSES's type includes the abstract class
        # TODO: In reality it is only implementations of the abstract class
        # TODO: This causes type errors
        # TODO: Fix this some time in the future
        website().check_for_updates()  # type: ignore

    playlist = Playlist.objects.get(id=playlist_id)

    for show in playlist.shows.filter(info_timestamp__lt=F("update_at"), update_at__lte=datetime.now().astimezone()):
        if not show.update_at:
            raise Exception("Show update_at is None")

        print(f"Updating: {show}")
        show.scraper_instance().import_all(minimum_info_timestamp=show.update_at)

    oldest_show = Show.objects.order_by("info_timestamp").first()
    if oldest_show:
        # This value is set to always start on July 1st as a starting point
        days = (date.today() - oldest_show.info_timestamp.date()).days

        # Update all information for this date range
        for x in range(0, days):
            just_watch_info = JustWatch(x)
            just_watch_info.update()

    return HttpResponseRedirect(f"/playlists/{playlist_id}")
