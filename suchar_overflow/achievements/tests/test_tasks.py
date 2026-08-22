import datetime
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import SchedulerRun
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.achievements.tasks import award_best_suchar
from suchar_overflow.achievements.tasks import compute_period_range
from suchar_overflow.achievements.tests.conftest import freeze_to_first_of_current_month
from suchar_overflow.achievements.tests.conftest import last_month_mid
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()


# ---------------------------------------------------------------------------
# compute_period_range (pure function, shared by the command and the task)
# ---------------------------------------------------------------------------


def test_compute_period_range_month():
    start_dt, end_dt, suffix = compute_period_range(
        "month",
        datetime.date(2024, 2, 15),
    )
    assert start_dt == datetime.datetime(2024, 2, 1, 0, 0, tzinfo=start_dt.tzinfo)
    assert end_dt == datetime.datetime(2024, 3, 1, 0, 0, tzinfo=end_dt.tzinfo)
    assert suffix == "month"


def test_compute_period_range_month_december_rolls_into_next_year():
    start_dt, end_dt, _suffix = compute_period_range(
        "month",
        datetime.date(2024, 12, 10),
    )
    assert start_dt == datetime.datetime(2024, 12, 1, 0, 0, tzinfo=start_dt.tzinfo)
    assert end_dt == datetime.datetime(2025, 1, 1, 0, 0, tzinfo=end_dt.tzinfo)


def test_compute_period_range_year():
    start_dt, end_dt, suffix = compute_period_range(
        "year",
        datetime.date(2024, 6, 1),
    )
    assert start_dt == datetime.datetime(2024, 1, 1, 0, 0, tzinfo=start_dt.tzinfo)
    assert end_dt == datetime.datetime(2025, 1, 1, 0, 0, tzinfo=end_dt.tzinfo)
    assert suffix == "year"


def test_compute_period_range_unknown_period_raises():
    with pytest.raises(ValueError, match="Unknown period"):
        compute_period_range("week", datetime.date(2024, 6, 1))


# ---------------------------------------------------------------------------
# award_best_suchar task
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_award_best_suchar_month_awards_winner(periodic_achievements):
    frozen_now = freeze_to_first_of_current_month()
    winner = User.objects.create_user(
        username="winner",
        email="w@example.com",
        password="pw",  # noqa: S106
    )
    loser = User.objects.create_user(
        username="loser",
        email="l@example.com",
        password="pw",  # noqa: S106
    )

    mid = last_month_mid()
    s_win = Suchar.objects.create(text="Funny", author=winner)
    s_win.created_at = mid
    s_win.save()
    s_lose = Suchar.objects.create(text="Bad", author=loser)
    s_lose.created_at = mid
    s_lose.save()

    for i in range(3):
        u = User.objects.create_user(
            username=f"v{i}",
            email=f"v{i}@example.com",
            password="pw",  # noqa: S106
        )
        Vote.objects.create(suchar=s_win, user=u, is_funny=True)
    Vote.objects.create(suchar=s_lose, user=winner, is_funny=True)

    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month")

    assert UserAchievement.objects.filter(
        user=winner,
        achievement__slug="best-suchar-month",
    ).exists()
    assert not UserAchievement.objects.filter(
        user=loser,
        achievement__slug="best-suchar-month",
    ).exists()


@pytest.mark.django_db
def test_award_best_suchar_month_no_suchars_does_not_crash(periodic_achievements):
    frozen_now = freeze_to_first_of_current_month()
    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month")  # should not raise
    assert UserAchievement.objects.count() == 0


@pytest.mark.django_db
def test_award_best_suchar_month_missing_achievement_does_not_crash(
    periodic_achievements,
):
    """If the achievement slug doesn't exist in the DB the task exits gracefully."""
    frozen_now = freeze_to_first_of_current_month()
    winner = User.objects.create_user(
        username="w2",
        email="w2@example.com",
        password="pw",  # noqa: S106
    )
    mid = last_month_mid()
    s = Suchar.objects.create(text="Joke", author=winner)
    s.created_at = mid
    s.save()
    voter = User.objects.create_user(
        username="vw2",
        email="vw2@example.com",
        password="pw",  # noqa: S106
    )
    Vote.objects.create(suchar=s, user=voter, is_funny=True)

    with (
        patch(
            "suchar_overflow.achievements.tasks.timezone.now",
            return_value=frozen_now,
        ),
        patch(
            "suchar_overflow.achievements.tasks.Achievement.objects.get",
            side_effect=Achievement.DoesNotExist,
        ),
    ):
        award_best_suchar("month")  # should not raise

    assert not UserAchievement.objects.filter(
        achievement__slug="best-suchar-month",
    ).exists()


@pytest.mark.django_db
def test_award_best_suchar_is_idempotent(periodic_achievements):
    """Calling the task twice doesn't create duplicate UserAchievements."""
    frozen_now = freeze_to_first_of_current_month()
    winner = User.objects.create_user(
        username="idem",
        email="idem@example.com",
        password="pw",  # noqa: S106
    )
    mid = last_month_mid()
    s = Suchar.objects.create(text="Idempotent joke", author=winner)
    s.created_at = mid
    s.save()
    voter = User.objects.create_user(
        username="votidem",
        email="vi@example.com",
        password="pw",  # noqa: S106
    )
    Vote.objects.create(suchar=s, user=voter, is_funny=True)

    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month")
        award_best_suchar("month")

    assert (
        UserAchievement.objects.filter(
            user=winner,
            achievement__slug="best-suchar-month",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_award_best_suchar_raises_on_unknown_period(periodic_achievements):
    frozen_now = freeze_to_first_of_current_month()
    with (
        patch(
            "suchar_overflow.achievements.tasks.timezone.now",
            return_value=frozen_now,
        ),
        pytest.raises(ValueError, match="Unknown period"),
    ):
        award_best_suchar("week")


# ---------------------------------------------------------------------------
# award_best_suchar records a SchedulerRun (replaces django-apscheduler's
# DjangoJobStore visibility now that the scheduler uses an in-memory jobstore)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_award_best_suchar_records_scheduler_run(periodic_achievements):
    frozen_now = freeze_to_first_of_current_month()
    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month")

    run = SchedulerRun.objects.get(job_id="award-best-suchar-month")
    assert run.ran_at == frozen_now


@pytest.mark.django_db
def test_award_best_suchar_updates_existing_scheduler_run(periodic_achievements):
    frozen_now = freeze_to_first_of_current_month()
    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month")
        award_best_suchar("month")

    assert SchedulerRun.objects.filter(job_id="award-best-suchar-month").count() == 1
