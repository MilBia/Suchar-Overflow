"""URLconf for ``tests/test_error_handler_db_connections.py`` (#447).

The probe views fail *before* anything reads ``request.user``, so the only code
that can open a DB connection afterwards runs in the executor thread Django
hands errors to. The ``handler*`` names are re-exported from ``config.urls``:
``resolve_error_handler`` reads them from the active URLconf, and without them
Django's stock handlers would run and the test would bypass the project's.
"""

from typing import TYPE_CHECKING

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseServerError
from django.urls import path

from config.urls import handler400
from config.urls import handler403
from config.urls import handler404
from config.urls import handler500
from config.urls import urlpatterns as project_urlpatterns

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.http import HttpResponse

__all__ = ["handler400", "handler403", "handler404", "handler500", "urlpatterns"]


def raise_error(request: HttpRequest) -> HttpResponse:  # noqa: ARG001
    msg = "probe: view raised"
    raise RuntimeError(msg)


def return_error(request: HttpRequest) -> HttpResponse:  # noqa: ARG001
    return HttpResponseServerError("probe: view returned 500")


def deny(request: HttpRequest) -> HttpResponse:  # noqa: ARG001
    raise PermissionDenied


urlpatterns = [
    path("raise/", raise_error),
    path("return-500/", return_error),
    path("deny/", deny),
    # The error pages extend base.html, which reverses the project's URLs.
    *project_urlpatterns,
]
