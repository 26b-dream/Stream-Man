# Generated by Django 4.0.3 on 2022-05-10 05:35

# Standard Library
import datetime

# Django
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shows", "0016_alter_show_update_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="show",
            name="update_at",
            field=models.DateTimeField(default=datetime.datetime(1, 1, 1, 0, 0)),
        ),
    ]
