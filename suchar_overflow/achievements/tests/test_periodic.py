import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.achievements.tests.conftest import last_month_end
from suchar_overflow.achievements.tests.conftest import last_month_mid
from suchar_overflow.achievements.tests.conftest import last_year_end
from suchar_overflow.achievements.tests.conftest import last_year_mid
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()


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

    mid_last_month = last_month_mid()

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

    call_command("award_periodic", period="month", date=last_month_end())

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
    s1.created_at = last_year_mid()
    s1.save()

    voter = User.objects.create_user(
        username="voter_y",
        email="voter_y@example.com",
        password="password",  # noqa: S106
    )
    Vote.objects.create(suchar=s1, user=voter, is_funny=True)

    call_command("award_periodic", period="year", date=last_year_end())

    assert UserAchievement.objects.filter(
        user=winner,
        achievement__slug="best-suchar-year",
    ).exists()


@pytest.mark.django_db
def test_award_periodic_month_no_suchars_does_not_crash(periodic_achievements):
    """Running the command on an empty period should exit gracefully."""
    call_command("award_periodic", period="month", date=last_month_end())
    assert UserAchievement.objects.count() == 0


@pytest.mark.django_db
def test_award_periodic_month_tie_awards_all_tied_authors(periodic_achievements):
    """When different authors tie for the top vote count, every one of them
    gets the main achievement plus the hidden tie achievement (#171)."""
    author_a = User.objects.create_user(
        username="cmd-tie-a",
        email="cmd-tie-a@example.com",
        password="password",  # noqa: S106
    )
    author_b = User.objects.create_user(
        username="cmd-tie-b",
        email="cmd-tie-b@example.com",
        password="password",  # noqa: S106
    )

    mid_last_month = last_month_mid()
    s_a = Suchar.objects.create(text="Tie joke A", author=author_a)
    s_a.created_at = mid_last_month
    s_a.save()
    s_b = Suchar.objects.create(text="Tie joke B", author=author_b)
    s_b.created_at = mid_last_month
    s_b.save()

    Vote.objects.create(suchar=s_a, user=author_b, is_funny=True)
    Vote.objects.create(suchar=s_b, user=author_a, is_funny=True)

    call_command("award_periodic", period="month", date=last_month_end())

    for author in (author_a, author_b):
        assert UserAchievement.objects.filter(
            user=author,
            achievement__slug="best-suchar-month",
        ).exists()
        assert UserAchievement.objects.filter(
            user=author,
            achievement__slug="best-suchar-month-tie",
        ).exists()


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
    mid = last_month_mid()

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

    call_command("award_periodic", period="month", date=last_month_end())

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
