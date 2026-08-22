from django.db import migrations

# Bootstrap Icons "arrow-left-right" — symbolizes a tie between two winners.
ICON_TIE = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-arrow-left-right" viewBox="0 0 16 16"><path fill-rule="evenodd" d="M1 11.5a.5.5 0 0 0 .5.5h11.793l-3.147 3.146a.5.5 0 0 0 .708.708l4-4a.5.5 0 0 0 0-.708l-4-4a.5.5 0 0 0-.708.708L13.293 11H1.5a.5.5 0 0 0-.5.5zm14-7a.5.5 0 0 1-.5.5H2.707l3.147 3.146a.5.5 0 1 1-.708.708l-4-4a.5.5 0 0 1 0-.708l4-4a.5.5 0 1 1 .708.708L2.707 4H14.5a.5.5 0 0 1 .5.5z"/></svg>"""  # noqa: E501

_TIE_ACHIEVEMENTS = [
    {
        "slug": "best-suchar-month-tie",
        "name_pl": "Remis Miesiąca",
        "description_pl": (
            "Twój suchar zremisował z innym na szczycie miesiąca —"
            " chwała dzielona po równo."
        ),
        "name_en": "Tie of the Month",
        "description_en": (
            "Your joke tied with another for the top spot this month —"
            " glory shared equally."
        ),
    },
    {
        "slug": "best-suchar-year-tie",
        "name_pl": "Remis Roku",
        "description_pl": (
            "Twój suchar zremisował z innym na szczycie roku —"
            " chwała dzielona po równo."
        ),
        "name_en": "Tie of the Year",
        "description_en": (
            "Your joke tied with another for the top spot this year —"
            " glory shared equally."
        ),
    },
]


def create_tie_achievements(apps, schema_editor):
    Achievement = apps.get_model("achievements", "Achievement")

    for ach in _TIE_ACHIEVEMENTS:
        Achievement.objects.update_or_create(
            slug=ach["slug"],
            defaults={
                "name": ach["name_pl"],
                "name_pl": ach["name_pl"],
                "name_en": ach["name_en"],
                "description": ach["description_pl"],
                "description_pl": ach["description_pl"],
                "description_en": ach["description_en"],
                "icon_content": ICON_TIE,
                "category": "PERIODIC",
                "event_type": "SUCHAR_POSTED",
                "metric": "SUM_SCORE",
                "threshold": 0,
                "theme": "Ukryte",
                "theme_pl": "Ukryte",
                "theme_en": "Hidden",
                "tier": 0,
                "is_secret": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("achievements", "0013_alter_schedulerrun_options"),
    ]

    operations = [
        migrations.RunPython(create_tie_achievements, migrations.RunPython.noop),
    ]
