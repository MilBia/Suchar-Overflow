import datetime
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.achievements.tasks import award_best_suchar
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()


@pytest.fixture
def periodic_achievements(db):
    Achievement.objects.get_or_create(
        slug="best-suchar-month",
        defaults={
            "name": "Comedian of the Month",
            "category": "PERIODIC",
            "metric": "SUM_SCORE",
            "threshold": 0,
            "icon_content": "<svg></svg>",
        },
    )
    Achievement.objects.get_or_create(
        slug="best-suchar-year",
        defaults={
            "name": "Legend of the Year",
            "category": "PERIODIC",
            "metric": "SUM_SCORE",
            "threshold": 0,
            "icon_content": "<svg></svg>",
        },
    )


def _freeze_to_first_of_current_month() -> datetime.datetime:
    """Return a datetime pinned to the 1st of the current month (noon UTC).

    When the task uses ``timezone.now() - timedelta(days=1)``, yesterday falls
    in the previous month — which is what the monthly scheduler triggers on.
    """
    today = timezone.now().date()
    first = today.replace(day=1)
    return timezone.make_aware(
        datetime.datetime(first.year, first.month, first.day, 12, 0, 0),  # noqa: DTZ001
    )


def _last_month_mid() -> datetime.datetime:
    today = timezone.now().date()
    first_of_this_month = today.replace(day=1)
    last_month = first_of_this_month - datetime.timedelta(days=1)
    mid = last_month.replace(day=min(15, last_month.day))
    return timezone.make_aware(
        datetime.datetime(mid.year, mid.month, mid.day, 12, 0, 0),  # noqa: DTZ001
    )


# ---------------------------------------------------------------------------
# award_best_suchar task
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_award_best_suchar_month_awards_winner(periodic_achievements):
    frozen_now = _freeze_to_first_of_current_month()
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

    mid = _last_month_mid()
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
    frozen_now = _freeze_to_first_of_current_month()
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
    frozen_now = _freeze_to_first_of_current_month()
    winner = User.objects.create_user(
        username="w2",
        email="w2@example.com",
        password="pw",  # noqa: S106
    )
    mid = _last_month_mid()
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
    frozen_now = _freeze_to_first_of_current_month()
    winner = User.objects.create_user(
        username="idem",
        email="idem@example.com",
        password="pw",  # noqa: S106
    )
    mid = _last_month_mid()
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
    frozen_now = _freeze_to_first_of_current_month()
    with (
        patch(
            "suchar_overflow.achievements.tasks.timezone.now",
            return_value=frozen_now,
        ),
        pytest.raises(ValueError, match="Unknown period"),
    ):
        award_best_suchar("week")


# ---------------------------------------------------------------------------
# register_scheduled_jobs management command
# ---------------------------------------------------------------------------


def test_register_scheduled_jobs_registers_cron_job():
    """Command registers the monthly cron job in the scheduler."""
    mock_scheduler = MagicMock()
    mock_scheduler.get_jobs.return_value = []

    with patch("django_rq.get_scheduler", return_value=mock_scheduler):
        call_command("register_scheduled_jobs")

    mock_scheduler.cron.assert_called_once()
    call_kwargs = mock_scheduler.cron.call_args
    assert call_kwargs.kwargs["id"] == "award-best-suchar-month"
    assert call_kwargs.args[0] == "5 0 1 * *"


def test_register_scheduled_jobs_is_idempotent():
    """Running the command twice cancels the old job before re-registering."""
    existing_job = MagicMock()
    existing_job.id = "award-best-suchar-month"

    mock_scheduler = MagicMock()
    mock_scheduler.get_jobs.return_value = [existing_job]

    with patch("django_rq.get_scheduler", return_value=mock_scheduler):
        call_command("register_scheduled_jobs")

    mock_scheduler.cancel.assert_called_once_with("award-best-suchar-month")
    mock_scheduler.cron.assert_called_once()
