"""Regression guard for #442 — a failing 500 page must not strand DB connections.

Under ASGI, `ASGIHandler.handle` sends `request_finished` (whose receiver
`close_old_connections` closes the request's Postgres connection) only after a
response went out. When `handler500` itself raises — as Django's default one did
under manifest storage while `base.html` held a stale `{% static %}` (#436) —
the exception escapes the handler, no response is sent and the connection is
left open in the dead per-request thread until cyclic GC collects it. Measured
before the fix: 50 concurrent failing requests left 50 connections open, still
50 after 5 s idle, 0 only after `gc.collect()`.

`suchar_overflow.utils.views.server_error` falls back to a static page, so a response
always goes out. The test drives `get_asgi_application()` directly, because
`AsyncClient` has no per-request `ThreadSensitiveContext` (see #434), and
records connections through `connection_created`: holding the wrappers keeps
them reachable, so GC cannot close a leaked one behind the assertion's back.
"""

import asyncio
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from asgiref.sync import sync_to_async
from django.core.asgi import get_asgi_application
from django.db.backends.signals import connection_created
from django.urls import reverse

from suchar_overflow.utils.views import fallback_500_html
from tests.asgi_client import asgi_get
from tests.asgi_client import login_session_cookie

if TYPE_CHECKING:
    from pathlib import Path

    from django.db.backends.base.base import BaseDatabaseWrapper
    from pytest_django.fixtures import Settings as SettingsWrapper

_REQUESTS = 3


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_failing_500_page_still_releases_db_connections(
    settings: SettingsWrapper,
    tmp_path: Path,
) -> None:
    cookie = await sync_to_async(login_session_cookie)("handler500-probe")
    settings.DEBUG = False
    # A manifest storage with no manifest: every {% static %} raises ValueError,
    # in the page and in the themed 500.html alike — the #436 failure mode.
    static_root = tmp_path / "static"
    static_root.mkdir()
    settings.STATIC_ROOT = str(static_root)
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
        },
    }
    opened: list[BaseDatabaseWrapper] = []

    def record(
        sender: object,  # noqa: ARG001
        connection: BaseDatabaseWrapper,
        **kwargs: object,  # noqa: ARG001
    ) -> None:
        opened.append(connection)

    app = get_asgi_application()
    connection_created.connect(record, weak=False)
    try:
        # Without the fallback asgi_get raises (the exception escapes the handler);
        # collect that instead so the connection check below still runs.
        results = await asyncio.wait_for(
            asyncio.gather(
                *(asgi_get(app, reverse("home"), cookie) for _ in range(_REQUESTS)),
                return_exceptions=True,
            ),
            timeout=10,
        )
    finally:
        connection_created.disconnect(record)

    # Not vacuous: each request did open a connection (session lookup).
    assert len({id(conn) for conn in opened}) >= _REQUESTS
    assert all(conn.connection is None for conn in opened)
    fallback = (HTTPStatus.INTERNAL_SERVER_ERROR, fallback_500_html().encode())
    assert results == [fallback] * _REQUESTS
