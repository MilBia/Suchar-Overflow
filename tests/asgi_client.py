"""Drive a real ``ASGIHandler`` in tests that care which thread did what.

``AsyncClient`` runs a request's sync code in one shared executor thread, with
no per-request ``ThreadSensitiveContext`` (see #434). So a connection-lifecycle
bug that depends on *which* thread opened a connection only shows up when
``get_asgi_application()`` is called directly, as ``asgi_get`` does.
"""

import asyncio
from typing import TYPE_CHECKING

from django.conf import settings as django_settings
from django.test import Client

from suchar_overflow.conftest import make_user

if TYPE_CHECKING:
    from asgiref.typing import ASGIReceiveEvent
    from asgiref.typing import ASGISendEvent
    from django.core.handlers.asgi import ASGIHandler


def login_session_cookie(username: str) -> str:
    """Session cookie value of a freshly created, logged-in user (sync, DB)."""
    client = Client()
    client.force_login(make_user(username))
    return client.cookies[django_settings.SESSION_COOKIE_NAME].value


async def asgi_get(
    app: ASGIHandler,
    path: str,
    cookie: str,
) -> tuple[int | None, bytes]:
    """GET ``path`` through ``app`` as the session ``cookie``; (status, body)."""
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
