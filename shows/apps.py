from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Django
from django.apps import AppConfig


class ShowsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shows"
