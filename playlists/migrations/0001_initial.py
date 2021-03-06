# Generated by Django 4.0 on 2022-01-01 02:58

# Django
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("shows", "0002_alter_episode_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Playlist",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=64, unique=True)),
            ],
            options={
                "db_table": "playlist",
            },
        ),
        migrations.CreateModel(
            name="PlaylistShow",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "playlist",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="playlists.playlist",
                    ),
                ),
                (
                    "show",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="shows.show"),
                ),
            ],
            options={
                "db_table": "playlist_show",
            },
        ),
        migrations.CreateModel(
            name="PlaylistSeasonSkip",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "playlist_show",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="playlists.playlistshow",
                    ),
                ),
                (
                    "season",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="shows.season"),
                ),
            ],
            options={
                "db_table": "playlist_season_skip",
            },
        ),
        migrations.CreateModel(
            name="PlaylistImportQue",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("url", models.CharField(max_length=256)),
                (
                    "playlist",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="playlists.playlist",
                    ),
                ),
            ],
            options={
                "db_table": "playlist_que",
            },
        ),
        migrations.AddField(
            model_name="playlist",
            name="shows",
            field=models.ManyToManyField(through="playlists.PlaylistShow", to="shows.Show"),
        ),
        migrations.AddConstraint(
            model_name="playlistshow",
            constraint=models.UniqueConstraint(fields=("playlist_id", "show_id"), name="playlist_id show_id"),
        ),
        migrations.AddConstraint(
            model_name="playlistseasonskip",
            constraint=models.UniqueConstraint(fields=("playlist_show", "season_id"), name="playlist_show season_id"),
        ),
        migrations.AddConstraint(
            model_name="playlistimportque",
            constraint=models.UniqueConstraint(fields=("playlist", "url"), name="playlist url"),
        ),
    ]
