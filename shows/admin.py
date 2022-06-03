from __future__ import annotations

# Django
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

# Local
from .models import Episode, EpisodeWatch, Season, Show


class EpisodeWatchInline(admin.TabularInline):  # type: ignore - This follows Django's documentation perfectly
    model = EpisodeWatch


class EpisodeAdmin(admin.ModelAdmin):  # type: ignore - This follows Django's documentation perfectly
    inlines = [
        EpisodeWatchInline,
    ]

    def season_link(self, episode: Episode):
        season = episode.season
        url = reverse("admin_show", args=[season.id])
        return format_html(f"<a href='{url}'>{episode.name}</a>", url, season.name)

    def show_link(self, episode: Episode):
        show = episode.season.show
        url = reverse("admin_show", args=[show.id])
        return format_html(f"<a href='{url}'>{episode.name}</a>", url, show.name)

    list_display = ["show_link", "season_link", "number", "name"]
    list_display_links = ["name"]
    search_fields = ["name", "number", "season__name", "season__show__name"]


class ShowSeasonInline(admin.TabularInline):  # type: ignore - This follows Django's documentation perfectly
    model = Season
    fields = ("name",)
    readonly_fields = ("name",)
    show_change_link = True
    extra = 0


class SeasonSeasonInline(admin.TabularInline):  # type: ignore - This follows Django's documentation perfectly
    model = Episode
    fields = ("number", "name", "release_date")
    readonly_fields = ("number", "name", "release_date")
    show_change_link = True
    extra = 0


class SeasonAdmin(admin.ModelAdmin):  # type: ignore - This follows Django's documentation perfectly
    inlines = [SeasonSeasonInline]
    list_display = ["name", "number", "show"]


class ShowAdmin(admin.ModelAdmin):  # type: ignore - This follows Django's documentation perfectly
    inlines = [ShowSeasonInline]
    list_display = ["name", "website"]


admin.site.register(Episode, EpisodeAdmin)
admin.site.register(EpisodeWatch)
admin.site.register(Season, SeasonAdmin)
admin.site.register(Show, ShowAdmin)
