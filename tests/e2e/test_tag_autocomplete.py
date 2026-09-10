"""E2E tests for the tag autocomplete in the suchar form (suchar_form.js)."""

import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Tag

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.users.models import User as UserModel


def _tag_on_published_suchar(name: str, slug: str, author: UserModel) -> Tag:
    """Create a Tag and attach it to a published suchar.

    The suggestion endpoint only returns tags used on at least one published
    suchar (#389), so a bare ``Tag.objects.create`` is invisible to it.
    """
    tag = Tag.objects.create(name=name, slug=slug)
    suchar = Suchar.objects.create(text=f"joke {slug}", author=author)
    suchar.tags.add(tag)
    return tag


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_typing_shows_matching_tag_suggestions(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    """Typing ≥2 chars in the tags input triggers the API and shows a dropdown."""
    _tag_on_published_suchar("programowanie", "programowanie", e2e_user)
    _tag_on_published_suchar("python", "python", e2e_user)

    page.goto(f"{live_server.url}/suchary/add/")

    tags_input = page.locator("#id_tags_input")
    tags_input.click()
    # delay=60ms spaces keystrokes so the debounce (300ms) fires after the last key
    tags_input.type("pr", delay=60)

    # Wait for the dropdown wrapper to get the "show" class
    page.locator("#tags-dropdown.show").wait_for(timeout=2000)

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
@pytest.mark.usefixtures("login")
def test_clicking_suggestion_inserts_tag_and_closes_dropdown(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    """Clicking a suggestion inserts the tag name and hides the dropdown."""
    _tag_on_published_suchar("it", "it", e2e_user)

    page.goto(f"{live_server.url}/suchary/add/")

    tags_input = page.locator("#id_tags_input")
    tags_input.click()
    tags_input.type("it", delay=60)

    dropdown = page.locator("#tags-dropdown")
    page.locator("#tags-dropdown.show").wait_for(timeout=2000)

    page.locator("#tags-suggestions .dropdown-item").first.click()

    # Dropdown should close
    expect(dropdown).not_to_have_class(re.compile(r"\bshow\b"))
    # The inserted tag name should appear in the input value
    expect(tags_input).to_have_value(re.compile(r"it"))
