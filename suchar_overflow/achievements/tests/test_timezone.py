"""Service time zone boundaries for achievements and contests (#405).

``TIME_ZONE = "Europe/Warsaw"``: storage stays UTC, but every day/hour/period
boundary (Night Owl, streak, monthly/yearly contest, scheduler fire times) is
measured on the Polish wall clock. Each timestamp here sits in the 22:00-24:00
UTC window (or a DST month), where UTC and local time disagree about the day —
the only window where a UTC boundary bug is observable.
"""

import datetime
import zoneinfo
from unittest.mock import patch

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings

from suchar_overflow.achievements.apps import AchievementsConfig
from suchar_overflow.achievements.engine import NightOwlRule
from suchar_overflow.achievements.engine import StreakLoginRule
from suchar_overflow.achievements.models import SchedulerRun
from suchar_overflow.achievements.tasks import award_best_suchar
from suchar_overflow.achievements.tasks import compute_period_range
from suchar_overflow.achievements.tasks import due_monthly_run_at
from suchar_overflow.achievements.tasks import due_yearly_run_at
from suchar_overflow.achievements.tasks import find_best_suchary
from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

WARSAW = zoneinfo.ZoneInfo("Europe/Warsaw")
UTC = datetime.UTC

CET = datetime.timedelta(hours=1)
CEST = datetime.timedelta(hours=2)


def _backdate(suchar: Suchar, at: datetime.datetime) -> Suchar:
    Suchar.objects.filter(pk=suchar.pk).update(created_at=at, published_at=at)
    suchar.refresh_from_db()
    return suchar


def test_service_time_zone_is_warsaw() -> None:
    assert settings.TIME_ZONE == "Europe/Warsaw"


# ---------------------------------------------------------------------------
# NightOwlRule — the 00-04 window is local
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_night_owl_counts_local_half_past_midnight_in_summer() -> None:
    """22:30Z in July is 00:30 CEST — a night suchar (UTC would say 22:xx)."""
    user = make_user("owl405a")
    suchar = _backdate(
        Suchar.objects.create(text="late", author=user),
        datetime.datetime(2024, 7, 10, 22, 30, tzinfo=UTC),
    )
    assert NightOwlRule.compute_value(user, instance=suchar) == 1


@pytest.mark.django_db
def test_night_owl_ignores_local_early_morning_in_summer() -> None:
    """03:30Z in July is 05:30 CEST — outside the window (UTC would say 03:xx)."""
    user = make_user("owl405b")
    suchar = _backdate(
        Suchar.objects.create(text="early", author=user),
        datetime.datetime(2024, 7, 10, 3, 30, tzinfo=UTC),
    )
    assert NightOwlRule.compute_value(user, instance=suchar) is None


# ---------------------------------------------------------------------------
# StreakLoginRule — day boundary is local midnight
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_streak_splits_days_at_local_midnight() -> None:
    """10:00Z and 22:30Z on July 10 are two different *local* days (Jul 10 and
    Jul 11) — a 2-day streak, not one day as a UTC truncation would count."""
    user = make_user("streak405")
    _backdate(
        Suchar.objects.create(text="day one", author=user),
        datetime.datetime(2024, 7, 10, 10, 0, tzinfo=UTC),
    )
    _backdate(
        Suchar.objects.create(text="day two", author=user),
        datetime.datetime(2024, 7, 10, 22, 30, tzinfo=UTC),
    )
    assert StreakLoginRule.compute_value(user) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Contest periods — month/year start at local midnight
# ---------------------------------------------------------------------------


def test_compute_period_range_month_bounds_are_local_midnight() -> None:
    start, end, _ = compute_period_range("month", datetime.date(2024, 7, 15))
    assert start == datetime.datetime(2024, 7, 1, tzinfo=WARSAW)
    assert start == datetime.datetime(2024, 6, 30, 22, 0, tzinfo=UTC)
    assert end == datetime.datetime(2024, 7, 31, 22, 0, tzinfo=UTC)


