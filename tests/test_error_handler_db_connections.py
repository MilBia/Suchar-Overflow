"""Regression guard for #447: error paths must not strand executor DB connections.

Under ASGI, Django's async ``convert_exception_to_response`` runs
``response_for_exception`` through ``sync_to_async(thread_sensitive=False)``,
and ``get_response_async`` runs ``log_response`` for every >= 400 response the
same way. Both land in a thread of the loop's default executor (``asyncio_N``),
not the request's ``ThreadSensitiveContext`` thread. ``request_finished`` →
``close_old_connections`` only runs in the latter, so a connection that the
error handler (404/403 pages read ``request.user`` through context processors)
or ``AdminEmailHandler`` (``str(request.user)`` in the report) opened in
``asyncio_N`` was never closed. Nothing health-checked it either, so after a
backend restart every later error page served from that thread was a 500.

The project's handlers (``config.urls``) and ``mail_admins`` handler
(``suchar_overflow.log.AdminEmailHandler``) release connections on entry and on
exit. The ASGI test drives ``get_asgi_application()`` directly (``AsyncClient``
has no per-request thread, see ``tests/asgi_client.py``) and records every
connection with the name of the thread that opened it.
"""

import asyncio
import logging
import threading
import time
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from asgiref.sync import sync_to_async
from django.core.asgi import get_asgi_application
from django.db import connection
from django.db.backends.signals import connection_created
from django.http import HttpResponse
from django.test import RequestFactory

from config import urls as config_urls
from suchar_overflow.db import releases_db_connections
from suchar_overflow.log import AdminEmailHandler
from tests.asgi_client import asgi_get
from tests.asgi_client import login_session_cookie

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper
    from django.http import HttpRequest
    from pytest_django.fixtures import Settings as SettingsWrapper

_REQUESTS = 3


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("path", "status"),
    [
        # handler404 → 404.html → achievements_bell → request.user
        ("/nope-447/", HTTPStatus.NOT_FOUND),
        # handler403 → 403.html → context processors → request.user
        ("/deny/", HTTPStatus.FORBIDDEN),
        # 500.html renders without a request; log_response → mail_admins reads it
        ("/raise/", HTTPStatus.INTERNAL_SERVER_ERROR),
        # no exception at all: get_response_async's own log_response
        ("/return-500/", HTTPStatus.INTERNAL_SERVER_ERROR),
    ],
)
async def test_error_paths_release_executor_thread_connections(
    settings: SettingsWrapper,
    path: str,
    status: HTTPStatus,
) -> None:
    cookie = await sync_to_async(login_session_cookie)("error-handler-probe")
    settings.DEBUG = False
    settings.ROOT_URLCONF = "tests.error_probe_urls"
    # AdminEmailHandler skips building the report (and reading request.user)
    # when there is nobody to mail; ADMINS is empty unless DJANGO_ADMINS is set (#453).
    settings.ADMINS = ["admin@example.com"]
    opened: list[tuple[BaseDatabaseWrapper, str]] = []

    def record(
        sender: object,  # noqa: ARG001
        connection: BaseDatabaseWrapper,
        **kwargs: object,  # noqa: ARG001
    ) -> None:
        opened.append((connection, threading.current_thread().name))

    # Production puts this class on the "django" logger (test_logging_settings);
    # a settings.LOGGING override would not reconfigure logging, so attach it.
    # After get_asgi_application(): its django.setup() re-runs dictConfig, which
    # resets the "django" logger's handlers.
    app = get_asgi_application()
    mail_admins = AdminEmailHandler()
    mail_admins.setLevel(logging.ERROR)
    django_logger = logging.getLogger("django")
    django_logger.addHandler(mail_admins)
    connection_created.connect(record, weak=False)
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(asgi_get(app, path, cookie) for _ in range(_REQUESTS))),
            timeout=10,
        )
    finally:
        connection_created.disconnect(record)
        django_logger.removeHandler(mail_admins)

    assert [result_status for result_status, _ in results] == [status] * _REQUESTS
    # Not vacuous: the error path itself opened connections off the request thread.
    executor_threads = {name for _, name in opened if name.startswith("asyncio_")}
    assert executor_threads, opened
    still_open = [(name, conn) for conn, name in opened if conn.connection is not None]
    assert still_open == []


@pytest.mark.django_db(transaction=True)
def test_wrapped_handler_resets_a_stale_connection_before_running() -> None:
    # An executor thread's connection outlives the request; a killed backend or
    # an expired CONN_MAX_AGE must be dropped before the handler reuses it.
    connection.ensure_connection()
    connection.close_at = time.monotonic() - 1
    seen_open: list[bool] = []

    @releases_db_connections
    def handler(request: HttpRequest) -> HttpResponse:  # noqa: ARG001
        seen_open.append(connection.connection is not None)
        return HttpResponse()

    handler(RequestFactory().get("/"))

    assert seen_open == [False]


@pytest.mark.django_db(transaction=True)
def test_wrapped_handler_closes_what_it_opened() -> None:
    connection.close()

    @releases_db_connections
    def handler(request: HttpRequest) -> HttpResponse:  # noqa: ARG001
        connection.ensure_connection()
        return HttpResponse()

    handler(RequestFactory().get("/"))

    assert connection.connection is None


@pytest.mark.django_db
def test_wrapped_handler_leaves_an_atomic_block_alone() -> None:
    # A plain django_db test runs inside a transaction; closing would break it.
    assert connection.in_atomic_block
    connection.ensure_connection()

    @releases_db_connections
    def handler(request: HttpRequest) -> HttpResponse:  # noqa: ARG001
        return HttpResponse()

    handler(RequestFactory().get("/"))

    assert connection.connection is not None
    assert connection.in_atomic_block


def test_project_error_handlers_are_wrapped() -> None:
    # resolve_error_handler reads these names from the root URLconf; a bare
    # django.views.defaults view here would skip the release (#447).
    for name in ("handler400", "handler403", "handler404", "handler500"):
        handler = getattr(config_urls, name)
        assert getattr(handler, "releases_db_connections", False), name
