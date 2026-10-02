from typing import TYPE_CHECKING

import pytest
from django.test import Client

from suchar_overflow.users.models import AuthToken
from suchar_overflow.users.tests.factories import UserFactory

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    import py
    from pytest_django.fixtures import Settings

    from suchar_overflow.users.models import User


@pytest.fixture(autouse=True)
def _media_storage(settings: Settings, tmpdir: py.path.local) -> None:
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user(db: None) -> User:  # noqa: ARG001
    return UserFactory.create()


@pytest.fixture
def api_token(user: User) -> str:
    """Clear-text bearer token of ``user`` (only its hash is stored, #459)."""
    return AuthToken.issue(user)[1]


@pytest.fixture
def api_client(api_token: str) -> Client:
    """Test client sending ``Authorization: Bearer <token>`` of the ``user`` fixture.

    Enforces CSRF like a browser would, so a passing request proves the bearer path
    needs none.
    """
    return Client(enforce_csrf_checks=True, headers={"Authorization": f"Bearer {api_token}"})


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


def run_enqueued_jobs(rq_queue: MagicMock) -> int:
    """Execute, in-process, every job the code under test passed to ``rq_queue.enqueue``.

    ``rq_queue`` is the autouse fixture from the root ``conftest.py``. Job options
    (``retry=`` ...) are dropped, as a worker would consume them; returns the job count.
    """
    calls = rq_queue.enqueue.call_args_list
    for call in calls:
        task, *args = call.args
        task(*args, **{key: value for key, value in call.kwargs.items() if key != "retry"})
    return len(calls)
