from __future__ import annotations

# Django
from django.contrib import admin

# Local
from .models import Playlist, PlaylistImportQueue, PlaylistSeason, PlaylistShow

admin.site.register(Playlist)
admin.site.register(PlaylistImportQueue)
admin.site.register(PlaylistSeason)
admin.site.register(PlaylistShow)
