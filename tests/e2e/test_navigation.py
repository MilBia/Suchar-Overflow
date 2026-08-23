"""E2E tests for navigation, modals, toasts, and the sort dropdown (project.js)."""

from typing import TYPE_CHECKING

import pytest

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
    page.wait_for_load_state("networkidle")

    menu = page.locator("#navbar-menu")
    assert "active" not in (menu.get_attribute("class") or "")

    page.click("#navbar-toggler")

    assert "active" in (menu.get_attribute("class") or "")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_mobile_nav_toggle_closes_menu(page: Page, live_server: LiveServer) -> None:
    """Clicking the hamburger button a second time removes .active."""
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{live_server.url}/")
    page.wait_for_load_state("networkidle")

    page.click("#navbar-toggler")
    assert "active" in (page.locator("#navbar-menu").get_attribute("class") or "")

    page.click("#navbar-toggler")
    assert "active" not in (page.locator("#navbar-menu").get_attribute("class") or "")


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
    page.wait_for_load_state("networkidle")

    modal = page.locator("#logoutModal")
    assert modal.evaluate("el => el.hidden") is True

    page.click("#logout-button")

    assert modal.evaluate("el => el.hidden") is False


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_logout_modal_closes_via_cancel_button(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clicking .modal-close inside the modal sets hidden back to true."""
    page.goto(f"{live_server.url}/")
    page.wait_for_load_state("networkidle")

    page.click("#logout-button")
    modal = page.locator("#logoutModal")
    assert modal.evaluate("el => el.hidden") is False

    # First .modal-close is the x button in the header.
    page.locator("#logoutModal .modal-close").first.click()

    assert modal.evaluate("el => el.hidden") is True


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_logout_modal_closes_on_overlay_click(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clicking the overlay backdrop (not the modal card) closes the modal."""
    page.goto(f"{live_server.url}/")
    page.wait_for_load_state("networkidle")

    page.click("#logout-button")

    # Click the top-left corner of the overlay — outside the inner .modal card.
    page.locator("#logoutModal").click(position={"x": 5, "y": 5})

    assert page.locator("#logoutModal").evaluate("el => el.hidden") is True


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
    page.wait_for_load_state("networkidle")

    dropdown = page.locator("#sortDropdown")
    assert "show" not in (dropdown.get_attribute("class") or "")

    page.locator("#sortDropdown .dropdown-trigger").click()

    assert "show" in (dropdown.get_attribute("class") or "")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_sort_dropdown_closes_on_outside_click(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clicking outside the sort dropdown removes .show."""
    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_load_state("networkidle")

    page.locator("#sortDropdown .dropdown-trigger").click()
    assert "show" in (page.locator("#sortDropdown").get_attribute("class") or "")

    # Click the page heading — well outside the dropdown.
    page.locator("h1").click()

    assert "show" not in (page.locator("#sortDropdown").get_attribute("class") or "")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_sort_dropdown_selecting_top_submits_form(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Selecting 'Top' from the sort dropdown navigates to ?sort=top."""
    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_load_state("networkidle")

    page.locator("#sortDropdown .dropdown-trigger").click()
    page.locator("#sortDropdown .dropdown-item[data-value='top']").click()

    page.wait_for_url(f"{live_server.url}/suchary/**")
    assert "sort=top" in page.url
