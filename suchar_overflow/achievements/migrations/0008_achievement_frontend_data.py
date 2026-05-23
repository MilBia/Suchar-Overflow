from django.db import migrations

ICON_EYE = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-eye-fill" viewBox="0 0 16 16"><path d="M10.5 8a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z"/><path d="M0 8s3-5.5 8-5.5S16 8 16 8s-3 5.5-8 5.5S0 8 0 8zm8 3.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/></svg>"""  # noqa: E501
ICON_MOUSE = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-mouse2-fill" viewBox="0 0 16 16"><path d="M3 5.188C3 2.341 5.22 0 8 0s5 2.342 5 5.188V8H3zM1 9h14v2.5c0 2.485-2.317 4.5-5.063 4.5H6.063C3.317 16 1 13.986 1 11.5z"/></svg>"""  # noqa: E501
ICON_STACK = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-stack" viewBox="0 0 16 16"><path d="m14.12 10.163 1.715.858c.22.11.22.424 0 .534L8.267 15.34a.6.6 0 0 1-.534 0L.165 11.555a.299.299 0 0 1 0-.534l1.716-.858 5.317 2.659c.505.252 1.1.252 1.604 0l5.317-2.66zm0-4.427 1.715.858c.22.11.22.424 0 .534l-7.568 3.784a.6.6 0 0 1-.534 0L.165 7.128a.299.299 0 0 1 0-.534l1.716-.858 5.317 2.659c.505.252 1.1.252 1.604 0l5.317-2.659zm-7.733-4.550 7.568 3.784a.299.299 0 0 1 0 .534L6.388 9.29a.6.6 0 0 1-.534 0L.165 5.504a.299.299 0 0 1 0-.534l7.568-3.783a.6.6 0 0 1 .534 0z"/></svg>"""  # noqa: E501
ICON_HOURGLASS = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-hourglass-split" viewBox="0 0 16 16"><path d="M2.5 15a.5.5 0 1 1 0-1h1v-1a4.5 4.5 0 0 1 2.557-4.06c.29-.139.443-.377.443-.59v-.7c0-.213-.154-.451-.443-.59A4.5 4.5 0 0 1 3.5 3V2h-1a.5.5 0 0 1 0-1h11a.5.5 0 0 1 0 1h-1v1a4.5 4.5 0 0 1-2.557 4.06c-.29.139-.443.377-.443.59v.7c0 .213.154.451.443.59A4.5 4.5 0 0 1 12.5 13v1h1a.5.5 0 0 1 0 1h-11zm2-13v1c0 .537.12 1.045.337 1.5h6.326c.216-.455.337-.963.337-1.5V2h-7zm3 6.35c0 .701-.478 1.236-1.011 1.492A3.5 3.5 0 0 0 4.5 13s.866-1.299 3-1.48V8.35zm1 0v3.17c2.134.181 3 1.48 3 1.48a3.5 3.5 0 0 0-1.989-3.158C8.978 9.586 8.5 9.052 8.5 8.351z"/></svg>"""  # noqa: E501
ICON_COMPASS = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-compass-fill" viewBox="0 0 16 16"><path d="M15.5 8.516a7.5 7.5 0 1 1-9.462-7.24A1 1 0 0 1 7 0h2a1 1 0 0 1 .962 1.276 7.503 7.503 0 0 1 5.538 7.24zm-3.61-3.905L6.94 7.439 4.11 11.39l4.95-2.828 2.828-3.951z"/></svg>"""  # noqa: E501

_ACHIEVEMENTS = [
    {
        "slug": "frontend-recenzent-totalny",
        "name": "Recenzent Totalny",
        "description": (
            "Kto czyta powoli, śmieje się długo — zatrzymałeś/aś się"
            " przy 20 sucharach dłużej niż 3 sekundy."
        ),
        "icon_content": ICON_EYE,
    },
    {
        "slug": "frontend-stluczona-mysz",
        "name": "Stłuczona Mysz",
        "description": "Kliknąłeś/aś ten sam przycisk głosowania pięć razy. Mysz Ci nie służy.",
        "icon_content": ICON_MOUSE,
    },
    {
        "slug": "frontend-zbieracz-sucharow",
        "name": "Zbieracz Sucharów",
        "description": (
            "Przewertowałeś/aś 5 stron sucharów niczego nie robiąc."
            " Czyżbyś tylko zbierał/a materiały?"
        ),
        "icon_content": ICON_STACK,
    },
    {
        "slug": "frontend-niecierpliwy",
        "name": "Niecierpliwy",
        "description": (
            "Trzykrotnie próbowałeś/aś wrzucić suchar krótszy niż 10 znaków."
            " Skupienie to klucz!"
        ),
        "icon_content": ICON_HOURGLASS,
    },
    {
        "slug": "frontend-odkrywca",
        "name": "Odkrywca",
        "description": "Odwiedziłeś/aś stronę osiągnięć 5 razy. Ktoś jest ciekawy...",
        "icon_content": ICON_COMPASS,
    },
]


def create_frontend_achievements(apps, schema_editor):
    Achievement = apps.get_model("achievements", "Achievement")

    for ach in _ACHIEVEMENTS:
        Achievement.objects.update_or_create(
            slug=ach["slug"],
            defaults={
                "name": ach["name"],
                "description": ach["description"],
                "icon_content": ach["icon_content"],
                "category": "LIFETIME",
                "event_type": "FRONTEND",
                "metric": "FRONTEND_EVENT",
                "threshold": 1,
                "theme": "Ukryte",
                "tier": 0,
                "is_secret": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0007_achievement_frontend_choices"),
    ]

    operations = [
        migrations.RunPython(create_frontend_achievements, migrations.RunPython.noop),
    ]
