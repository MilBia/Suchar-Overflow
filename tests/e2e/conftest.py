from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from suchar_overflow.suchary.models import Suchar

if TYPE_CHECKING:
    from typing import Any

    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.suchary.models import Suchar as SucharModel
    from suchar_overflow.users.models import User as UserModel

User = get_user_model()

TEST_PASSWORD = "e2e-test-password-123"  # noqa: S105


@pytest.fixture(scope="session")
def browser_type_launch_args(
    browser_type_launch_args: dict[str, Any],
) -> dict[str, Any]:
    # Required in Docker/CI where kernel namespaces for sandboxing are restricted.
    return {
        **browser_type_launch_args,
        "args": ["--no-sandbox", "--disable-setuid-sandbox"],
    }


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 800},
        "locale": "pl-PL",
    }


@pytest.fixture
def e2e_user(db: None) -> UserModel:  # noqa: ARG001
    return User.objects.create_user(
        username="e2etestuser",
        email="e2e@test.example.com",
        password=TEST_PASSWORD,
    )


@pytest.fixture
def published_suchar(db: None, e2e_user: UserModel) -> SucharModel:  # noqa: ARG001
    return Suchar.objects.create(
        text="Dlaczego programiści nie lubią natury? Bo ma za dużo bugów.",
        author=e2e_user,
        published_at=timezone.now() - timedelta(minutes=5),
    )


@pytest.fixture(autouse=True)
def block_sse_stream(page: Page) -> None:
    """Abort SSE connections so the live_server thread never gets a BrokenPipe.

    project.js opens /achievements/stream/ for authenticated pages.  When the
    browser closes at test-end the live_server thread tries to clean up DB
    connections and hits pytest-django's DB-access guard.  Aborting the route
    before any navigation prevents that race entirely.
    """
    page.route("**/achievements/stream/", lambda route: route.abort())


@pytest.fixture
def login(page: Page, live_server: LiveServer, e2e_user: UserModel) -> Page:  # noqa: ARG001
    """Log in via the login form and return the page."""
    page.goto(f"{live_server.url}/accounts/login/")
    page.fill("input[name='username']", "e2etestuser")
    page.fill("input[name='password']", TEST_PASSWORD)
    page.click("button[type='submit']")
    page.wait_for_url(f"{live_server.url}/**")
    return page
