"""Extra middleware tests: API path bypass."""

from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.cache import cache

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement

User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


def make_achievement(slug="mw-extra-ach"):
    return Achievement.objects.create(
        slug=slug,
        name=slug,
        description="desc",
        icon_content="<svg/>",
        category=Achievement.Category.LIFETIME,
        event_type=Achievement.EventType.SUCHAR_POSTED,
        metric=Achievement.Metric.COUNT_SUCHAR,
        threshold=99,  # high threshold — engine won't auto-award
    )


# ---------------------------------------------------------------------------
# API path bypass
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_middleware_skips_api_routes(client):
    """Requests to /api/… must not trigger middleware's notification delivery.

    We use a neutral API endpoint (/api/suchary/tags) that never touches
    achievements, so only the middleware could clear the cache or mark is_seen.
    If the cache key and is_seen are untouched after the request, the middleware
    correctly bypassed the API route.
    """
    user = make_user("u1")
    ach = make_achievement("mw-api-bypass")
    ua = UserAchievement.objects.create(user=user, achievement=ach, is_seen=False)
    cache.set(f"achievements_pending:{user.pk}", value=True, timeout=60)

    client.force_login(user)
    # Use a neutral API endpoint that never processes achievements
    response = client.get("/api/suchary/tags")
    assert response.status_code == HTTPStatus.OK

    # Middleware must have skipped — is_seen still False, cache still set
    ua.refresh_from_db()
    assert ua.is_seen is False
    assert cache.get(f"achievements_pending:{user.pk}") is True


@pytest.mark.django_db
def test_middleware_runs_on_non_api_routes(client):
    """Requests to non-API routes must still deliver notifications."""
    user = make_user("u2")
    ach = make_achievement("mw-non-api")
    ua = UserAchievement.objects.create(user=user, achievement=ach, is_seen=False)
    cache.set(f"achievements_pending:{user.pk}", value=True, timeout=60)

    client.force_login(user)
    response = client.get("/suchary/", follow=True)
    assert response.status_code == HTTPStatus.OK

    # Middleware clears the cache key but does not send toasts or mark is_seen.
    ua.refresh_from_db()
    assert ua.is_seen is False
    assert cache.get(f"achievements_pending:{user.pk}") is None


# ---------------------------------------------------------------------------
# Cache cleared even when no unseen achievements in DB
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cache_cleared_even_when_no_unseen_achievements(client):
    """Cache flag is cleared even when DB has no unseen achievements."""
    user = make_user("u3")
    cache.set(f"achievements_pending:{user.pk}", value=True, timeout=60)

    client.force_login(user)
    client.get("/suchary/")

    assert cache.get(f"achievements_pending:{user.pk}") is None


# ---------------------------------------------------------------------------
# Messages not produced for anonymous user
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_middleware_produces_no_messages_for_anonymous(client):
    response = client.get("/suchary/", follow=True)
    msgs = [str(m) for m in get_messages(response.wsgi_request)]
    assert not any("Achievement Unlocked" in m for m in msgs)
