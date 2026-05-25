"""Tests for the achievement SSE stream endpoint."""

from http import HTTPStatus

import pytest
from asgiref.sync import sync_to_async
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


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_requires_login(async_client):
    response = await async_client.get(reverse(STREAM_URL))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_content_type_is_event_stream(async_client):
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(STREAM_URL))
    assert "text/event-stream" in response.get("Content-Type", "")


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_sets_cache_control_no_cache(async_client):
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(STREAM_URL))
    assert response.get("Cache-Control") == "no-cache"


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_sets_x_accel_buffering_no(async_client):
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(STREAM_URL))
    assert response.get("X-Accel-Buffering") == "no"


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_sends_retry_when_no_pending(async_client):
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    await cache.adelete(f"achievements_pending:{user.pk}")

    response = await async_client.get(reverse(STREAM_URL))
    content = ""
    async for chunk in response.streaming_content:
        content += chunk.decode()
        if "retry:" in content:
            break
    assert "retry:" in content


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_sends_data_new_when_pending(async_client):
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    cache_key = f"achievements_pending:{user.pk}"
    await cache.aset(cache_key, True, timeout=60)  # noqa: FBT003

    response = await async_client.get(reverse(STREAM_URL))
    content = ""
    async for chunk in response.streaming_content:
        content += chunk.decode()
        if "data: new" in content:
            break
    assert "data: new" in content


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_does_not_send_data_without_cache_flag(async_client):
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    await cache.adelete(f"achievements_pending:{user.pk}")

    response = await async_client.get(reverse(STREAM_URL))
    content = ""
    async for chunk in response.streaming_content:
        content += chunk.decode()
        break
    assert "data: new" not in content
