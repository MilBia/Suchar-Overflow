"""Regression guard for #442 — a failing 500 page must not strand DB connections.

Under ASGI, `ASGIHandler.handle` sends `request_finished` (whose receiver
`close_old_connections` closes the request's Postgres connection) only after a
response went out. When `handler500` itself raises — as Django's default one did
under manifest storage while `base.html` held a stale `{% static %}` (#436) —
the exception escapes the handler, no response is sent and the connection is
left open in the dead per-request thread until cyclic GC collects it. Measured
before the fix: 50 concurrent failing requests left 50 connections open, still
50 after 5 s idle, 0 only after `gc.collect()`.

`suchar_overflow.views.server_error` falls back to a static page, so a response
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
from django.conf import settings as django_settings
from django.core.asgi import get_asgi_application
from django.db.backends.signals import connection_created
from django.test import Client
from django.urls import reverse

from suchar_overflow.conftest import make_user
from suchar_overflow.views import FALLBACK_500_HTML

if TYPE_CHECKING:
    from pathlib import Path

    from asgiref.typing import ASGIReceiveEvent
    from asgiref.typing import ASGISendEvent
    from django.core.handlers.asgi import ASGIHandler
    from django.db.backends.base.base import BaseDatabaseWrapper
    from pytest_django.fixtures import Settings as SettingsWrapper

_REQUESTS = 3


def _login_session_cookie() -> str:
    client = Client()
    client.force_login(make_user("handler500-probe"))
    return client.cookies[django_settings.SESSION_COOKIE_NAME].value


async def _get(app: ASGIHandler, cookie: str) -> tuple[int | None, bytes]:
    path = reverse("home")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"cookie", f"{django_settings.SESSION_COOKIE_NAME}={cookie}".encode()),
        ],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }
    request_sent = False
    status: int | None = None
    body = b""

    async def receive() -> ASGIReceiveEvent:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()  # never disconnects
        raise AssertionError  # pragma: no cover

    async def send(message: ASGISendEvent) -> None:
        nonlocal status, body
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            body += message.get("body", b"")

    await app(scope, receive, send)  # type: ignore[arg-type]
    return status, body


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_failing_500_page_still_releases_db_connections(
    settings: SettingsWrapper,
    tmp_path: Path,
) -> None:
    cookie = await sync_to_async(_login_session_cookie)()
    settings.DEBUG = False
    # A manifest storage with no manifest: every {% static %} raises ValueError,
    # in the page and in the themed 500.html alike — the #436 failure mode.
    static_root = tmp_path / "static"
    static_root.mkdir()  # WhiteNoise warns about a missing STATIC_ROOT
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
        # Without the fallback _get raises (the exception escapes the handler);
        # collect that instead so the connection check below still runs.
        results = await asyncio.wait_for(
            asyncio.gather(
                *(_get(app, cookie) for _ in range(_REQUESTS)),
                return_exceptions=True,
            ),
            timeout=10,
        )
    finally:
        connection_created.disconnect(record)

    # Not vacuous: each request did open a connection (session lookup).
    assert len({id(conn) for conn in opened}) >= _REQUESTS
    assert all(conn.connection is None for conn in opened)
    fallback = (HTTPStatus.INTERNAL_SERVER_ERROR, FALLBACK_500_HTML.encode())
    assert results == [fallback] * _REQUESTS
