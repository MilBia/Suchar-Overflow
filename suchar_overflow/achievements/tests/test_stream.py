"""Tests for the achievement SSE stream endpoint."""

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db import connections
from django.urls import reverse

from suchar_overflow.achievements.cache import pending_cache_key
from suchar_overflow.achievements.cache import toast_cache_key
from suchar_overflow.conftest import make_user

if TYPE_CHECKING:
    from django.test import AsyncClient
    from pytest_django.fixtures import Settings as SettingsWrapper

STREAM_URL = "achievements:stream"


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_requires_login(async_client: AsyncClient) -> None:
    response = await async_client.get(reverse(STREAM_URL))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_content_type_is_event_stream(async_client: AsyncClient) -> None:
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(STREAM_URL))
    assert "text/event-stream" in response.get("Content-Type", "")


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_sets_cache_control_no_cache(async_client: AsyncClient) -> None:
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(STREAM_URL))
    assert response.get("Cache-Control") == "no-cache"


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_sets_x_accel_buffering_no(async_client: AsyncClient) -> None:
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(STREAM_URL))
    assert response.get("X-Accel-Buffering") == "no"


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_sends_retry_when_no_pending(async_client: AsyncClient) -> None:
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    await cache.adelete(pending_cache_key(user.pk))

    response = await async_client.get(reverse(STREAM_URL))
    content = ""
    async for chunk in response.streaming_content:  # type: ignore[attr-defined]
        content += chunk.decode()
        if "retry:" in content:
            break
    assert "retry:" in content


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_sends_data_new_when_pending(async_client: AsyncClient) -> None:
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    cache_key = pending_cache_key(user.pk)
    await cache.aset(cache_key, True, timeout=60)  # noqa: FBT003

    response = await async_client.get(reverse(STREAM_URL))
    content = ""
    async for chunk in response.streaming_content:  # type: ignore[attr-defined]
        content += chunk.decode()
        if "data: new" in content:
            break
    assert "data: new" in content


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_does_not_send_data_without_cache_flag(
    async_client: AsyncClient,
) -> None:
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    await cache.adelete(pending_cache_key(user.pk))

    response = await async_client.get(reverse(STREAM_URL))
    content = ""
    async for chunk in response.streaming_content:  # type: ignore[attr-defined]
        content += chunk.decode()
        break
    assert "data: new" not in content


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_sends_data_toast_when_toast_pending(
    async_client: AsyncClient,
) -> None:
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    await cache.adelete(pending_cache_key(user.pk))
    await cache.aset(toast_cache_key(user.pk), True, timeout=60)  # noqa: FBT003

    response = await async_client.get(reverse(STREAM_URL))
    content = ""
    async for chunk in response.streaming_content:  # type: ignore[attr-defined]
        content += chunk.decode()
        if "data: toast" in content:
            break
    assert "data: toast" in content


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_stream_does_not_send_data_toast_without_flag(
    async_client: AsyncClient,
) -> None:
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)
    await cache.adelete(pending_cache_key(user.pk))
    await cache.adelete(toast_cache_key(user.pk))

    response = await async_client.get(reverse(STREAM_URL))
    content = ""
    async for chunk in response.streaming_content:  # type: ignore[attr-defined]
        content += chunk.decode()
        break
    assert "data: toast" not in content


def _default_connection_is_closed() -> bool:
    return connections["default"].connection is None


async def _assert_stream_holds_no_db_connection(async_client: AsyncClient) -> None:
    user = await sync_to_async(make_user)("u1")
    await async_client.aforce_login(user)

    response = await async_client.get(reverse(STREAM_URL))
    async for _chunk in response.streaming_content:  # type: ignore[attr-defined]
        # Checked inside the loop: breaking out closes the response, and its
        # request_finished -> close_old_connections would close the connection
        # anyway. Under AsyncClient there is no per-request ThreadSensitiveContext,
        # so the view, the middleware and this check all share sync_to_async's
        # one thread-sensitive executor thread — the thread that owns it.
        assert await sync_to_async(_default_connection_is_closed)()
        break


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_open_stream_releases_db_connection(async_client: AsyncClient) -> None:
    """An open SSE stream must not pin a Postgres connection (#434)."""
    await _assert_stream_holds_no_db_connection(async_client)


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_open_stream_releases_db_connection_after_session_save(
    async_client: AsyncClient,
    settings: SettingsWrapper,
) -> None:
    """The release must follow the middleware response phase, not the view (#434).

    SESSION_SAVE_EVERY_REQUEST makes SessionMiddleware write the session after
    the view returns — a connection closed in the view itself would be reopened.
    """
    settings.SESSION_SAVE_EVERY_REQUEST = True
    await _assert_stream_holds_no_db_connection(async_client)
