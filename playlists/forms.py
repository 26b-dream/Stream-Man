from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional


# Django
from django import forms

# Common
from common.scrapers import SHOW_SUBCLASSES

# Local
from .builder import Builder
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

    show_order = grouped_choice_field(
        choices=Builder.ShowOrder.acceptable_functions,
        widget=forms.RadioSelect,
        initial="random",
        required=False,
    )
    show_order.group = 0
    show_order.group_title = "Show Order"

    episode_order = grouped_choice_field(
        choices=Builder.EpisodeOrder.acceptable_functions,
        widget=forms.RadioSelect,
        initial="chronological",
        required=False,
    )
    episode_order.group = 1
    episode_order.group_title = "Episode Order"

    change_show = grouped_choice_field(
        choices=Builder.ChangeShowIf.acceptable_functions,
        widget=forms.RadioSelect,
        initial="after_every_episode",
        required=False,
    )
    change_show.group = 2
    change_show.group_title = "Change Show"

    rotate_type = grouped_choice_field(
        choices=Builder.Resort.acceptable_functions,
        widget=forms.RadioSelect,
        required=False,
        initial="rotate",
    )
    rotate_type.group = 3
    rotate_type.group_title = "Rotate Type"

    FILTER_OPTIONS = (
        ("include_watched", "Include Watched"),
        ("only_started_shows", "Only Started Shows"),
        ("only_new_shows", "Only New Shows"),
    )
    REVERSE_OPTIONS = (
        ("shows", "Shows"),
        ("episodes", "Episodes"),
    )
    reverse = grouped_multiple_choice_field(
        choices=REVERSE_OPTIONS, widget=forms.CheckboxSelectMultiple, required=False
    )
    reverse.group = 4
    reverse.group_title = "Reverse"

    websites = grouped_multiple_choice_field(
        choices=[(x.WEBSITE, x.WEBSITE) for x in SHOW_SUBCLASSES.values()],
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    websites.group = 5
    websites.group_title = "Wesbites"

    episode_filter = grouped_multiple_choice_field(
        choices=FILTER_OPTIONS, widget=forms.CheckboxSelectMultiple, required=False
    )
    episode_filter.group = 6
    episode_filter.group_title = "Filter"

    number_of_episodes = grouped_integer_field(initial=100)
    number_of_episodes.group = 7
    number_of_episodes.group_title = "Number of Episodes"

    # Group specific fields together so the form is easier to use
