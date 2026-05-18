"""Tests for the ActivationToken model and cache flag set by AchievementEngine."""

import contextlib
import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError
from django.utils import timezone

from suchar_overflow.achievements.engine import AchievementEngine
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.users.models import ActivationToken

User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
        is_active=False,
    )


@pytest.mark.django_db
def test_fresh_token_is_valid():
    user = make_user("alice")
    token = ActivationToken.objects.create(user=user)
    assert token.is_valid()


@pytest.mark.django_db
def test_token_within_expiry_window_is_valid():
    user = make_user("alice")
    token = ActivationToken.objects.create(user=user)
    ActivationToken.objects.filter(pk=token.pk).update(
        created_at=timezone.now() - datetime.timedelta(hours=71),
    )
    token.refresh_from_db()
    assert token.is_valid()


@pytest.mark.django_db
def test_expired_token_is_invalid():
    user = make_user("alice")
    token = ActivationToken.objects.create(user=user)
    ActivationToken.objects.filter(pk=token.pk).update(
        created_at=timezone.now() - datetime.timedelta(hours=73),
    )
    token.refresh_from_db()
    assert not token.is_valid()


@pytest.mark.django_db
def test_token_is_unique_per_user():
    """Creating a second token for the same user must raise an IntegrityError."""
    user = make_user("alice")
    ActivationToken.objects.create(user=user)
    with contextlib.suppress(Exception), pytest.raises(IntegrityError):
        ActivationToken.objects.create(user=user)


@pytest.mark.django_db
def test_engine_sets_cache_flag_when_achievement_awarded():
    """Creating a Suchar fires the signal → engine awards → cache flag set."""
    user = User.objects.create_user(
        username="winner",
        email="winner@example.com",
        password="pw",  # noqa: S106
    )
    Achievement.objects.get_or_create(
        slug="cache-flag-test-ach",
        defaults={
            "name": "Cache Flag Test",
            "description": "desc",
            "icon_content": "",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.SUCHAR_POSTED,
            "metric": Achievement.Metric.COUNT_SUCHAR,
            "threshold": 1,
        },
    )

    # Signal fires here → engine checks achievements → awards → sets cache flag.
    Suchar.objects.create(text="Hello world", author=user)

    assert cache.get(f"achievements_pending:{user.pk}") is True


@pytest.mark.django_db
def test_engine_does_not_set_cache_flag_when_no_achievement_awarded():
    user = User.objects.create_user(
        username="nobody",
        email="nobody@example.com",
        password="pw",  # noqa: S106
    )
    # No achievements in DB — nothing to award.
    AchievementEngine.check_achievements(user, Achievement.EventType.SUCHAR_POSTED)

    assert cache.get(f"achievements_pending:{user.pk}") is None
