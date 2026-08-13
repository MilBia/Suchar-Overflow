import pytest

from suchar_overflow.users.models import User
from suchar_overflow.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def _media_storage(settings, tmpdir) -> None:
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user(db) -> User:
    return UserFactory.create()


def make_user(
    username: str,
    email: str | None = None,
    password: str = "password",  # noqa: S107
    *,
    is_active: bool = True,
) -> User:
    """Create a test user via UserFactory with an explicit, predictable username."""
    return UserFactory.create(
        username=username,
        email=email or f"{username}@example.com",
        password=password,
        is_active=is_active,
    )
