import datetime
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
