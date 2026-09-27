"""``releases_db_connections`` in isolation (#447).

The end-to-end guard — every project error path under ``ASGIHandler`` leaves no
executor-thread connection open — stays in
``tests/test_error_handler_db_connections.py``.
"""

import time
from typing import TYPE_CHECKING

import pytest
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory

from suchar_overflow.utils.db import releases_db_connections

if TYPE_CHECKING:
    from django.http import HttpRequest


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
