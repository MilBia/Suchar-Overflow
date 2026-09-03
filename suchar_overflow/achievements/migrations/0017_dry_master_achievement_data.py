from django.db import migrations

# Bootstrap Icons "droplet-half" — the same "dryness" motif the Grzybiarz /
# "Susza" series already uses for dry votes.
ICON_DROP = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-droplet-half" viewBox="0 0 16 16"><path fill-rule="evenodd" d="M7.21.8C7.69.295 8 0 8 0c.109.363.234.708.371 1.038.812 1.946 2.073 3.35 3.197 4.6C12.878 7.096 14 8.345 14 10a6 6 0 0 1-12 0C2 6.668 5.58 2.517 7.21.8zm.413 1.021A31.259 31.259 0 0 0 5.794 3.99c-1.573 2.046-3.792 5.353-3.792 6.01a5.992 5.992 0 0 0 4 5.657z"/></svg>"""  # noqa: E501


def create_dry_master_achievement(apps, schema_editor):
    Achievement = apps.get_model("achievements", "Achievement")

    Achievement.objects.update_or_create(
        slug="dry-master",
        defaults={
            "name": "Mistrz Suszu",
            "name_pl": "Mistrz Suszu",
            "name_en": "Master of Dryness",
            "description": (
                "W godzinę od publikacji Twój suchar zebrał 10 głosów „suchar”"
                " i ani jednego „śmieszne”. Mistrzostwo w swoim gatunku."
            ),
            "description_pl": (
                "W godzinę od publikacji Twój suchar zebrał 10 głosów „suchar”"
                " i ani jednego „śmieszne”. Mistrzostwo w swoim gatunku."
            ),
            "description_en": (
                "Within an hour of going live, your joke pulled ten „dry”"
                " votes and not one „funny”. A masterclass, of sorts."
            ),
            "icon_content": ICON_DROP,
            "category": "LIFETIME",
            "event_type": "VOTE_RECEIVED",
            "metric": "DRY_MASTER",
            # DryMasterRule.compute_value counts the author's latched
            # ("is_overdried") suchary; the "10 dry / 0 funny / within 1h"
            # test lives in the vote signal, so one latched suchar is enough.
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
        ("achievements", "0016_alter_achievement_metric"),
    ]

    operations = [
        migrations.RunPython(
            create_dry_master_achievement,
            migrations.RunPython.noop,
        ),
    ]
