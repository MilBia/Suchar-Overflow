"""E2E tests for the dark/light theme toggle (project.js)."""

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_clicking_toggle_flips_theme_and_persists_to_localstorage(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clicking #theme-toggle switches the theme and writes it to localStorage."""
    page.goto(f"{live_server.url}/")

    initial_theme = page.evaluate("localStorage.getItem('theme') || 'light'")
    expected_theme = "dark" if initial_theme == "light" else "light"

    page.click("#theme-toggle")

    # The click handler sets the data-theme attribute and localStorage in the
    # same synchronous call, so once the (auto-retrying) attribute check
    # settles, localStorage is guaranteed to already be up to date too.
    expect(page.locator("html")).to_have_attribute("data-theme", expected_theme)
    stored = page.evaluate("localStorage.getItem('theme')")
    assert stored == expected_theme


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_theme_is_restored_after_page_reload(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Setting theme to dark then reloading keeps data-theme='dark' on <html>."""
    page.goto(f"{live_server.url}/")

    page.evaluate("localStorage.setItem('theme', 'dark')")
    page.reload()

    expect(page.locator("html")).to_have_attribute("data-theme", "dark")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_light_theme_is_restored_after_page_reload(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Setting theme to light then reloading keeps data-theme='light' on <html>."""
    page.goto(f"{live_server.url}/")

    page.evaluate("localStorage.setItem('theme', 'light')")
    page.reload()

    expect(page.locator("html")).to_have_attribute("data-theme", "light")
