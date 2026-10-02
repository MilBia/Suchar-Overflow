from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest  # noqa: TC002
from django.http import HttpResponse  # noqa: TC002
from django.utils.translation import gettext
from ninja import NinjaAPI
from ninja import Router
from ninja.operation import Operation  # noqa: TC002


class SucharOverflowAPI(NinjaAPI):
    """``NinjaAPI`` whose operation URL names are unique across routers (#458)."""

    def get_operation_url_name(self, operation: Operation, router: Router) -> str:
        """``<router tag>_<view function>``, e.g. ``suchary_vote_suchar``.

        Ninja's default is the bare function name, which collides as soon as two
        routers share one. Every ``Router`` therefore carries ``tags=[...]``; the
        namespace stays ``api``, so ``reverse("api:suchary_vote_suchar")`` works.
        """
        if not router.tags:
            msg = f"Router of {operation.view_func.__name__} needs tags=[...] to name its URLs (#458)."
            raise ImproperlyConfigured(msg)
        return f"{router.tags[0]}_{operation.view_func.__name__}"


api = SucharOverflowAPI(
    title="Suchar Overflow API",
    version="1.0.0",
    description="API for accessing and interacting with Suchar Overflow content.",
    urls_namespace="api",
    docs_url="/docs" if settings.API_ENABLE_DOCS else None,
)


@api.exception_handler(PermissionDenied)
def permission_denied(request: HttpRequest, exc: PermissionDenied) -> HttpResponse:  # noqa: ARG001
    return api.create_response(request, {"message": gettext("Brak uprawnień do wykonania tej operacji.")}, status=403)


api.add_router("/suchary/", "suchar_overflow.suchary.api.router")
api.add_router("/achievements/", "suchar_overflow.achievements.api.router")
