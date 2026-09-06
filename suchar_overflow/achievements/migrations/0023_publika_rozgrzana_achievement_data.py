from django.db import migrations

# Bootstrap Icons "fire" — the crowd is warmed up and roaring.
ICON_FIRE = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-fire" viewBox="0 0 16 16"><path d="M8 16c3.314 0 6-2 6-5.5 0-1.5-.5-4-2.5-6 .25 1.5-1.25 2-1.25 2C11 4 9 .5 6 0c.357 2 .5 4-2 6-1.25 1-2 2.729-2 4.5C2 14 4.686 16 8 16m0-1c-1.657 0-3-1-3-2.75 0-.75.25-2 1.25-3C6.125 10 7 10.5 7 10.5c-.375-1.25.5-3.25 2-3.5-.179 1-.25 2 1 3 .625.5 1 1.364 1 2.25C11 14 9.657 15 8 15"/></svg>"""  # noqa: E501


def create_publika_rozgrzana_achievement(apps, schema_editor):
    Achievement = apps.get_model("achievements", "Achievement")

    Achievement.objects.update_or_create(
        slug="frontend-ee-publika-rozgrzana",
        defaults={
            "name": "Publika Rozgrzana",
            "name_pl": "Publika Rozgrzana",
            "name_en": "Warmed-Up Crowd",
            "description": (
                "10 głosów „śmieszne” pod rząd w 60 sekund — publika rozgrzana."
            ),
            "description_pl": (
                "10 głosów „śmieszne” pod rząd w 60 sekund — publika rozgrzana."
            ),
            "description_en": (
                "10 funny votes in a row within 60 seconds — the crowd is warmed up."
            ),
            "icon_content": ICON_FIRE,
            "category": "LIFETIME",
            "event_type": "FRONTEND",
            "metric": "FRONTEND_EVENT",
            "threshold": 1,
            "theme": "Ukryte",
            "theme_pl": "Ukryte",
            "theme_en": "Hidden",
            "tier": 0,
            "is_secret": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("achievements", "0022_archeolog_achievement_data"),
    ]

    operations = [
        migrations.RunPython(
            create_publika_rozgrzana_achievement,
            migrations.RunPython.noop,
        ),
    ]
