import importlib

import pytest
from django.apps import apps as global_apps
from django.utils import timezone

from suchar_overflow.achievements.models import SchedulerRun


@pytest.mark.django_db
def test_scheduler_run_default_ordering_is_by_job_id():
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
def test_migration_0015_seeds_yearly_scheduler_marker():
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
