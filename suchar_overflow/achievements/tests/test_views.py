from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement

User = get_user_model()

ACHIEVEMENT_LIST_URL = "achievements:list"


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


def make_achievement(
    slug,
    name="Achievement",
    *,
    is_secret=False,
    theme="",
    tier=Achievement.Tier.NONE,
):
    return Achievement.objects.create(
        slug=slug,
        name=name,
        description="A test achievement.",
        icon_content="<svg></svg>",
        category="LIFETIME",
        event_type="SUCHAR_POSTED",
        metric="COUNT_SUCHAR",
        threshold=1,
        is_secret=is_secret,
        theme=theme,
        tier=tier,
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_achievement_list_requires_login(client):
    response = client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_achievement_list_renders_for_authenticated_user(client):
    user = make_user("user1")
    client.force_login(user)
    response = client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert response.status_code == HTTPStatus.OK


# ---------------------------------------------------------------------------
# Context data
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_achievement_list_shows_all_non_grouped_achievements(client):
    user = make_user("user1")
    client.force_login(user)
    make_achievement("ach-1", name="Achievement One")
    make_achievement("ach-2", name="Achievement Two")

    response = client.get(reverse(ACHIEVEMENT_LIST_URL))
    achs = response.context["achievements"]
    names = [a.name for a in achs]
    assert "Achievement One" in names
    assert "Achievement Two" in names


@pytest.mark.django_db
def test_user_achievements_set_in_context(client):
    user = make_user("user1")
    client.force_login(user)
    ach = make_achievement("ach-1")
    UserAchievement.objects.create(user=user, achievement=ach)

    response = client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert ach.pk in response.context["user_achievements"]


@pytest.mark.django_db
def test_unearned_achievement_not_in_user_achievements(client):
    user = make_user("user1")
    client.force_login(user)
    ach = make_achievement("ach-1")

    response = client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert ach.pk not in response.context["user_achievements"]


# ---------------------------------------------------------------------------
# Tiered / grouped series visibility
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_series_first_locked_achievement_is_visible(client):
    """First achievement in an unlocked series must appear in the list."""
    user = make_user("user1")
    client.force_login(user)

    ach_bronze = make_achievement(
        "series-bronze",
        name="Bronze",
        theme="Programming",
        tier=Achievement.Tier.BRONZE,
    )
    make_achievement(
        "series-silver",
        name="Silver",
        theme="Programming",
        tier=Achievement.Tier.SILVER,
    )

    response = client.get(reverse(ACHIEVEMENT_LIST_URL))
    achs = response.context["achievements"]
    ids = [a.id for a in achs]
    # Bronze (first in series) should be shown as the "next to earn" hint
    assert ach_bronze.id in ids


@pytest.mark.django_db
def test_series_locked_second_tier_hidden_until_first_earned(client):
    """Silver in a series must not appear until the user earns Bronze."""
    user = make_user("user1")
    client.force_login(user)

    make_achievement(
        "series-bronze",
        name="Bronze",
        theme="Programming",
        tier=Achievement.Tier.BRONZE,
    )
    ach_silver = make_achievement(
        "series-silver",
        name="Silver",
        theme="Programming",
        tier=Achievement.Tier.SILVER,
    )

    response = client.get(reverse(ACHIEVEMENT_LIST_URL))
    achs = response.context["achievements"]
    ids = [a.id for a in achs]
    assert ach_silver.id not in ids


@pytest.mark.django_db
def test_series_second_tier_visible_after_first_earned(client):
    """After earning Bronze the Silver achievement must become visible."""
    user = make_user("user1")
    client.force_login(user)

    ach_bronze = make_achievement(
        "series-bronze",
        name="Bronze",
        theme="Programming",
        tier=Achievement.Tier.BRONZE,
    )
    ach_silver = make_achievement(
        "series-silver",
        name="Silver",
        theme="Programming",
        tier=Achievement.Tier.SILVER,
    )
    UserAchievement.objects.create(user=user, achievement=ach_bronze)

    response = client.get(reverse(ACHIEVEMENT_LIST_URL))
    achs = response.context["achievements"]
    ids = [a.id for a in achs]
    assert ach_silver.id in ids


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_achievement_list_user_has_no_earned_achievements(client):
    """A user with no earned achievements should have an empty user_achievements set."""
    user = make_user("user1")
    client.force_login(user)
    response = client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert response.status_code == HTTPStatus.OK
    # user_achievements tracks what THIS user has earned — must be empty for a new user
    assert response.context["user_achievements"] == set()
