from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional


# Django
from django import forms

# Common
from common.scrapers import SHOW_SUBCLASSES

# Local
from .models import Playlist, PlaylistSeason, PlaylistShow


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


class group_mixin:
    group: Optional[int]
    group_title: Optional[str]


class grouped_choice_field(forms.ChoiceField, group_mixin):
    """Modified version of ChoiceField that allows for grouping choices"""


class grouped_multiple_choice_field(forms.MultipleChoiceField, group_mixin):
    """Modified version of MultipleChoiceField that allows for grouping choices"""


class grouped_integer_field(forms.IntegerField, group_mixin):
    """Modified version of IntegerField that allows for grouping choices"""


class PlaylistSortForm(forms.Form):
    """Form used to sort and filter playlists"""

    # TODO: Consider making this form more dynamic and havign every buiolder option as an option allowing easier mixing and matching
    # TODO: So finish_up_straight and finish_up_mixed could just be created on demand using toggles or something
    PLAYLIST_SORT_OPTIONS = [
        ("normal", "Normal"),
        ("random", "Random"),
        ("newest", "Newest First"),
        ("smart_newest_straight", "Smart Newest Straight"),
        ("smart_newest_mixed", "Smart Newest Mixed"),
        ("least_recently_watched", "Least Recently Watched"),
        ("finish_up_straight", "Finish Up Straight"),
        ("finish_up_mixed", "Finish Up Mixed"),
    ]
    FILTER_OPTIONS = (
        ("include_watched", "Include Watched"),
        ("only_started_shows", "Only Started Shows"),
        ("only_new_shows", "Only New Shows"),
    )
    REVERSE_OPTIONS = (("reverse", "Reverse"),)

    order = grouped_choice_field(
        choices=PLAYLIST_SORT_OPTIONS,
        widget=forms.RadioSelect,
        initial="normal",
        required=False,
    )

    # It seems dumb to have this as a multiple choice when there is only one option
    # Djang just formats text prettier when using MultipleChoiceField with CheckboxSelectMultiple
    # So multiple choice is used just to improve user experience even if it seems illoigcal
    reverse = grouped_multiple_choice_field(
        choices=REVERSE_OPTIONS, widget=forms.CheckboxSelectMultiple, required=False
    )

    episode_filter = grouped_multiple_choice_field(
        choices=FILTER_OPTIONS, widget=forms.CheckboxSelectMultiple, required=False
    )
    websites = grouped_multiple_choice_field(
        choices=[(x.WEBSITE, x.WEBSITE) for x in SHOW_SUBCLASSES.values()],
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    number_of_episodes = grouped_integer_field(initial=100)

    # Group specific fields together so the form is easier to use
    order.group = reverse.group = 1
    order.group_title = reverse.group_title = "Order"
    episode_filter.group = 2
    episode_filter.group_title = "Filter"
    websites.group = 3
    websites.group_title = "Wesbites"
    number_of_episodes.group = 4
    number_of_episodes.group_title = "Number of Episodes"