def test_compute_period_range_year_bounds_are_local_midnight() -> None:
    start, end, _ = compute_period_range("year", datetime.date(2024, 7, 15))
    assert start == datetime.datetime(2023, 12, 31, 23, 0, tzinfo=UTC)
    assert end == datetime.datetime(2024, 12, 31, 23, 0, tzinfo=UTC)


@pytest.mark.django_db
def test_suchar_just_after_local_month_start_counts_for_new_month() -> None:
    """June 30 22:30Z is July 1 00:30 CEST — July's contest, not June's."""
    author = make_user("contest405")
    voter = make_user("contest405voter")
    suchar = _backdate(
        Suchar.objects.create(text="first of July", author=author),
        datetime.datetime(2024, 6, 30, 22, 30, tzinfo=UTC),
    )
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    july = compute_period_range("month", datetime.date(2024, 7, 1))
    june = compute_period_range("month", datetime.date(2024, 6, 1))
    assert find_best_suchary(july[0], july[1]) == [suchar]
    assert find_best_suchary(june[0], june[1]) == []


# ---------------------------------------------------------------------------
# due_*_run_at — cron fires reconstructed on the local wall clock
# ---------------------------------------------------------------------------


def test_due_monthly_run_at_converts_utc_now_to_local_first() -> None:
    """June 30 22:10Z is already July 1 00:10 CEST: July's 00:05 fire is due."""
    now = datetime.datetime(2024, 6, 30, 22, 10, tzinfo=UTC)
    last_ran_at = datetime.datetime(2024, 6, 1, 0, 5, tzinfo=WARSAW)
    due_at = due_monthly_run_at(now, last_ran_at)
    assert due_at == datetime.datetime(2024, 7, 1, 0, 5, tzinfo=WARSAW)
    assert due_at == datetime.datetime(2024, 6, 30, 22, 5, tzinfo=UTC)


def test_due_monthly_run_at_just_before_local_fire_is_not_due_yet() -> None:
    """June 30 22:04Z is July 1 00:04 CEST — July's fire hasn't happened."""
    now = datetime.datetime(2024, 6, 30, 22, 4, tzinfo=UTC)
    last_ran_at = datetime.datetime(2024, 6, 1, 0, 5, tzinfo=WARSAW)
    assert due_monthly_run_at(now, last_ran_at) is None


def test_due_monthly_run_at_ignores_marker_from_utc_era() -> None:
    """Deploy-day guard: the pre-#405 cron wrote its marker at 00:05 *UTC* on
    the 1st (02:05 CEST), which is after the new 00:05-local fire time — so the
    first boot after deploy must not see a spurious missed run."""
    now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
    utc_era_marker = datetime.datetime(2024, 6, 1, 0, 5, tzinfo=UTC)
    assert due_monthly_run_at(now, utc_era_marker) is None


def test_due_yearly_run_at_ignores_marker_from_utc_era() -> None:
    now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
    utc_era_marker = datetime.datetime(2024, 1, 1, 0, 5, tzinfo=UTC)
    assert due_yearly_run_at(now, utc_era_marker) is None


def test_due_yearly_run_at_converts_utc_now_to_local_first() -> None:
    """Dec 31 23:10Z is Jan 1 00:10 CET: the new year's fire is due."""
    now = datetime.datetime(2023, 12, 31, 23, 10, tzinfo=UTC)
    last_ran_at = datetime.datetime(2023, 1, 1, 0, 5, tzinfo=WARSAW)
    assert due_yearly_run_at(now, last_ran_at) == datetime.datetime(
        2024,
        1,
        1,
        0,
        5,
        tzinfo=WARSAW,
    )


