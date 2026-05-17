import pytest
from django.contrib.auth import get_user_model

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()


@pytest.fixture
def ensure_achievements():
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
            event_type="VOTE_CAST",
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


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


# ---------------------------------------------------------------------------
# first-suchar
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_first_suchar_achievement(ensure_achievements):
    user = make_user("joker")
    assert not UserAchievement.objects.filter(
        user=user,
        achievement__slug="first-suchar",
    ).exists()

    Suchar.objects.create(text="Why did the chicken cross the road?", author=user)

    assert UserAchievement.objects.filter(
        user=user,
        achievement__slug="first-suchar",
    ).exists()


@pytest.mark.django_db
def test_first_suchar_achievement_not_awarded_twice(ensure_achievements):
    user = make_user("joker")
    Suchar.objects.create(text="First joke", author=user)
    Suchar.objects.create(text="Second joke", author=user)

    assert (
        UserAchievement.objects.filter(
            user=user,
            achievement__slug="first-suchar",
        ).count()
        == 1
    )


# ---------------------------------------------------------------------------
# first-vote (funny)  # noqa: ERA001
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_first_vote_achievement_funny(ensure_achievements):
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Knock knock", author=author)

    assert not UserAchievement.objects.filter(
        user=voter,
        achievement__slug="first-vote",
    ).exists()

    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    assert UserAchievement.objects.filter(
        user=voter,
        achievement__slug="first-vote",
    ).exists()


# ---------------------------------------------------------------------------
# first-vote (dry)  # noqa: ERA001
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_first_vote_achievement_dry(ensure_achievements):
    """Casting a dry vote (not funny) should also award the first-vote achievement."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="A dry joke", author=author)

    Vote.objects.create(suchar=suchar, user=voter, is_dry=True)

    assert UserAchievement.objects.filter(
        user=voter,
        achievement__slug="first-vote",
    ).exists()


@pytest.mark.django_db
def test_first_vote_achievement_not_awarded_twice(ensure_achievements):
    author = make_user("author")
    voter = make_user("voter")
    s1 = Suchar.objects.create(text="Joke 1", author=author)
    s2 = Suchar.objects.create(text="Joke 2", author=author)

    Vote.objects.create(suchar=s1, user=voter, is_funny=True)
    Vote.objects.create(suchar=s2, user=voter, is_dry=True)

    assert (
        UserAchievement.objects.filter(
            user=voter,
            achievement__slug="first-vote",
        ).count()
        == 1
    )


# ---------------------------------------------------------------------------
# rising-star (threshold = 5 votes)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rising_star_not_awarded_before_threshold(ensure_achievements):
    author = make_user("popular_author")
    suchar = Suchar.objects.create(text="Very funny joke", author=author)

    for i in range(4):
        voter = make_user(f"voter_{i}")
        Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    assert not UserAchievement.objects.filter(
        user=author,
        achievement__slug="rising-star",
    ).exists()


@pytest.mark.django_db
def test_rising_star_awarded_on_fifth_vote(ensure_achievements):
    author = make_user("popular_author")
    suchar = Suchar.objects.create(text="Very funny joke", author=author)

    for i in range(4):
        voter = make_user(f"voter_{i}")
        Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    voter_5 = make_user("voter_5")
    Vote.objects.create(suchar=suchar, user=voter_5, is_funny=True)

    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug="rising-star",
    ).exists()


@pytest.mark.django_db
def test_rising_star_dry_votes_count_negatively(ensure_achievements):
    """Dry votes subtract from SUM_SCORE so 5 dry-only votes must NOT award rising-star."""  # noqa: E501
    author = make_user("popular_author")
    suchar = Suchar.objects.create(text="A controversial classic", author=author)

    for i in range(5):
        voter = make_user(f"dry_voter_{i}")
        Vote.objects.create(suchar=suchar, user=voter, is_dry=True)

    # Score = 5 x (-1) = -5, below the threshold of 5
    assert not UserAchievement.objects.filter(
        user=author,
        achievement__slug="rising-star",
    ).exists()


@pytest.mark.django_db
def test_rising_star_net_score_reaches_threshold(ensure_achievements):
    """Net score (funny +1, dry -1) must reach threshold=5 to award rising-star."""
    author = make_user("popular_author")
    suchar = Suchar.objects.create(text="A mixed joke", author=author)

    # 7 funny (+7) + 2 dry (-2) = net 5 → exactly at threshold
    for i in range(7):
        voter = make_user(f"funny_voter_{i}")
        Vote.objects.create(suchar=suchar, user=voter, is_funny=True)
    for i in range(2):
        voter = make_user(f"dry_voter_{i}")
        Vote.objects.create(suchar=suchar, user=voter, is_dry=True)

    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug="rising-star",
    ).exists()


@pytest.mark.django_db
def test_rising_star_counts_votes_across_multiple_suchars(ensure_achievements):
    """Votes spread across multiple suchars by the same author should accumulate."""
    author = make_user("popular_author")
    s1 = Suchar.objects.create(text="Joke A", author=author)
    s2 = Suchar.objects.create(text="Joke B", author=author)

    for i in range(3):
        voter = make_user(f"va{i}")
        Vote.objects.create(suchar=s1, user=voter, is_funny=True)

    for i in range(2):
        voter = make_user(f"vb{i}")
        Vote.objects.create(suchar=s2, user=voter, is_funny=True)

    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug="rising-star",
    ).exists()


@pytest.mark.django_db
def test_rising_star_not_awarded_twice(ensure_achievements):
    author = make_user("popular_author")
    suchar = Suchar.objects.create(text="Very funny joke", author=author)

    for i in range(6):
        voter = make_user(f"voter_{i}")
        Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    assert (
        UserAchievement.objects.filter(
            user=author,
            achievement__slug="rising-star",
        ).count()
        == 1
    )
