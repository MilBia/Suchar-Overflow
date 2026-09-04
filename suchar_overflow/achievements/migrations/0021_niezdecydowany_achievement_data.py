from django.db import migrations

# Bootstrap Icons "yin-yang" — half light, half dark, forever undecided.
ICON_YIN_YANG = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-yin-yang" viewBox="0 0 16 16"><path d="M9.167 4.5a1.167 1.167 0 1 1-2.334 0 1.167 1.167 0 0 1 2.334 0"/><path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0M1 8a7 7 0 0 1 7-7 3.5 3.5 0 1 1 0 7 3.5 3.5 0 1 0 0 7 7 7 0 0 1-7-7m7 4.667a1.167 1.167 0 1 1 0-2.334 1.167 1.167 0 0 1 0 2.334"/></svg>"""  # noqa: E501


def create_niezdecydowany_achievement(apps, schema_editor):
    Achievement = apps.get_model("achievements", "Achievement")

    Achievement.objects.update_or_create(
        slug="frontend-ee-niezdecydowany",
        defaults={
            "name": "Niezdecydowany",
            "name_pl": "Niezdecydowany",
            "name_en": "Undecided",
            "description": (
                "10 przełączeń motywu w 5 sekund — jasny czy ciemny, w końcu?"
            ),
            "description_pl": (
                "10 przełączeń motywu w 5 sekund — jasny czy ciemny, w końcu?"
            ),
            "description_en": (
                "10 theme toggles in 5 seconds — light or dark, pick one already."
            ),
            "icon_content": ICON_YIN_YANG,
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
        ("achievements", "0020_konami_achievement_data"),
    ]

    operations = [
        migrations.RunPython(
            create_niezdecydowany_achievement,
            migrations.RunPython.noop,
        ),
    ]
