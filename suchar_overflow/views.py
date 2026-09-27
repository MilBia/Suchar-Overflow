"""Project-wide error views."""

import logging
from typing import TYPE_CHECKING

from django.http import HttpResponse
from django.http import HttpResponseServerError
from django.views import defaults

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)

# No template loader, no base.html, no {% static %} / {% url %}: nothing here can
# fail the way the themed 500.html can.
FALLBACK_500_HTML = (
    '<!doctype html><html lang="pl"><head><meta charset="utf-8">'
    "<title>500</title></head><body><h1>500</h1>"
    "<p>Coś chrupnęło po stronie serwera. Odśwież za chwilę.</p>"
    "</body></html>"
)


def server_error(request: HttpRequest) -> HttpResponse:
    """``handler500`` that always returns a response (#442).

    Renders the themed ``500.html`` through Django's default view and falls
    back to a static page when that raises (e.g. a stale ``{% static %}`` under
    manifest storage, #436). Under ASGI an exception escaping ``handler500``
    leaves ``ASGIHandler.handle`` without sending ``request_finished``, so
    ``close_old_connections`` never runs and the request's Postgres connection
    stays open until cyclic GC happens to collect it — an idle worker never does.
    """
    try:
        return defaults.server_error(request)
    except Exception:
        logger.exception("Rendering 500.html failed; serving the static fallback")
        return HttpResponseServerError(FALLBACK_500_HTML)
