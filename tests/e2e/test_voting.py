"""E2E tests for the AJAX voting system (voting.js)."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.suchary.models import Suchar as SucharModel


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_authenticated_user_can_cast_funny_vote(
    page: Page,
    live_server: LiveServer,
    published_suchar: SucharModel,
) -> None:
    """Clicking the funny button increments the count and marks it active."""
    page.goto(f"{live_server.url}/suchary/")

    pk = published_suchar.pk
    funny_btn = page.locator(
        f"button.btn-vote[data-suchar-id='{pk}'][data-vote-type='funny']",
    )
    initial_count = int(funny_btn.locator(".vote-count").inner_text())

    funny_btn.click()

    # Wait for the API response to update the DOM
    page.wait_for_function(
        f"""
        parseInt(document.querySelector(
            "button.btn-vote[data-suchar-id='{pk}'][data-vote-type='funny'] .vote-count"
        ).textContent) !== {initial_count}
        """,
    )

    assert int(funny_btn.locator(".vote-count").inner_text()) == initial_count + 1
    assert funny_btn.get_attribute("aria-pressed") == "true"
    assert "active" in (funny_btn.get_attribute("class") or "")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_unauthenticated_vote_click_redirects_to_login(
    page: Page,
    live_server: LiveServer,
    published_suchar: SucharModel,
) -> None:
    """Anonymous user clicking a vote button is redirected to the login page."""
    page.goto(f"{live_server.url}/suchary/")

    pk = published_suchar.pk
    # Anonymous buttons carry data-anonymous="true"
    funny_btn = page.locator(
        f"button.btn-vote[data-suchar-id='{pk}'][data-vote-type='funny'][data-anonymous='true']",
    )
    funny_btn.click()

    page.wait_for_url(f"{live_server.url}/accounts/login/")
    assert "/accounts/login/" in page.url


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_author_dry_voting_own_suchar_shows_wink_toast(
    page: Page,
    live_server: LiveServer,
    published_suchar: SucharModel,
) -> None:
    """#299: the logged-in user authors ``published_suchar``; a dry vote on it
    is a self dry-vote, so the endpoint returns the wink text and voting.js
    surfaces it as a toast."""
    page.goto(f"{live_server.url}/suchary/")

    pk = published_suchar.pk
    dry_btn = page.locator(
        f"button.btn-vote[data-suchar-id='{pk}'][data-vote-type='dry']",
    )
    dry_btn.click()

    toast = page.locator("#toast-container .toast-body", has_text="Odwaga. Szacunek.")
    toast.wait_for(state="visible")
    assert "Odwaga. Szacunek." in toast.inner_text()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_clicking_active_vote_toggles_it_off(
    page: Page,
    live_server: LiveServer,
    published_suchar: SucharModel,
) -> None:
    """Clicking an active vote button a second time removes the active state."""
    pk = published_suchar.pk
    page.goto(f"{live_server.url}/suchary/")

    funny_btn = page.locator(
        f"button.btn-vote[data-suchar-id='{pk}'][data-vote-type='funny']",
    )

    # First click — vote cast, button becomes active
    funny_btn.click()
    page.wait_for_function(
        f"document.querySelector(\"button.btn-vote[data-suchar-id='{pk}'][data-vote-type='funny']\").classList.contains('active')",
    )

    # Second click — vote removed, button becomes inactive
    funny_btn.click()
    page.wait_for_function(
        f"!document.querySelector(\"button.btn-vote[data-suchar-id='{pk}'][data-vote-type='funny']\").classList.contains('active')",
    )

    assert funny_btn.get_attribute("aria-pressed") == "false"
