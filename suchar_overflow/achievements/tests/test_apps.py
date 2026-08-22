import datetime
import logging
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from suchar_overflow.achievements.apps import AchievementsConfig
from suchar_overflow.achievements.models import SchedulerRun
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()


def test_is_no_scheduler_command_detects_plain_management_command():
    assert AchievementsConfig._is_no_scheduler_command(  # noqa: SLF001
        ["manage.py", "migrate"],
    )


def test_is_no_scheduler_command_detects_command_after_global_flags():
    assert AchievementsConfig._is_no_scheduler_command(  # noqa: SLF001
        ["manage.py", "--settings=config.settings.test", "migrate"],
    )


def test_is_no_scheduler_command_false_for_runserver():
    assert not AchievementsConfig._is_no_scheduler_command(  # noqa: SLF001
        ["manage.py", "runserver"],
    )


def test_is_no_scheduler_command_does_not_misfire_on_unrelated_argument():
    """A _NO_SCHEDULER word (e.g. "check") appearing as some other command's
    own argument, rather than as the command name itself, must not match."""
    assert not AchievementsConfig._is_no_scheduler_command(  # noqa: SLF001
        ["manage.py", "test", "-k", "check"],
    )


# ---------------------------------------------------------------------------
# _catch_up_missed_monthly_run — catch-up on process start (#169)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_catch_up_missed_monthly_run_calls_award_when_never_run():
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        AchievementsConfig._catch_up_missed_monthly_run()  # noqa: SLF001

    mock_award.assert_called_once_with(
        "month",
        reference_date=datetime.date(2024, 5, 31),
    )


@pytest.mark.django_db
def test_catch_up_missed_monthly_run_calls_award_when_run_is_stale():
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    SchedulerRun.objects.create(
        job_id="award-best-suchar-month",
        ran_at=datetime.datetime(2024, 4, 1, 0, 5, tzinfo=datetime.UTC),
    )
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        AchievementsConfig._catch_up_missed_monthly_run()  # noqa: SLF001

    mock_award.assert_called_once_with(
        "month",
        reference_date=datetime.date(2024, 5, 31),
    )


@pytest.mark.django_db
def test_catch_up_missed_monthly_run_skips_award_when_run_is_current():
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    SchedulerRun.objects.create(
        job_id="award-best-suchar-month",
        ran_at=datetime.datetime(2024, 6, 1, 0, 5, tzinfo=datetime.UTC),
    )
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        AchievementsConfig._catch_up_missed_monthly_run()  # noqa: SLF001

    mock_award.assert_not_called()


@pytest.mark.django_db
def test_catch_up_missed_monthly_run_awards_the_missed_period_not_current(
    periodic_achievements,
):
    """A restart on June 15 with May's fire missed must award May's best
    suchar, not evaluate the (incomplete) current month (see #169)."""
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    may_winner = User.objects.create_user(
        username="may-winner",
        email="may-winner@example.com",
        password="pw",  # noqa: S106
    )
    june_poster = User.objects.create_user(
        username="june-poster",
        email="june-poster@example.com",
        password="pw",  # noqa: S106
    )
    voter = User.objects.create_user(
        username="voter169",
        email="voter169@example.com",
        password="pw",  # noqa: S106
    )

    may_suchar = Suchar.objects.create(text="May joke", author=may_winner)
    may_suchar.created_at = datetime.datetime(2024, 5, 15, 12, 0, tzinfo=datetime.UTC)
    may_suchar.save()
    Vote.objects.create(suchar=may_suchar, user=voter, is_funny=True)

    june_suchar = Suchar.objects.create(text="June joke", author=june_poster)
    june_suchar.created_at = datetime.datetime(2024, 6, 10, 12, 0, tzinfo=datetime.UTC)
    june_suchar.save()

    with patch("django.utils.timezone.now", return_value=frozen_now):
        AchievementsConfig._catch_up_missed_monthly_run()  # noqa: SLF001

    assert UserAchievement.objects.filter(
        user=may_winner,
        achievement__slug="best-suchar-month",
    ).exists()
    assert not UserAchievement.objects.filter(
        user=june_poster,
        achievement__slug="best-suchar-month",
    ).exists()


# ---------------------------------------------------------------------------
# _catch_up_missed_yearly_run — catch-up on process start (#168)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_catch_up_missed_yearly_run_calls_award_when_never_run():
    """Migration 0015 seeds a real "award-best-suchar-year" SchedulerRun row
    at test-db build time so a fresh deploy doesn't retroactively award the
    previous year; delete it here to exercise the true "never run" case."""
    SchedulerRun.objects.filter(job_id="award-best-suchar-year").delete()
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        AchievementsConfig._catch_up_missed_yearly_run()  # noqa: SLF001

    mock_award.assert_called_once_with(
        "year",
        reference_date=datetime.date(2023, 12, 31),
    )


@pytest.mark.django_db
def test_catch_up_missed_yearly_run_calls_award_when_run_is_stale():
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    SchedulerRun.objects.update_or_create(
        job_id="award-best-suchar-year",
        defaults={"ran_at": datetime.datetime(2022, 1, 1, 0, 5, tzinfo=datetime.UTC)},
    )
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        AchievementsConfig._catch_up_missed_yearly_run()  # noqa: SLF001

    mock_award.assert_called_once_with(
        "year",
        reference_date=datetime.date(2023, 12, 31),
    )


