import pytest
from django.contrib.auth import get_user_model

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()

# Ensure migration data is loaded or create it if strategy differs.
# Pytest-django with migrations enabled should have data.
# But just in case, or for clarity, we can check/create.


@pytest.fixture
def ensure_achievements():
    # Helper to ensure achievements exist for tests if not loaded via migration
    # (Though they should be).
    if not Achievement.objects.filter(slug="first-suchar").exists():
        Achievement.objects.create(
            name="First Suchar",
            slug="first-suchar",
            description="Posted your first Suchar!",
            icon_content="<svg>...</svg>",
            category="LIFETIME",
            event_type="SUCHAR_POSTED",
            metric="COUNT_SUCHAR",
            threshold=1,
        )
    if not Achievement.objects.filter(slug="first-vote").exists():
        Achievement.objects.create(
            name="First Vote",
            slug="first-vote",
            description="Cast your first vote!",
            icon_content="<svg>...</svg>",
            category="LIFETIME",
            event_type="VOTE_CAST",  # VOTE_CAST changed from VOTE_RECEIVED for voter
            metric="COUNT_VOTE_CAST",
            threshold=1,
        )
    if not Achievement.objects.filter(slug="rising-star").exists():
        Achievement.objects.create(
            name="Rising Star",
            slug="rising-star",
            description="Received 5 votes in total!",
            icon_content="<svg>...</svg>",
            category="LIFETIME",
            event_type="VOTE_RECEIVED",
            metric="SUM_SCORE",
            threshold=5,
        )


@pytest.mark.django_db
def test_first_suchar_achievement(ensure_achievements):
    user = User.objects.create_user(
        username="joker",
        email="joker@example.com",
        password="password",  # noqa: S106
    )

    # User should not have achievement yet
    assert not UserAchievement.objects.filter(
        user=user,
        achievement__slug="first-suchar",
    ).exists()

    # Create first Suchar
    Suchar.objects.create(text="Why did the chicken cross the road?", author=user)

    # User should have achievement now
    assert UserAchievement.objects.filter(
        user=user,
        achievement__slug="first-suchar",
    ).exists()


@pytest.mark.django_db
def test_first_vote_achievement(ensure_achievements):
    author = User.objects.create_user(
        username="author",
        email="author@example.com",
        password="password",  # noqa: S106
    )
    voter = User.objects.create_user(
        username="voter",
        email="voter@example.com",
        password="password",  # noqa: S106
    )
    suchar = Suchar.objects.create(text="Knock knock", author=author)

    # Voter should not have achievement yet
    assert not UserAchievement.objects.filter(
        user=voter,
        achievement__slug="first-vote",
    ).exists()

    # Vote
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    # Voter should have achievement now
    assert UserAchievement.objects.filter(
        user=voter,
        achievement__slug="first-vote",
    ).exists()


@pytest.mark.django_db
def test_rising_star_achievement(ensure_achievements):
    author = User.objects.create_user(
        username="popular_author",
        email="pop@example.com",
        password="password",  # noqa: S106
    )
    suchar = Suchar.objects.create(text="Very funny joke", author=author)

    # Vote 4 times (threshold is 5)
    for i in range(4):
        voter = User.objects.create_user(
            username=f"voter_{i}",
            email=f"voter_{i}@example.com",
            password="password",  # noqa: S106
        )
        Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    assert not UserAchievement.objects.filter(
        user=author,
        achievement__slug="rising-star",
    ).exists()

    # 5th vote
    voter_5 = User.objects.create_user(
        username="voter_5",
        email="voter_5@example.com",
        password="password",  # noqa: S106
    )
    Vote.objects.create(suchar=suchar, user=voter_5, is_funny=True)

    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug="rising-star",
    ).exists()
