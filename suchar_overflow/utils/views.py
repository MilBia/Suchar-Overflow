"""Project-wide error views."""

import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.db import connection
from django.http import HttpResponse
from django.http import HttpResponseServerError
from django.http import JsonResponse
from django.utils.html import escape
from django.utils.translation import get_language
from django.utils.translation import gettext
from django.views import defaults
from django.views.decorators.cache import never_cache
from django_redis import get_redis_connection

from suchar_overflow.utils.db import releases_db_connections

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest

logger = logging.getLogger(__name__)


def fallback_500_html() -> str:
    """Static 500 page: no template loader, base.html, {% static %} or {% url %}.

    Nothing here can fail the way the themed 500.html can. It reuses that
    template's msgids, so both variants say the same thing in every language.
    """
    title = escape(gettext("500 — coś chrupnęło"))
    joke = escape(
        gettext(
            "Serwer usłyszał suchar i się rozsypał. Już to naprawiamy — odśwież za chwilę.",
        ),
    )
    return (
        f'<!doctype html><html lang="{escape(get_language() or "pl")}"><head>'
        f'<meta charset="utf-8"><title>{title}</title></head>'
        f"<body><h1>{title}</h1><p>{joke}</p></body></html>"
    )


# handler400/403/404 (#447). Under ASGI Django calls the error handlers in an
# executor thread that request_finished never cleans up, and 403/404 pages read
# request.user through context processors — see suchar_overflow.utils.db.
bad_request = releases_db_connections(defaults.bad_request)
permission_denied = releases_db_connections(defaults.permission_denied)
page_not_found = releases_db_connections(defaults.page_not_found)


@releases_db_connections
def server_error(request: HttpRequest) -> HttpResponse:
    """``handler500`` that always returns a response (#442).

    Renders the themed ``500.html`` through Django's default view and falls
    back to a static page when that raises (e.g. a stale ``{% static %}`` under
    manifest storage, #436). Under ASGI an exception escaping ``handler500``
    leaves ``ASGIHandler.handle`` without sending ``request_finished``, so
    ``close_old_connections`` never runs and the request's Postgres connection
    stays open until cyclic GC happens to collect it — an idle worker never does.
    Like the other handlers it also releases connections of the executor thread
    Django calls it in (#447).
    """
    try:
        return defaults.server_error(request)
    except Exception:
        logger.exception("Rendering 500.html failed; serving the static fallback")
        return HttpResponseServerError(fallback_500_html())


@releases_db_connections
def check_database() -> None:
    """``SELECT 1`` on the default connection; raises when the database is unreachable.

    Run in the request's thread via ``sync_to_async``; the wrapper closes the
    connection afterwards when it is obsolete (``CONN_MAX_AGE = 0``), so a probe
    every few seconds leaves nothing behind (#434, #447).
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def check_cache() -> None:
    """``PING`` on the raw Redis connection; raises when Redis is unreachable.

    Not ``cache.get``: the cache runs with ``IGNORE_EXCEPTIONS`` (base.py), which
    would swallow the very error this check exists to report.
    """
    get_redis_connection("default").ping()


# name -> check; the key is the field in the response. #460 adds the RQ queue here.
HEALTH_CHECKS: dict[str, Callable[[], None]] = {
    "database": check_database,
    "cache": check_cache,
}


@never_cache
async def healthz(request: HttpRequest) -> JsonResponse:  # noqa: ARG001
    """Liveness/readiness probe for the container healthcheck and uptime monitors (#457).

    ``{"database": "ok"|"error", "cache": "ok"|"error"}`` with 200, or 503 when any
    check failed. Failures are logged here, never echoed to the (anonymous) caller.
    """
    results: dict[str, str] = {}
    for name, check in HEALTH_CHECKS.items():
        try:
            await sync_to_async(check)()
        except Exception:
            logger.exception("Health check %r failed", name)
            results[name] = "error"
        else:
            results[name] = "ok"
    healthy = all(value == "ok" for value in results.values())
    return JsonResponse(results, status=HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE)
