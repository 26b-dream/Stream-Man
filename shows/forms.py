from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Django
from django import forms

# Local
from .models import EpisodeWatch


class EpisodeWatchForm(forms.ModelForm):
    class Meta:  # type: ignore - class Meta always throws errors
        model = EpisodeWatch
        fields = ["episode", "watch_date"]
        widgets = {
            "episode": forms.widgets.HiddenInput(),
            "watch_date": forms.widgets.DateInput(attrs={"type": "date"}),
        }
