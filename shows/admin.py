from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, Any
# Standard Library
from urllib.request import Request

# Django
from django.contrib import admin
from django.db.models.query import QuerySet
from django.urls import reverse
from django.utils.html import format_html

# Local
from .models import Episode, EpisodeWatch, Season, Show


class EpisodeWatchInline(admin.TabularInline):  # type: ignore - This follows Django's documentation perfectly
    model = EpisodeWatch


class FitlerTest(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = "cross reference status"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "cross_ref_check"

    def lookups(self, request: Request, model_admin: Any) -> list[tuple[Any, str]]:
        return [
            ("completed_season", ("Completed Season")),
            ("completed_episode", ("Completed Episode")),
        ]

    def queryset(self, request: Request, queryset: QuerySet[Episode]) -> Optional[QuerySet[Episode]]:
        if self.value() == "completed_season":
            return (
                queryset.filter(cross_referenced=False, episodewatch__isnull=False)
                .exclude(season__episode__episodewatch__isnull=True)
                .distinct()
            )
        elif self.value() == "completed_episode":
            return queryset.filter(cross_referenced=False, episodewatch__isnull=False)


class EpisodeAdmin(admin.ModelAdmin):  # type: ignore - This follows Django's documentation perfectly
    inlines = [
        EpisodeWatchInline,
    ]
    list_filter = ("cross_referenced", FitlerTest)

    def season_link(self, episode: Episode):
        season = episode.season
        url = reverse("admin_show", args=[season.id])
        return format_html(f"<a href='{url}'>{season.name}</a>", url, season.name)

    def show_link(self, episode: Episode):
        show = episode.season.show
        url = reverse("admin_show", args=[show.id])
        return format_html(f"<a href='{url}'>{show.name}</a>", url, show.name)

    list_display = ["show_link", "season_link", "number", "name", "cross_referenced"]
    list_display_links = ["name"]
    search_fields = ["name", "number", "season__name", "season__show__name"]
    list_editable = ["cross_referenced"]


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
