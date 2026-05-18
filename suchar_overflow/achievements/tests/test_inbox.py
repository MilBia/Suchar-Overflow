"""Tests for the achievement notification inbox view."""

from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement

User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


def make_achievement(slug, name="Achievement"):
    ach, _ = Achievement.objects.get_or_create(
        slug=slug,
        defaults={
            "name": name,
            "description": "desc",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.SUCHAR_POSTED,
            "metric": Achievement.Metric.COUNT_SUCHAR,
            "threshold": 99,  # high threshold so signals never auto-award it
        },
    )
    return ach


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_inbox_requires_login(client):
    response = client.get(reverse("achievements:inbox"))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_inbox_authenticated_returns_200(client):
    user = make_user("alice")
    client.force_login(user)
    response = client.get(reverse("achievements:inbox"))
    assert response.status_code == HTTPStatus.OK


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_inbox_shows_users_achievements(client):
    user = make_user("alice")
    ach = make_achievement("first-suchar", "First Suchar")
    UserAchievement.objects.create(user=user, achievement=ach)

    client.force_login(user)
    response = client.get(reverse("achievements:inbox"))

    ua_list = list(response.context["user_achievements"])
    assert len(ua_list) == 1
    assert ua_list[0].achievement == ach


@pytest.mark.django_db
def test_inbox_empty_for_user_without_achievements(client):
    user = make_user("alice")
    client.force_login(user)
    response = client.get(reverse("achievements:inbox"))

    assert list(response.context["user_achievements"]) == []


@pytest.mark.django_db
def test_inbox_does_not_show_other_users_achievements(client):
    alice = make_user("alice")
    bob = make_user("bob")
    ach = make_achievement("first-vote")
    UserAchievement.objects.create(user=bob, achievement=ach)

    client.force_login(alice)
    response = client.get(reverse("achievements:inbox"))

    assert list(response.context["user_achievements"]) == []


@pytest.mark.django_db
def test_inbox_ordered_newest_first(client):
    user = make_user("alice")
    ach1 = make_achievement("ach-one", "First")
    ach2 = make_achievement("ach-two", "Second")
    ua1 = UserAchievement.objects.create(user=user, achievement=ach1)
    ua2 = UserAchievement.objects.create(user=user, achievement=ach2)

    client.force_login(user)
    response = client.get(reverse("achievements:inbox"))

    ua_list = list(response.context["user_achievements"])
    # Newer record (ua2) should come first.
    assert ua_list[0].pk == ua2.pk
    assert ua_list[1].pk == ua1.pk
