"""E2E tests for the dark/light theme toggle (project.js)."""

import pytest


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_clicking_toggle_flips_theme_and_persists_to_localstorage(page, live_server):
    """Clicking #theme-toggle switches the theme and writes it to localStorage."""
    page.goto(f"{live_server.url}/")
    page.wait_for_load_state("networkidle")

    initial_theme = page.evaluate("localStorage.getItem('theme') || 'light'")
    expected_theme = "dark" if initial_theme == "light" else "light"

    page.click("#theme-toggle")

    stored = page.evaluate("localStorage.getItem('theme')")
    html_attr = page.evaluate("document.documentElement.getAttribute('data-theme')")

    assert stored == expected_theme
    assert html_attr == expected_theme


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_theme_is_restored_after_page_reload(page, live_server):
    """Setting theme to dark then reloading keeps data-theme='dark' on <html>."""
    page.goto(f"{live_server.url}/")
    page.wait_for_load_state("networkidle")

    page.evaluate("localStorage.setItem('theme', 'dark')")
    page.reload()
    page.wait_for_load_state("networkidle")

    html_attr = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert html_attr == "dark"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_light_theme_is_restored_after_page_reload(page, live_server):
    """Setting theme to light then reloading keeps data-theme='light' on <html>."""
    page.goto(f"{live_server.url}/")
    page.wait_for_load_state("networkidle")

    page.evaluate("localStorage.setItem('theme', 'light')")
    page.reload()
    page.wait_for_load_state("networkidle")

    html_attr = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert html_attr == "light"
