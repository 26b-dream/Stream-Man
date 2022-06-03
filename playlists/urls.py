"""stream_man URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# Django
from django.urls import path

# Local
from .views import modal, post, views

app_name = "playlists"
urlpatterns = [
    path("", views.index, name="index"),
    path(
        "post_new_playlist_form/",
        post.new_playlist_form,
        name="post_new_playlist_form",
    ),
    path("modal_new_playlist/", modal.new_playlist, name="modal_new_playlist"),
    path("<int:playlist_id>/modal_add_show/", modal.add_show, name="modal_add_show"),
    path(
        "<int:playlist_id>/modal_remove_show/",
        modal.remove_show,
        name="modal_remove_show",
    ),
    path(
        "<int:playlist_id>/modal_hide_season/",
        modal.hide_season,
        name="modal_hide_season",
    ),
    path(
        "<int:playlist_id>/modal_filter_episodes/",
        modal.filter_episodes,
        name="modal_filter_episodes",
    ),
    path("<int:playlist_id>/", views.playlist, name="playlist"),
    path("<int:playlist_id>/shows", views.playlist_shows, name="playlist_shows"),
    path(
        "<int:playlist_id>/post_playlist_que_formset/",
        post.playlist_que_formset,
        name="post_playlist_que_formset",
    ),
    path(
        "<int:playlist_id>/post_remove_show_formset/",
        post.remove_show_formset,
        name="post_remove_show_formset",
    ),
    path(
        "<int:playlist_id>/post_hide_season_formset/",
        post.hide_season_formset,
        name="post_hide_season_formset",
    ),
    path(
        "<int:playlist_id>/post_rename_playlist_form/",
        post.rename_playlist_form,
        name="post_rename_playlist_form",
    ),
    path(
        "<int:playlist_id>/post_update_shows/",
        post.update_shows,
        name="post_update_shows",
    ),
]
