from __future__ import annotations

# Django
from django.db import transaction
from django.forms import BaseModelFormSet, ModelForm
from django.http import HttpResponse, HttpResponseRedirect

# Local
from .forms import PlaylistQueFormSet
from .models import Playlist, PlaylistImportQueue


# This as a seperate function because the transaction needs to be atomic
# If this is not atomic the entire queue could be accidently deleted
@transaction.atomic
def update_queue(playlist: Playlist, formset: PlaylistQueFormSet) -> None:
    """Updates all urls in the playlist's queue"""
    if formset.is_valid():
        # Clear out old values so new values can be created
        PlaylistImportQueue.objects.filter(playlist=playlist).delete()

        # Import each URL
        # TODO: Can this be done in a single SQL statement
        for form in formset:
            if form.cleaned_data.get("url"):
                # Get or create will automatically ignore duplicate URLs
                # If saving manually every URL must be checked if it is unique
                PlaylistImportQueue.objects.get_or_create(url=form.cleaned_data["url"], playlist=playlist)
    else:
        raise Exception("PlaylistQueFormSet is not valid")


def update_form(form: BaseModelFormSet | ModelForm, playlist_id: int) -> HttpResponse:
    """Generic function that validates and saves multiple forms for playlists"""
    if form.is_valid():
        form.save()
    else:
        form_name = type(form)
        raise Exception(f"{form_name} is not valid")

    return HttpResponseRedirect(f"/playlists/{playlist_id}")
