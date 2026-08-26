"""E2E tests for navigation, modals, toasts, and the sort dropdown (project.js)."""

import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

# ---------------------------------------------------------------------------
# Mobile navigation toggle
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_mobile_nav_toggle_opens_menu(page: Page, live_server: LiveServer) -> None:
    """Clicking the hamburger button adds .active to #navbar-menu."""
    # Use a narrow viewport so the hamburger button is actually visible.
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{live_server.url}/")

    menu = page.locator("#navbar-menu")
    expect(menu).not_to_have_class(re.compile(r"\bactive\b"))

    page.click("#navbar-toggler")

    expect(menu).to_have_class(re.compile(r"\bactive\b"))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_mobile_nav_toggle_closes_menu(page: Page, live_server: LiveServer) -> None:
    """Clicking the hamburger button a second time removes .active."""
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{live_server.url}/")

    menu = page.locator("#navbar-menu")
    page.click("#navbar-toggler")
    expect(menu).to_have_class(re.compile(r"\bactive\b"))

    page.click("#navbar-toggler")
    expect(menu).not_to_have_class(re.compile(r"\bactive\b"))


# ---------------------------------------------------------------------------
# Logout modal
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_logout_modal_opens_on_button_click(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clicking #logout-button removes the hidden attribute from #logoutModal."""
    page.goto(f"{live_server.url}/")

    modal = page.locator("#logoutModal")
    expect(modal).to_be_hidden()

    page.click("#logout-button")

    expect(modal).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_logout_modal_closes_via_cancel_button(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clicking .modal-close inside the modal sets hidden back to true."""
    page.goto(f"{live_server.url}/")

    page.click("#logout-button")
    modal = page.locator("#logoutModal")
    expect(modal).to_be_visible()

    # First .modal-close is the x button in the header.
    page.locator("#logoutModal .modal-close").first.click()

    expect(modal).to_be_hidden()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_logout_modal_closes_on_overlay_click(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clicking the overlay backdrop (not the modal card) closes the modal."""
    page.goto(f"{live_server.url}/")

    page.click("#logout-button")

    # Click the top-left corner of the overlay — outside the inner .modal card.
    page.locator("#logoutModal").click(position={"x": 5, "y": 5})

    expect(page.locator("#logoutModal")).to_be_hidden()


# ---------------------------------------------------------------------------
# Toast manual close
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_toast_manual_close_removes_it_from_dom(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clicking a toast's close button removes it from the DOM."""
    page.goto(f"{live_server.url}/")
    # Wait until project.js has finished registering window.showToast.
    page.wait_for_function("typeof window.showToast === 'function'")

    # Inject a non-persistent toast via the public helper.
    page.evaluate("window.showToast('Test message', 'Test', 'success', false)")

    toast = page.locator("#toast-container .toast").last
    toast.wait_for(state="attached")

    toast.locator(".btn-close").click()

    # After the CSS transition the toast is removed from the DOM entirely.
    toast.wait_for(state="detached", timeout=3000)


# ---------------------------------------------------------------------------
# Sort dropdown (suchary list)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_sort_dropdown_opens_on_trigger_click(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clicking the sort dropdown trigger adds .show to #sortDropdown."""
    page.goto(f"{live_server.url}/suchary/")

    dropdown = page.locator("#sortDropdown")
    expect(dropdown).not_to_have_class(re.compile(r"\bshow\b"))

    page.locator("#sortDropdown .dropdown-trigger").click()

    expect(dropdown).to_have_class(re.compile(r"\bshow\b"))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_sort_dropdown_closes_on_outside_click(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clicking outside the sort dropdown removes .show."""
    page.goto(f"{live_server.url}/suchary/")

    dropdown = page.locator("#sortDropdown")
    page.locator("#sortDropdown .dropdown-trigger").click()
    expect(dropdown).to_have_class(re.compile(r"\bshow\b"))

    # Click the page heading — well outside the dropdown.
    page.locator("h1").click()

    expect(dropdown).not_to_have_class(re.compile(r"\bshow\b"))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_sort_dropdown_selecting_top_submits_form(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Selecting 'Top' from the sort dropdown navigates to ?sort=top."""
    page.goto(f"{live_server.url}/suchary/")

    page.locator("#sortDropdown .dropdown-trigger").click()
    page.locator("#sortDropdown .dropdown-item[data-value='top']").click()

    page.wait_for_url(f"{live_server.url}/suchary/**")
    assert "sort=top" in page.url
