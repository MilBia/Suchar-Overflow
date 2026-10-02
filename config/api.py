from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest  # noqa: TC002
from django.http import HttpResponse  # noqa: TC002
from django.utils.translation import gettext
from ninja import NinjaAPI
from ninja import Router
from ninja.operation import Operation  # noqa: TC002
from ninja.security import HttpBearer
from ninja.security import django_auth

from suchar_overflow.users.models import AuthToken
from suchar_overflow.users.models import User


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


class ApiToken(HttpBearer):
    """``Authorization: Bearer <token>`` for scripts and integrations (#459).

    Returning ``None`` for an unknown (or inactive-user) token makes ninja try the next
    authenticator and finally answer 401. A bearer request never touches a session, so
    it is exempt from the CSRF check ``django_auth`` applies to cookie sessions.
    """

    def authenticate(self, request: HttpRequest, token: str) -> User | None:
        auth_token = (
            AuthToken.objects.select_related("user")
            .filter(token_hash=AuthToken.hash_token(token), user__is_active=True)
            .first()
        )
        if auth_token is None:
            return None
        request.user = auth_token.user
        return auth_token.user


api = SucharOverflowAPI(
    title="Suchar Overflow API",
    version="1.0.0",
    description="API for accessing and interacting with Suchar Overflow content.",
    urls_namespace="api",
    # Bearer token first (scripts), then the Django session (the frontend, CSRF-checked).
    # Public endpoints opt out explicitly with ``auth=None``.
    auth=[ApiToken(), django_auth],
    docs_url="/docs" if settings.API_ENABLE_DOCS else None,
)


@api.exception_handler(PermissionDenied)
def permission_denied(request: HttpRequest, exc: PermissionDenied) -> HttpResponse:  # noqa: ARG001
    return api.create_response(request, {"message": gettext("Brak uprawnień do wykonania tej operacji.")}, status=403)


api.add_router("/suchary/", "suchar_overflow.suchary.api.router")
api.add_router("/achievements/", "suchar_overflow.achievements.api.router")
api.add_router("/users/", "suchar_overflow.users.api.router")
