# Generated by Django 4.2.7 on 2025-06-03 20:26

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "ensure_profiles"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="avatar",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="google_id",
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
    ]
