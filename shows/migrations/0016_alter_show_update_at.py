# Generated by Django 4.0.3 on 2022-05-10 05:31

# Standard Library
import datetime

# Django
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shows", "0015_show_update_at_alter_episode_release_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="show",
            name="update_at",
            field=models.DateTimeField(default=datetime.datetime(1969, 12, 31, 16, 0)),
        ),
    ]
