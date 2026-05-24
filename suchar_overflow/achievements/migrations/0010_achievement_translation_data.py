from django.db import migrations
from django.db.models import F

# Polish fixes for achievements whose original `name`/`description` columns
# were seeded in English (migration 0002).
_ENGLISH_SEEDED = {
    "first-suchar": {
        "name_pl": "Pierwszy Suchar",
        "description_pl": "Opublikowałeś/aś swojego pierwszego Suchara!",
        "name_en": "First Suchar",
        "description_en": "Posted your first Suchar!",
    },
    "first-vote": {
        "name_pl": "Pierwszy Głos",
        "description_pl": "Oddałeś/aś swój pierwszy głos!",
        "name_en": "First Vote",
        "description_en": "Cast your first vote!",
    },
    "rising-star": {
        "name_pl": "Wschodzący Talent",
        "description_pl": "Zdobyłeś/aś 5 punktów popularności na wszystkich sucharach!",
        "name_en": "Rising Star",
        "description_en": "Received 5 votes in total!",
    },
    "best-suchar-month": {
        "name_pl": "Komik Miesiąca",
        "description_pl": "Opublikowałeś/aś najwyżej ocenianego Suchara miesiąca!",
        "name_en": "Comedian of the Month",
        "description_en": "Posted the highest rated Suchar of the month!",
    },
    "best-suchar-year": {
        "name_pl": "Legenda Roku",
        "description_pl": "Opublikowałeś/aś najwyżej ocenianego Suchara roku!",
        "name_en": "Legend of the Year",
        "description_en": "Posted the highest rated Suchar of the year!",
    },
}

# English translations for tier-series achievements (slug-prefix → (name_base_en, desc_template_en))
_SERIES_EN = {
    "suchar-creator": (
        "Queen/King of Jokes",
        "Post {} jokes.",
    ),
    "vote-caster": (
        "Dry Joke Connoisseur",
        "Cast {} votes on jokes.",
    ),
    "rising-star-serie": (
        "Star of the Stage",
        "Reach a total popularity score of {} across all your jokes.",
    ),
    "night-owl": (
        "Night Owl",
        "Post {} jokes between midnight and 4 AM.",
    ),
    "streak-login": (
        "Recidivist",
        "Maintain an activity streak of {} consecutive days.",
    ),
    "vote-dry-koneser": (
        "Dry Voter",
        "Cast {} dry votes over the course of your career.",
    ),
    "polarizer-master": (
        "Polarizer",
        "Polarize the community perfectly with {} balanced votes.",
    ),
}

# Polish tier label → English tier label (slugs use the Polish labels)
_TIER_SUFFIX_EN = {
    "brąz": "Bronze",
    "srebro": "Silver",
    "złoto": "Gold",
    "platyna": "Platinum",
    "diament": "Diamond",
}

# English translations for frontend (hidden) achievements
_FRONTEND_EN = {
    "frontend-recenzent-totalny": {
        "name_en": "Total Reviewer",
        "description_en": (
            "Those who read slowly laugh longest — you paused on 20 jokes for more than 3 seconds."
        ),
    },
    "frontend-stluczona-mysz": {
        "name_en": "Broken Mouse",
        "description_en": "You clicked the same vote button five times. Your mouse is betraying you.",
    },
    "frontend-zbieracz-sucharow": {
        "name_en": "Joke Collector",
        "description_en": (
            "You browsed 5 pages of jokes without doing anything. Just gathering material?"
        ),
    },
    "frontend-niecierpliwy": {
        "name_en": "Impatient",
        "description_en": (
            "You tried to post a joke shorter than 10 characters three times. Focus is key!"
        ),
    },
    "frontend-odkrywca": {
        "name_en": "Explorer",
        "description_en": "You visited the achievements page 5 times. Someone is curious...",
    },
}

# Theme label translations (Polish → English)
_THEME_EN = {
    "Twórca": "Creator",
    "Aktywista": "Activist",
    "Rozgłos": "Fame",
    "Nocny Marek": "Night Owl",
    "Streaki": "Streaks",
    "Susza": "Dry Spell",
    "Kontrowersja": "Controversy",
    "Ukryte": "Hidden",
}


def populate_translation_fields(apps, schema_editor):
    Achievement = apps.get_model("achievements", "Achievement")

    # Step 1: Copy existing `name`/`description`/`theme` to the _pl columns.
    # All rows seeded by 0006/0008 already contain Polish text.
    Achievement.objects.update(
        name_pl=F("name"),
        description_pl=F("description"),
        theme_pl=F("theme"),
    )

    # Step 2: Fix Polish values + add English for achievements seeded in English (0002).
    for slug, translations in _ENGLISH_SEEDED.items():
        Achievement.objects.filter(slug=slug).update(**translations)

    # Step 3: Add English translations for tier-series achievements (0006).
    for prefix, (name_en_base, desc_en_tpl) in _SERIES_EN.items():
        for pl_suffix, en_suffix in _TIER_SUFFIX_EN.items():
            slug = f"{prefix}-{pl_suffix}"
            ach = Achievement.objects.filter(slug=slug).values("threshold").first()
            if ach is None:
                continue
            Achievement.objects.filter(slug=slug).update(
                name_en=f"{name_en_base} ({en_suffix})",
                description_en=desc_en_tpl.format(ach["threshold"]),
            )

    # Step 4: Add English translations for frontend achievements (0008).
    for slug, translations in _FRONTEND_EN.items():
        Achievement.objects.filter(slug=slug).update(**translations)

    # Step 5: Populate theme_en for all achievements by their Polish theme value.
    for pl_theme, en_theme in _THEME_EN.items():
        Achievement.objects.filter(theme=pl_theme).update(theme_en=en_theme)


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0009_achievement_description_en_and_more"),
    ]

    operations = [
        migrations.RunPython(populate_translation_fields, migrations.RunPython.noop),
    ]
