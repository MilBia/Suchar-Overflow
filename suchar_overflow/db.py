"""DB connection housekeeping for code that runs off the request's thread (#447)."""

import functools
from typing import TYPE_CHECKING

from django.db import connections

if TYPE_CHECKING:
    from collections.abc import Callable


def release_stale_db_connections() -> None:
    """``close_old_connections()`` for this thread, skipping atomic blocks.

    Under ASGI, Django runs the error handlers and ``log_response`` in a thread of
    the loop's default executor (``sync_to_async(thread_sensitive=False)``).
    ``request_started``/``request_finished`` fire only in the request's own thread,
    so nothing else closes a connection opened there or drops one whose backend
    died. Same rules as those signals: obsolete (``CONN_MAX_AGE``) or unusable
    connections are closed, healthy young ones kept. Connections inside an atomic
    block (a non-``transaction=True`` pytest-django test) are left alone, since
    closing would break the transaction.
    """
    for conn in connections.all(initialized_only=True):
        if not conn.in_atomic_block:
            conn.close_if_unusable_or_obsolete()


def releases_db_connections[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Run ``func`` between two ``release_stale_db_connections()`` calls."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        release_stale_db_connections()
        try:
            return func(*args, **kwargs)
        finally:
            release_stale_db_connections()

    wrapper.releases_db_connections = True  # type: ignore[attr-defined]
    return wrapper
