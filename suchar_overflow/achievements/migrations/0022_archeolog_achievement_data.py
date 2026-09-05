from django.db import migrations

# Bootstrap Icons "archive-fill" — digging through a box of old suchary.
ICON_ARCHIVE = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-archive-fill" viewBox="0 0 16 16"><path d="M12.643 15C13.979 15 15 13.845 15 12.5V5H1v7.5C1 13.845 2.021 15 3.357 15zM5.5 7h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1 0-1M.8 1a.8.8 0 0 0-.8.8V3a.8.8 0 0 0 .8.8h14.4A.8.8 0 0 0 16 3V1.8a.8.8 0 0 0-.8-.8z"/></svg>"""  # noqa: E501


def create_archeolog_achievement(apps, schema_editor):
    Achievement = apps.get_model("achievements", "Achievement")

    Achievement.objects.update_or_create(
        slug="frontend-ee-archeolog",
        defaults={
            "name": "Archeolog",
            "name_pl": "Archeolog",
            "name_en": "Archaeologist",
            "description": (
                "Dotarłeś przewijaniem do dna ostatniej z co najmniej pięciu "
                "stron sucharów."
            ),
            "description_pl": (
                "Dotarłeś przewijaniem do dna ostatniej z co najmniej pięciu "
                "stron sucharów."
            ),
            "description_en": (
                "Scrolled all the way to the bottom of the last of at least "
                "five pages of suchary."
            ),
            "icon_content": ICON_ARCHIVE,
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
        ("achievements", "0021_niezdecydowany_achievement_data"),
    ]

    operations = [
        migrations.RunPython(
            create_archeolog_achievement,
            migrations.RunPython.noop,
        ),
    ]
