"""E2E tests for the tag autocomplete in the suchar form (suchar_form.js)."""

import pytest

from suchar_overflow.suchary.models import Tag


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_typing_shows_matching_tag_suggestions(page, live_server, login):
    """Typing ≥2 chars in the tags input triggers the API and shows a dropdown."""
    Tag.objects.create(name="programowanie", slug="programowanie")
    Tag.objects.create(name="python", slug="python")

    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

    tags_input = page.locator("#id_tags_input")
    tags_input.click()
    # delay=60ms spaces keystrokes so the debounce (300ms) fires after the last key
    tags_input.type("pr", delay=60)

    # Wait for the dropdown wrapper to get the "show" class
    page.wait_for_function(
        "document.getElementById('tags-dropdown').classList.contains('show')",
        timeout=2000,
    )

    # Wait for the specific text to appear — avoids a race between the dropdown
    # becoming visible and the async API response populating item text.
    page.wait_for_selector(
        "#tags-suggestions .dropdown-item",
        state="visible",
    )
    items = page.locator("#tags-suggestions .dropdown-item")
    assert items.count() >= 1
    assert items.first.inner_text() == "programowanie"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_clicking_suggestion_inserts_tag_and_closes_dropdown(page, live_server, login):
    """Clicking a suggestion inserts the tag name and hides the dropdown."""
    Tag.objects.create(name="it", slug="it")

    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

    tags_input = page.locator("#id_tags_input")
    tags_input.click()
    tags_input.type("it", delay=60)

    page.wait_for_function(
        "document.getElementById('tags-dropdown').classList.contains('show')",
        timeout=2000,
    )

    page.locator("#tags-suggestions .dropdown-item").first.click()

    # Dropdown should close
    assert not page.locator("#tags-dropdown").evaluate(
        "el => el.classList.contains('show')",
    )
    # The inserted tag name should appear in the input value
    assert "it" in tags_input.input_value()