@pytest.mark.parametrize(
    ("now", "expected_offset"),
    [
        # After the March switch (Mar 31 2024, 02:00 CET -> 03:00 CEST) the
        # due fire is still March 1 00:05 *CET*.
        (datetime.datetime(2024, 3, 31, 12, 0, tzinfo=WARSAW), CET),
        # April 1 00:10 CEST -> April 1 00:05 CEST.
        (datetime.datetime(2024, 4, 1, 0, 10, tzinfo=WARSAW), CEST),
        # After the October switch (Oct 27 2024, 03:00 CEST -> 02:00 CET) the
        # due fire is still October 1 00:05 *CEST*.
        (datetime.datetime(2024, 10, 27, 12, 0, tzinfo=WARSAW), CEST),
        # November 1 00:10 CET -> November 1 00:05 CET.
        (datetime.datetime(2024, 11, 1, 0, 10, tzinfo=WARSAW), CET),
    ],
)
def test_due_monthly_run_at_across_dst(
    now: datetime.datetime,
    expected_offset: datetime.timedelta,
) -> None:
    due_at = due_monthly_run_at(now, None)
    assert due_at is not None
    local_due = due_at.astimezone(WARSAW)
    assert (local_due.day, local_due.hour, local_due.minute) == (1, 0, 5)
    assert local_due.month == now.month
    assert local_due.utcoffset() == expected_offset


@pytest.mark.django_db
def test_catch_up_monthly_run_references_local_previous_day() -> None:
    """Restart at July 1 00:10 CEST (June 30 22:10Z) with July's fire missed:
    the catch-up must award June (reference June 30), not May."""
    frozen_now = datetime.datetime(2024, 6, 30, 22, 10, tzinfo=UTC)
    SchedulerRun.objects.update_or_create(
        job_id="award-best-suchar-month",
        defaults={"ran_at": datetime.datetime(2024, 6, 1, 0, 5, tzinfo=WARSAW)},
    )
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        AchievementsConfig._catch_up_missed_monthly_run()  # noqa: SLF001

    mock_award.assert_called_once_with(
        "month",
        reference_date=datetime.date(2024, 6, 30),
    )


@pytest.mark.django_db
def test_award_best_suchar_default_reference_date_is_local_yesterday() -> None:
    """The cron fires at 00:05 local on the 1st, when the UTC date is still the
    last day of the previous month — "yesterday" must be the local one, or the
    job would score the month *before* the one that just ended."""
    frozen_now = datetime.datetime(2024, 6, 30, 22, 5, tzinfo=UTC)
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch(
            "suchar_overflow.achievements.tasks.compute_period_range",
            wraps=compute_period_range,
        ) as mock_range,
    ):
        award_best_suchar("month")

    mock_range.assert_called_once_with("month", datetime.date(2024, 6, 30))


@pytest.mark.parametrize(
    ("job_id", "now", "expected_fire_utc"),
    [
        # July 1 00:05 CEST.
        (
            "award-best-suchar-month",
            datetime.datetime(2024, 6, 30, 21, 0, tzinfo=UTC),
            datetime.datetime(2024, 6, 30, 22, 5, tzinfo=UTC),
        ),
        # Nov 1 00:05 CET — the October DST switch lies in between.
        (
            "award-best-suchar-month",
            datetime.datetime(2024, 10, 15, 12, 0, tzinfo=UTC),
            datetime.datetime(2024, 10, 31, 23, 5, tzinfo=UTC),
        ),
        # Jan 1 2025 00:05 CET.
        (
            "award-best-suchar-year",
            datetime.datetime(2024, 6, 15, 12, 0, tzinfo=UTC),
            datetime.datetime(2024, 12, 31, 23, 5, tzinfo=UTC),
        ),
    ],
)
def test_scheduler_crons_fire_at_local_midnight(
    job_id: str,
    now: datetime.datetime,
    expected_fire_utc: datetime.datetime,
) -> None:
    """Real APScheduler triggers (only ``start`` is stubbed): the contest crons
    resolve on the Polish wall clock, so they fire at 00:05 local time."""
    with (
        patch.object(AchievementsConfig, "_catch_up_missed_monthly_run"),
        patch.object(AchievementsConfig, "_catch_up_missed_yearly_run"),
        patch.object(AchievementsConfig, "_catch_up_missed_publication_run"),
        patch.object(BackgroundScheduler, "start", autospec=True) as mock_start,
    ):
        AchievementsConfig._start_scheduler()  # noqa: SLF001

    scheduler = mock_start.call_args.args[0]
    job = scheduler.get_job(job_id)
    assert job is not None
    assert job.trigger.get_next_fire_time(None, now) == expected_fire_utc
