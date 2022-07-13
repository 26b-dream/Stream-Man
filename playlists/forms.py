from __future__ import annotations

# Django
from django import forms
from django.utils.safestring import mark_safe

# Local
from .builder import Builder
from .models import Playlist, PlaylistSeason, PlaylistShow

# Plugins
from plugins.streaming import SHOW_SUBCLASSES


# Don't use a model form set because it makes it harder to manage empty strngs in the form
#   Model form set's require a seperate value for deleting entries
#   A regular formset makes it easier to manage empty strings because they can just be ignored
class PlaylistQueForm(forms.Form):
    """Form used to add shows to a playlist"""

    url = forms.CharField(required=False)


# Only allow adding 10 shows at once
#   Keeps the form from looking messy
#   Forces the user to save often so they won't lose their work
PlaylistQueFormSet = forms.formsets.formset_factory(PlaylistQueForm, extra=10)


class PlaylistHideSeasonForm(forms.ModelForm):
    """Form used to hide seasons from a playlist"""

    class Meta:  # type: ignore - class Meta always throws errors
        model = PlaylistSeason
        fields = ["season", "skip"]
        widgets = {"season": forms.widgets.HiddenInput()}


PlaylistHideSeasonFormSet = forms.models.modelformset_factory(PlaylistSeason, form=PlaylistHideSeasonForm, extra=0)


class PlaylistnewForm(forms.ModelForm):
    """Form used to create a new playlist"""

    class Meta:  # type: ignore - class Meta always throws errors
        model = Playlist
        fields = ["name"]


class PlaylistRemoveShowForm(forms.ModelForm):
    """Form used to remove a show from a playlist"""

    class Meta:  # type: ignore - class Meta always throws errors
        model = PlaylistShow
        fields = ["show"]
        widgets = {"show": forms.widgets.HiddenInput()}


PlaylistRemoveShowFormSet = forms.models.modelformset_factory(
    PlaylistShow, form=PlaylistRemoveShowForm, can_delete=True, extra=0
)


class PlaylistRenameForm(forms.ModelForm):
    """Form to rename a playlist"""

    class Meta:  # type: ignore - class Meta always throws errors
        model = Playlist
        fields = ["name"]


class PlaylistSortForm(forms.Form):
    """Form used to sort and filter playlists"""

    show_order = forms.ChoiceField(
        choices=Builder.ShowOrder.acceptable_functions,
        widget=forms.RadioSelect,
        initial="random",
        required=False,
    )

    episode_order = forms.ChoiceField(
        choices=Builder.EpisodeOrder.acceptable_functions,
        widget=forms.RadioSelect,
        initial="chronological",
        required=False,
    )

    change_show = forms.ChoiceField(
        choices=Builder.ChangeShowIf.acceptable_functions,
        widget=forms.RadioSelect,
        initial="after_every_episode",
        required=False,
    )

    rotate_type = forms.ChoiceField(
        choices=Builder.Resort.acceptable_functions,
        widget=forms.RadioSelect,
        required=False,
        initial="rotate",
    )

    FILTER_OPTIONS = (
        ("include_watched", "Include Watched"),
        ("only_started_shows", "Only Started Shows"),
        ("only_new_shows", "Only New Shows"),
    )
    REVERSE_OPTIONS = (
        ("shows", "Shows"),
        ("episodes", "Episodes"),
    )
    reverse = forms.MultipleChoiceField(choices=REVERSE_OPTIONS, widget=forms.CheckboxSelectMultiple, required=False)

    websites = forms.MultipleChoiceField(
        choices=[
            (x.WEBSITE, mark_safe(f"<img src={x.FAVICON_URL} style='width:16px;height:16px;'> {x.WEBSITE}"))
            for x in SHOW_SUBCLASSES.values()
        ],
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    episode_filter = forms.MultipleChoiceField(
        choices=FILTER_OPTIONS, widget=forms.CheckboxSelectMultiple, required=False
    )

    number_of_episodes = forms.IntegerField(initial=100)

    # Group specific fields together so the form is easier to use
