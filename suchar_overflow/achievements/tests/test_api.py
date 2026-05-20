from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement

User = get_user_model()

UNSEEN_ACHIEVEMENTS_URL = "/api/achievements/unseen"


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


def make_achievement(slug, name="Achievement"):
    return Achievement.objects.create(
        slug=slug,
        name=name,
        description="A test achievement.",
        icon_content="<svg></svg>",
        category="LIFETIME",
        event_type="SUCHAR_POSTED",
        metric="COUNT_SUCHAR",
        threshold=1,
    )


@pytest.mark.django_db
def test_unseen_achievements_requires_login(client):
    response = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_unseen_achievements_empty_by_default(client):
    user = make_user("user1")
    client.force_login(user)

    response = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.django_db
def test_unseen_achievements_returns_awarded(client):
    user = make_user("user1")
    client.force_login(user)

    ach = make_achievement("ach-1", name="Achievement Test")
    UserAchievement.objects.create(user=user, achievement=ach, is_seen=False)

    # Set pending cache key
    cache.set(f"achievements_pending:{user.pk}", value=True)

    response = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response.status_code == HTTPStatus.OK

    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Achievement Test"
    assert data[0]["description"] == "A test achievement."
    assert data[0]["icon_content"] == "<svg></svg>"
    assert data[0]["tier"] == Achievement.Tier.NONE

    # Subsequent request should return empty
    response_again = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response_again.status_code == HTTPStatus.OK
    assert response_again.json() == []

    # Check database and cache state
    user_ach = UserAchievement.objects.get(user=user, achievement=ach)
    assert user_ach.is_seen is True
    assert cache.get(f"achievements_pending:{user.pk}") is None
