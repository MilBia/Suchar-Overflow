"""``achievements/cron.py`` registers the periodic jobs for ``rqcron`` (#462)."""

import importlib
from datetime import UTC
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from croniter import croniter
from django.conf import settings
from rq import cron as rq_cron

from suchar_overflow.achievements import cron
from suchar_overflow.achievements import tasks

WARSAW = ZoneInfo("Europe/Warsaw")


@pytest.fixture
def registered() -> dict[str, dict]:
    rq_cron._job_data_registry.clear()  # noqa: SLF001
    importlib.reload(cron)
    jobs = {data["name"]: data for data in rq_cron._job_data_registry}  # noqa: SLF001
    rq_cron._job_data_registry.clear()  # noqa: SLF001
    return jobs


def test_registers_exactly_the_three_jobs(registered: dict[str, dict]) -> None:
    assert {name: (job["func"], job["cron"]) for name, job in registered.items()} == {
        "award-best-suchar-month": (tasks.award_best_suchar_month_if_due, "5 * * * *"),
        "award-best-suchar-year": (tasks.award_best_suchar_year_if_due, "5 * * * *"),
        "award-publication-achievements": (tasks.award_publication_achievements, "* * * * *"),
    }


def test_every_job_expires_when_the_worker_is_down(registered: dict[str, dict]) -> None:
    # A stopped worker must not leave a growing backlog of per-minute jobs (#462).
    assert registered["award-publication-achievements"]["ttl"] <= 5 * 60
    for job in registered.values():
        assert job["ttl"] > 0
        assert job["queue_name"] == settings.RQ_QUEUE_NAME
        assert job["job_timeout"] > 0


@pytest.mark.parametrize(
    "start",
    [datetime(2024, 7, 10, 12, 0, tzinfo=UTC), datetime(2024, 12, 10, 12, 0, tzinfo=UTC)],
    ids=["summer", "winter"],
)
def test_hourly_checks_land_on_minute_five_of_the_polish_clock(start: datetime) -> None:
    """``rq.cron`` evaluates in UTC; the contest fires at 00:05 Warsaw, so one hourly
    check per day must land exactly there in both CET and CEST."""
    fires = croniter(cron.HOURLY_AT_5, start)
    local = [fires.get_next(datetime).astimezone(WARSAW) for _ in range(24)]
    assert all(fire.minute == 5 for fire in local)
    assert sum(fire.hour == 0 for fire in local) == 1
