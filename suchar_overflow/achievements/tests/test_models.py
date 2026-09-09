import importlib

import pytest
from django.apps import apps as global_apps
from django.utils import timezone

from suchar_overflow.achievements.models import SchedulerRun
from suchar_overflow.achievements.models import UserAchievement


def test_user_achievement_has_user_is_seen_composite_index() -> None:
    """The achievements-bell context processor runs
    ``UserAchievement.objects.filter(user=..., is_seen=False)`` on every page
    render for every logged-in user whenever the 5-minute Redis cache is cold
    (#338). Guard the composite index that backs that filter — the lone FK
    index on ``user`` does not cover the ``is_seen`` predicate.
    """
    index_field_sets = {
        tuple(index.fields)
        for index in UserAchievement._meta.indexes  # noqa: SLF001
    }
    assert ("user", "is_seen") in index_field_sets


@pytest.mark.django_db
def test_scheduler_run_default_ordering_is_by_job_id() -> None:
    """job_id__in isolates from the "award-best-suchar-year" row seeded by
    migration 0015 (baseline data present in every test, like the migration-
    seeded Achievement rows — see CLAUDE.md Test patterns)."""
    SchedulerRun.objects.create(job_id="b-job", ran_at=timezone.now())
    SchedulerRun.objects.create(job_id="a-job", ran_at=timezone.now())

    assert list(
        SchedulerRun.objects.filter(job_id__in=["a-job", "b-job"]).values_list(
            "job_id",
            flat=True,
        ),
    ) == ["a-job", "b-job"]


@pytest.mark.django_db
def test_migration_0015_seeds_yearly_scheduler_marker() -> None:
    """Migration 0015 seeds this marker so a fresh deploy's catch-up doesn't
    retroactively award the previous calendar year (see #168). Exercises the
    migration's own function directly (rather than asserting on ambient
    baseline data) so the test is deterministic regardless of whether an
    earlier session's transactional tests flushed the reused test DB."""
    SchedulerRun.objects.filter(job_id="award-best-suchar-year").delete()
    migration = importlib.import_module(
        "suchar_overflow.achievements.migrations.0015_seed_yearly_scheduler_run",
    )
    migration.seed_scheduler_run(global_apps, None)

    assert SchedulerRun.objects.filter(job_id="award-best-suchar-year").exists()
