from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

# Django
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render

# Local
from .forms import EpisodeWatchForm
from .models import Episode, Season, Show


def show(request: HttpRequest, show_id: int) -> HttpResponse:
    show = Show.objects.filter(id=show_id)[0]
    return HttpResponse(f"TODO: Implement show page, {show}")


def season(request: HttpRequest, season_id: int) -> HttpResponse:
    season = Season.objects.filter(id=season_id)[0]
    return HttpResponse(f"TODO: Implement season page, {season}")


def show_index(request: HttpRequest) -> HttpResponse:
    return HttpResponse("TODO: Implement show index page")


def episode(request: HttpRequest, episode_id: int) -> HttpResponse:
    episode = Episode.objects.get(id=episode_id)
    return HttpResponse(f"TODO: Implement episode page, {episode}")


def episode_modal(request: HttpRequest, episode_id: int) -> HttpResponse:
    episode = Episode.objects.get(id=episode_id)
    return render(request, "episodes/modal.html", {"episode": episode})


def post_episode_watch_form(request: HttpRequest, episode_id: int) -> HttpResponseRedirect:
    form = EpisodeWatchForm(request.POST)
    if form.is_valid():
        form.save()
    else:
        raise Exception("Form is not valid")
    return HttpResponseRedirect("/playlists")