@pytest.mark.django_db
def test_catch_up_missed_yearly_run_skips_award_when_run_is_current():
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    SchedulerRun.objects.update_or_create(
        job_id="award-best-suchar-year",
        defaults={"ran_at": datetime.datetime(2024, 1, 1, 0, 5, tzinfo=datetime.UTC)},
    )
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        AchievementsConfig._catch_up_missed_yearly_run()  # noqa: SLF001

    mock_award.assert_not_called()


@pytest.mark.django_db
def test_catch_up_missed_yearly_run_awards_the_missed_period_not_current(
    periodic_achievements,
):
    """A restart in June 2024 with the 2023 fire missed must award 2023's
    best suchar, not evaluate the (incomplete) current year (see #168)."""
    SchedulerRun.objects.filter(job_id="award-best-suchar-year").delete()
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    year_winner = User.objects.create_user(
        username="year-winner",
        email="year-winner@example.com",
        password="pw",  # noqa: S106
    )
    current_year_poster = User.objects.create_user(
        username="current-year-poster",
        email="current-year-poster@example.com",
        password="pw",  # noqa: S106
    )
    voter = User.objects.create_user(
        username="voter168",
        email="voter168@example.com",
        password="pw",  # noqa: S106
    )

    year_suchar = Suchar.objects.create(text="2023 joke", author=year_winner)
    year_suchar.created_at = datetime.datetime(
        2023,
        5,
        15,
        12,
        0,
        tzinfo=datetime.UTC,
    )
    year_suchar.save()
    Vote.objects.create(suchar=year_suchar, user=voter, is_funny=True)

    current_year_suchar = Suchar.objects.create(
        text="2024 joke",
        author=current_year_poster,
    )
    current_year_suchar.created_at = datetime.datetime(
        2024,
        6,
        10,
        12,
        0,
        tzinfo=datetime.UTC,
    )
    current_year_suchar.save()

    with patch("django.utils.timezone.now", return_value=frozen_now):
        AchievementsConfig._catch_up_missed_yearly_run()  # noqa: SLF001

    assert UserAchievement.objects.filter(
        user=year_winner,
        achievement__slug="best-suchar-year",
    ).exists()
    assert not UserAchievement.objects.filter(
        user=current_year_poster,
        achievement__slug="best-suchar-year",
    ).exists()


# ---------------------------------------------------------------------------
# _start_scheduler must still start the recurring jobs even if catch-up fails
# (e.g. a transient DB error) — a broken catch-up shouldn't take down the
# whole scheduler thread before scheduler.start() runs (PR #170 review).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_start_scheduler_starts_even_if_monthly_catch_up_raises(caplog):
    with (
        patch(
            "suchar_overflow.achievements.apps.AchievementsConfig"
            "._catch_up_missed_monthly_run",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "apscheduler.schedulers.background.BackgroundScheduler",
        ) as mock_scheduler_cls,
        caplog.at_level(logging.ERROR, logger="suchar_overflow.achievements.apps"),
    ):
        AchievementsConfig._start_scheduler()  # noqa: SLF001

    assert mock_scheduler_cls.return_value.add_job.call_count == 2  # noqa: PLR2004
    mock_scheduler_cls.return_value.start.assert_called_once()
    assert "boom" in caplog.text


@pytest.mark.django_db
def test_start_scheduler_starts_even_if_yearly_catch_up_raises(caplog):
    with (
        patch(
            "suchar_overflow.achievements.apps.AchievementsConfig"
            "._catch_up_missed_yearly_run",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "apscheduler.schedulers.background.BackgroundScheduler",
        ) as mock_scheduler_cls,
        caplog.at_level(logging.ERROR, logger="suchar_overflow.achievements.apps"),
    ):
        AchievementsConfig._start_scheduler()  # noqa: SLF001

    assert mock_scheduler_cls.return_value.add_job.call_count == 2  # noqa: PLR2004
    mock_scheduler_cls.return_value.start.assert_called_once()
    assert "boom" in caplog.text


@pytest.mark.django_db
def test_start_scheduler_registers_month_and_year_jobs():
    with (
        patch(
            "suchar_overflow.achievements.apps.AchievementsConfig"
            "._catch_up_missed_monthly_run",
        ),
        patch(
            "suchar_overflow.achievements.apps.AchievementsConfig"
            "._catch_up_missed_yearly_run",
        ),
        patch(
            "apscheduler.schedulers.background.BackgroundScheduler",
        ) as mock_scheduler_cls,
    ):
        AchievementsConfig._start_scheduler()  # noqa: SLF001

    jobs_by_id = {
        call.kwargs["id"]: call.kwargs
        for call in mock_scheduler_cls.return_value.add_job.call_args_list
    }
    assert jobs_by_id.keys() == {"award-best-suchar-month", "award-best-suchar-year"}
    assert jobs_by_id["award-best-suchar-month"]["day"] == 1
    assert jobs_by_id["award-best-suchar-year"]["month"] == 1
    assert jobs_by_id["award-best-suchar-year"]["day"] == 1
