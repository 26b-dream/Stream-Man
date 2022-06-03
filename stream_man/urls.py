"""stream_man URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
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
from django.contrib import admin
from django.urls import include, path

# Shows
from shows import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("playlists/", include("playlists.urls")),
    path("shows/", include("shows.urls.shows")),
    path("seasons/", include("shows.urls.seasons")),
    path("episodes/", include("shows.urls.episodes")),
    path("admin/shows/show/<int:show_id>/change/", views.show, name="admin_show"),
    path("admin/shows/season/<int:show_id>/change/", views.show, name="admin_season"),
    path("admin/shows/episode/<int:show_id>/change/", views.show, name="admin_episode"),
]
