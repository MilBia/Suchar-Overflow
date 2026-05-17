from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
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


def make_achievement(slug="test-ach", name="Test Achievement"):
    achievement, _ = Achievement.objects.get_or_create(
        slug=slug,
        defaults={
            "name": name,
            "description": "A test achievement.",
            "icon_content": "<svg></svg>",
            "category": "LIFETIME",
            "event_type": "SUCHAR_POSTED",
            "metric": "COUNT_SUCHAR",
            "threshold": 1,
        },
    )
    return achievement


# ---------------------------------------------------------------------------
# Notification messages
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unseen_achievement_produces_message(client):
    user = make_user("winner")
    achievement = make_achievement()
    UserAchievement.objects.create(user=user, achievement=achievement, is_seen=False)

    client.force_login(user)
    response = client.get(reverse("suchary:list"), follow=True)

    messages = list(get_messages(response.wsgi_request))
    texts = [str(m) for m in messages]
    assert any("Test Achievement" in t for t in texts)


@pytest.mark.django_db
def test_unseen_achievement_marked_as_seen_after_request(client):
    user = make_user("winner")
    achievement = make_achievement()
    ua = UserAchievement.objects.create(
        user=user,
        achievement=achievement,
        is_seen=False,
    )

    client.force_login(user)
    client.get(reverse("suchary:list"))

    ua.refresh_from_db()
    assert ua.is_seen is True


@pytest.mark.django_db
def test_seen_achievement_produces_no_message(client):
    user = make_user("winner")
    achievement = make_achievement()
    UserAchievement.objects.create(user=user, achievement=achievement, is_seen=True)

    client.force_login(user)
    response = client.get(reverse("suchary:list"), follow=True)

    messages = list(get_messages(response.wsgi_request))
    texts = [str(m) for m in messages]
    assert not any("Test Achievement" in t for t in texts)


@pytest.mark.django_db
def test_multiple_unseen_achievements_all_notified(client):
    user = make_user("winner")
    ach1 = make_achievement(slug="ach-1", name="Achievement One")
    ach2 = make_achievement(slug="ach-2", name="Achievement Two")
    UserAchievement.objects.create(user=user, achievement=ach1, is_seen=False)
    UserAchievement.objects.create(user=user, achievement=ach2, is_seen=False)

    client.force_login(user)
    response = client.get(reverse("suchary:list"), follow=True)

    texts = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("Achievement One" in t for t in texts)
    assert any("Achievement Two" in t for t in texts)


@pytest.mark.django_db
def test_unauthenticated_user_gets_no_messages(client):
    """The middleware must not query achievements for anonymous users."""
    response = client.get(reverse("suchary:list"), follow=True)
    # Should complete without error and without achievement messages
    assert response.status_code == HTTPStatus.OK
    messages = list(get_messages(response.wsgi_request))
    assert all("Achievement Unlocked" not in str(m) for m in messages)
