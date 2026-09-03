"""The "Kod Konami" hidden achievement — data migration 0020 (#283).

Pure data check: the migration's ``create_konami_achievement`` must seed one
hidden ``FRONTEND`` / ``FRONTEND_EVENT`` achievement with both the pl and en
translation columns populated (django-modeltranslation).

The migration function is invoked directly rather than relying on the
migration-seeded row surviving in the test DB — ``transaction=True`` tests
truncate baseline data and ``--reuse-db`` never re-runs ``RunPython`` (see
CLAUDE.md "Migration-seeded achievements"). The award path itself is covered in
``test_api.py`` (``POST /api/achievements/frontend-event``).
"""

import importlib

import pytest
from django.apps import apps as global_apps

from suchar_overflow.achievements.models import Achievement

KONAMI_SLUG = "frontend-ee-konami"

_migration = importlib.import_module(
    "suchar_overflow.achievements.migrations.0020_konami_achievement_data",
)


@pytest.fixture
def _seed_konami() -> None:
    Achievement.objects.filter(slug=KONAMI_SLUG).delete()
    _migration.create_konami_achievement(global_apps, None)


@pytest.mark.django_db
@pytest.mark.usefixtures("_seed_konami")
def test_migration_seeds_a_hidden_frontend_achievement() -> None:
    ach = Achievement.objects.get(slug=KONAMI_SLUG)

    assert ach.event_type == Achievement.EventType.FRONTEND
    assert ach.metric == Achievement.Metric.FRONTEND_EVENT
    assert ach.category == Achievement.Category.LIFETIME
    assert ach.threshold == 1
    assert ach.tier == Achievement.Tier.NONE
    assert ach.is_secret is True
    assert ach.icon_content.startswith("<svg")


@pytest.mark.django_db
@pytest.mark.usefixtures("_seed_konami")
def test_migration_populates_pl_and_en_translations() -> None:
    # django-modeltranslation's `*_pl` / `*_en` columns aren't visible to
    # django-stubs, so read them through `.values()` (a plain dict) rather than
    # attribute access.
    row = (
        Achievement.objects.filter(slug=KONAMI_SLUG)
        .values(
            "name_pl",
            "name_en",
            "description_pl",
            "description_en",
            "theme_pl",
            "theme_en",
        )
        .get()
    )

    assert row["name_pl"] == "Kod Konami"
    assert row["name_en"] == "Konami Code"
    assert row["description_pl"]
    assert row["description_en"]
    assert row["description_pl"] != row["description_en"]
    assert row["theme_pl"] == "Ukryte"
    assert row["theme_en"] == "Hidden"


@pytest.mark.django_db
@pytest.mark.usefixtures("_seed_konami")
def test_migration_is_idempotent() -> None:
    _migration.create_konami_achievement(global_apps, None)

    assert Achievement.objects.filter(slug=KONAMI_SLUG).count() == 1
