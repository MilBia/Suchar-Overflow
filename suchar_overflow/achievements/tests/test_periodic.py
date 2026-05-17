import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
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


def _last_month_mid() -> datetime.datetime:
    """Return a timezone-aware datetime in the middle of the previous calendar month."""
    today = timezone.now().date()
    first_of_this_month = today.replace(day=1)
    last_month = first_of_this_month - datetime.timedelta(days=1)
    mid = last_month.replace(day=min(15, last_month.day))
    return timezone.make_aware(
        datetime.datetime(mid.year, mid.month, mid.day, 12, 0, 0),  # noqa: DTZ001
    )


def _last_month_end() -> str:
    """Return a YYYY-MM-DD string for the last day of the previous calendar month."""
    today = timezone.now().date()
    first_of_this_month = today.replace(day=1)
    last_day = first_of_this_month - datetime.timedelta(days=1)
    return last_day.strftime("%Y-%m-%d")


def _last_year_mid() -> datetime.datetime:
    """Return a timezone-aware datetime in the middle of the previous calendar year."""
    last_year = timezone.now().year - 1
    return timezone.make_aware(datetime.datetime(last_year, 6, 15, 12, 0, 0))  # noqa: DTZ001


def _last_year_end() -> str:
    """Return the last day of the previous calendar year as YYYY-MM-DD."""
    last_year = timezone.now().year - 1
    return f"{last_year}-12-31"


@pytest.mark.django_db
def test_award_periodic_month(periodic_achievements):
    winner = User.objects.create_user(
        username="winner",
        email="winner@example.com",
        password="password",  # noqa: S106
    )
    loser = User.objects.create_user(
        username="loser",
        email="loser@example.com",
        password="password",  # noqa: S106
    )

    mid_last_month = _last_month_mid()

    # Winner's joke — place it in last month
    s1 = Suchar.objects.create(text="Funny joke", author=winner)
    s1.created_at = mid_last_month
    s1.save()

    # Loser's joke — same period
    s2 = Suchar.objects.create(text="Bad joke", author=loser)
    s2.created_at = mid_last_month
    s2.save()

    # Winner gets 3 votes, loser gets 1
    for i in range(3):
        u = User.objects.create_user(
            username=f"voter{i}",
            email=f"voter{i}@example.com",
            password="password",  # noqa: S106
        )
        Vote.objects.create(suchar=s1, user=u, is_funny=True)

    Vote.objects.create(suchar=s2, user=winner, is_funny=True)

    call_command("award_periodic", period="month", date=_last_month_end())

    assert UserAchievement.objects.filter(
        user=winner,
        achievement__slug="best-suchar-month",
    ).exists()
    assert not UserAchievement.objects.filter(
        user=loser,
        achievement__slug="best-suchar-month",
    ).exists()


@pytest.mark.django_db
def test_award_periodic_year(periodic_achievements):
    winner = User.objects.create_user(
        username="year_winner",
        email="year_winner@example.com",
        password="password",  # noqa: S106
    )

    s1 = Suchar.objects.create(text="Yearly best", author=winner)
    s1.created_at = _last_year_mid()
    s1.save()

    voter = User.objects.create_user(
        username="voter_y",
        email="voter_y@example.com",
        password="password",  # noqa: S106
    )
    Vote.objects.create(suchar=s1, user=voter, is_funny=True)

    call_command("award_periodic", period="year", date=_last_year_end())

    assert UserAchievement.objects.filter(
        user=winner,
        achievement__slug="best-suchar-year",
    ).exists()


@pytest.mark.django_db
def test_award_periodic_month_no_suchars_does_not_crash(periodic_achievements):
    """Running the command on an empty period should exit gracefully."""
    call_command("award_periodic", period="month", date=_last_month_end())
    assert UserAchievement.objects.count() == 0


@pytest.mark.django_db
def test_award_periodic_month_winner_is_highest_vote_getter(periodic_achievements):
    """When multiple authors post in the same period, the one with more votes wins."""
    authors = [
        User.objects.create_user(
            username=f"author{i}",
            email=f"author{i}@example.com",
            password="password",  # noqa: S106
        )
        for i in range(3)
    ]
    mid = _last_month_mid()

    suchars = []
    for author in authors:
        s = Suchar.objects.create(text=f"Joke by {author.username}", author=author)
        s.created_at = mid
        s.save()
        suchars.append(s)

    # author0: 1 vote, author1: 3 votes, author2: 2 votes → author1 should win
    for i, count in enumerate([1, 3, 2]):
        for j in range(count):
            voter = User.objects.create_user(
                username=f"v{i}_{j}",
                email=f"v{i}_{j}@example.com",
                password="password",  # noqa: S106
            )
            Vote.objects.create(suchar=suchars[i], user=voter, is_funny=True)

    call_command("award_periodic", period="month", date=_last_month_end())

    assert UserAchievement.objects.filter(
        user=authors[1],
        achievement__slug="best-suchar-month",
    ).exists()
    assert not UserAchievement.objects.filter(
        user=authors[0],
        achievement__slug="best-suchar-month",
    ).exists()
    assert not UserAchievement.objects.filter(
        user=authors[2],
        achievement__slug="best-suchar-month",
    ).exists()
