"""Tests for the achievement SSE stream endpoint."""

from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse

User = get_user_model()

STREAM_URL = "achievements:stream"


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_stream_requires_login(client):
    response = client.get(reverse(STREAM_URL))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


# ---------------------------------------------------------------------------
# Content-type and headers
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_stream_content_type_is_event_stream(client):
    user = make_user("u1")
    client.force_login(user)
    response = client.get(reverse(STREAM_URL))
    assert "text/event-stream" in response.get("Content-Type", "")


@pytest.mark.django_db
def test_stream_sets_cache_control_no_cache(client):
    user = make_user("u1")
    client.force_login(user)
    response = client.get(reverse(STREAM_URL))
    assert response.get("Cache-Control") == "no-cache"


@pytest.mark.django_db
def test_stream_sets_x_accel_buffering_no(client):
    user = make_user("u1")
    client.force_login(user)
    response = client.get(reverse(STREAM_URL))
    assert response.get("X-Accel-Buffering") == "no"


# ---------------------------------------------------------------------------
# Response body
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_stream_sends_retry_when_no_pending(client):
    """Without a pending cache flag, the response must contain retry directive."""
    user = make_user("u1")
    client.force_login(user)
    cache.delete(f"achievements_pending:{user.pk}")

    response = client.get(reverse(STREAM_URL))
    content = b"".join(response.streaming_content).decode()
    assert "retry:" in content


@pytest.mark.django_db
def test_stream_sends_data_new_when_pending(client):
    """With a pending cache flag set, the response must emit 'data: new'."""
    user = make_user("u1")
    client.force_login(user)
    cache.set(f"achievements_pending:{user.pk}", value=True, timeout=60)

    response = client.get(reverse(STREAM_URL))
    content = b"".join(response.streaming_content).decode()
    assert "data: new" in content


@pytest.mark.django_db
def test_stream_does_not_send_data_without_cache_flag(client):
    user = make_user("u1")
    client.force_login(user)
    cache.delete(f"achievements_pending:{user.pk}")

    response = client.get(reverse(STREAM_URL))
    content = b"".join(response.streaming_content).decode()
    assert "data: new" not in content
