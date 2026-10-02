from django.http import HttpRequest  # noqa: TC002
from ninja import Router
from ninja import Schema

from suchar_overflow.users.models import User

router = Router(tags=["users"])


class MeResponse(Schema):
    username: str


@router.get("/me", response=MeResponse)
def me(request: HttpRequest) -> User:
    """The authenticated user (session or bearer token)."""
    user = request.user
    assert isinstance(user, User)  # the API default auth already rejects anonymous requests
    return user
