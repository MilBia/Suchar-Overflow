import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

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


@pytest.mark.django_db
def test_award_periodic_month(periodic_achievements):
    # Setup: Create jokes in previous month
    # today removed as unused
    # If today is Jan 1st, previous month is Dec last year.
    # To be safe, let's explicitly set the date for the command.

    # Let's verify logic for "March 2024"
    # target_date removed as unused

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

    # Winner's joke
    s1 = Suchar.objects.create(text="Funny joke", author=winner)
    s1.created_at = datetime.datetime(2024, 3, 10, 12, 0, 0, tzinfo=datetime.UTC)
    s1.save()

    # Loser's joke
    s2 = Suchar.objects.create(text="Bad joke", author=loser)
    s2.created_at = datetime.datetime(2024, 3, 10, 12, 0, 0, tzinfo=datetime.UTC)
    s2.save()

    # Vote for winner (3 votes)
    for i in range(3):
        u = User.objects.create_user(
            username=f"voter{i}",
            email=f"voter{i}@example.com",
            password="password",  # noqa: S106
        )
        Vote.objects.create(suchar=s1, user=u, is_funny=True)

    # Vote for loser (1 vote)
    Vote.objects.create(suchar=s2, user=winner, is_funny=True)

    # Run command for March 2024 (reference date in March finds Best of March?)
    # Command logic: "Find the Best Suchar (created within the period)".
    # If period='month' and date='2024-03-31', it looks at March 2024.

    call_command("award_periodic", period="month", date="2024-03-31")

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
    # Verify year logic
    # target_year unused

    winner = User.objects.create_user(
        username="year_winner",
        email="year_winner@example.com",
        password="password",  # noqa: S106
    )

    s1 = Suchar.objects.create(text="Yearly best", author=winner)
    s1.created_at = datetime.datetime(2023, 6, 15, 12, 0, 0, tzinfo=datetime.UTC)
    s1.save()

    # 1 vote is enough if only one
    voter = User.objects.create_user(
        username="voter_y",
        email="voter_y@example.com",
        password="password",  # noqa: S106
    )
    Vote.objects.create(suchar=s1, user=voter, is_funny=True)

    call_command("award_periodic", period="year", date="2023-12-31")

    assert UserAchievement.objects.filter(
        user=winner,
        achievement__slug="best-suchar-year",
    ).exists()
