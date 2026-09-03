from django.db import migrations

# Bootstrap Icons "arrow-repeat" — the "here we go again" motif for a suchar
# edited over and over.
ICON_REPEAT = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-arrow-repeat" viewBox="0 0 16 16"><path d="M11.534 7h3.932a.25.25 0 0 1 .192.41l-1.966 2.36a.25.25 0 0 1-.384 0l-1.966-2.36a.25.25 0 0 1 .192-.41m-11 2h3.932a.25.25 0 0 0 .192-.41L2.692 6.23a.25.25 0 0 0-.384 0L.342 8.59A.25.25 0 0 0 .534 9"/><path fill-rule="evenodd" d="M8 3c-1.552 0-2.94.707-3.857 1.818a.5.5 0 1 1-.771-.636A6.002 6.002 0 0 1 13.917 7H12.9A5.002 5.002 0 0 0 8 3M3.1 9a5.002 5.002 0 0 0 8.757 2.182.5.5 0 1 1 .771.636A6.002 6.002 0 0 1 2.083 9z"/></svg>"""  # noqa: E501


def create_recydywa_achievement(apps, schema_editor):
    Achievement = apps.get_model("achievements", "Achievement")

    Achievement.objects.update_or_create(
        slug="recydywa",
        defaults={
            "name": "Recydywa",
            "name_pl": "Recydywa",
            "name_en": "Repeat Offender",
            "description": (
                "Ten sam suchar zapisany z okna edycji pięć razy. Wracasz na"
                " miejsce zbrodni."
            ),
            "description_pl": (
                "Ten sam suchar zapisany z okna edycji pięć razy. Wracasz na"
                " miejsce zbrodni."
            ),
            "description_en": (
                "The same joke saved from the edit window five times over."
                " A return to the scene of the crime."
            ),
            "icon_content": ICON_REPEAT,
            "category": "LIFETIME",
            "event_type": "SUCHAR_EDITED",
            "metric": "EDIT_COUNT",
            # EditCountRule.compute_value reports the highest edit_count among
            # the author's suchary; five saves of one suchar is the bar.
            "threshold": 5,
            "theme": "Ukryte",
            "theme_pl": "Ukryte",
            "theme_en": "Hidden",
            "tier": 0,
            "is_secret": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("achievements", "0018_alter_achievement_event_type_and_more"),
    ]

    operations = [
        migrations.RunPython(
            create_recydywa_achievement,
            migrations.RunPython.noop,
        ),
    ]
