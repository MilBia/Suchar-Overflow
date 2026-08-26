"""E2E tests for the suchar form's live UI behaviors (suchar_form.js)."""

import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

# ---------------------------------------------------------------------------
# Live text preview
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_text_preview_updates_as_user_types(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Typing in #id_text updates #previewText in real time."""
    page.goto(f"{live_server.url}/suchary/add/")

    page.fill("#id_text", "Dlaczego komputer nie śpi? Bo ma za dużo otwartych kart.")

    preview = page.locator("#previewText")
    expect(preview).to_contain_text("Dlaczego komputer")
    # With real content the muted/italic placeholder classes should be gone.
    expect(preview).not_to_have_class(re.compile(r"\btext-muted\b"))
    expect(preview).not_to_have_class(re.compile(r"\bfst-italic\b"))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_text_preview_shows_placeholder_when_cleared(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clearing the textarea restores the Polish placeholder text in #previewText."""
    page.goto(f"{live_server.url}/suchary/add/")

    page.fill("#id_text", "Jakiś suchar")
    page.fill("#id_text", "")
    # Trigger the input event so the JS handler fires after fill clears the field.
    page.locator("#id_text").dispatch_event("input")

    preview = page.locator("#previewText")
    placeholder = preview.get_attribute("data-placeholder") or ""
    assert placeholder
    expect(preview).to_have_text(placeholder)
    expect(preview).to_have_class(re.compile(r"\btext-muted\b"))
    expect(preview).to_have_class(re.compile(r"\bfst-italic\b"))


# ---------------------------------------------------------------------------
# Tags live preview
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_tags_preview_creates_badges_for_each_tag(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Typing comma-separated tags in #id_tags_input creates badge elements."""
    page.goto(f"{live_server.url}/suchary/add/")

    page.fill("#id_tags_input", "python, it, humor")
    page.locator("#id_tags_input").dispatch_event("input")

    badges = page.locator("#previewTags .badge")
    expect(badges).to_have_count(3)
    texts = [badges.nth(i).inner_text() for i in range(3)]
    assert "#python" in texts
    assert "#it" in texts
    assert "#humor" in texts


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_tags_preview_clears_when_input_is_emptied(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Clearing the tags input removes all badges from the preview."""
    page.goto(f"{live_server.url}/suchary/add/")

    badges = page.locator("#previewTags .badge")
    page.fill("#id_tags_input", "python, it")
    page.locator("#id_tags_input").dispatch_event("input")
    expect(badges).to_have_count(2)

    page.fill("#id_tags_input", "")
    page.locator("#id_tags_input").dispatch_event("input")

    expect(badges).to_have_count(0)


# ---------------------------------------------------------------------------
# Schedule checkbox
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_schedule_checkbox_shows_date_container(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Checking #scheduleCheck removes .d-none from #scheduleContainer."""
    page.goto(f"{live_server.url}/suchary/add/")

    container = page.locator("#scheduleContainer")
    expect(container).to_have_class(re.compile(r"\bd-none\b"))

    page.check("#scheduleCheck")
    page.wait_for_selector("#scheduleContainer:not(.d-none)")

    expect(container).not_to_have_class(re.compile(r"\bd-none\b"))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_schedule_checkbox_hides_date_container(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Unchecking #scheduleCheck adds .d-none back to #scheduleContainer."""
    page.goto(f"{live_server.url}/suchary/add/")

    page.check("#scheduleCheck")
    page.wait_for_selector("#scheduleContainer:not(.d-none)")

    page.uncheck("#scheduleCheck")

    container = page.locator("#scheduleContainer")
    container.wait_for(state="hidden")
    expect(container).to_have_class(re.compile(r"\bd-none\b"))


# ---------------------------------------------------------------------------
# Schedule validation error clears on edit
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_schedule_error_clears_when_date_input_is_changed(
    page: Page,
    live_server: LiveServer,
) -> None:
    """After a past-date validation error, editing the input hides #dateError."""
    page.goto(f"{live_server.url}/suchary/add/")

    page.fill("#id_text", "Suchar testowy.")
    page.check("#scheduleCheck")
    page.wait_for_selector("#scheduleContainer:not(.d-none)")

    # Trigger the past-date validation error via programmatic submit.
    page.evaluate("""
        const publishedAtInput = document.getElementById('id_published_at');
        publishedAtInput.disabled = false;
        publishedAtInput.value = '2020-01-01 12:00';
        document.querySelector('form').dispatchEvent(
            new Event('submit', { bubbles: true, cancelable: true })
        );
    """)

    page.locator("#dateError").wait_for(state="visible")

    # Simulating typing in the date input should clear the error.
    page.evaluate("""
        const input = document.getElementById('id_published_at');
        input.value = '2030-01-01 12:00';
        input.dispatchEvent(new Event('input', { bubbles: true }));
    """)

    date_error = page.locator("#dateError")
    date_error.wait_for(state="hidden")
    expect(date_error).to_have_class(re.compile(r"\bd-none\b"))
    expect(page.locator("#id_published_at")).not_to_have_class(
        re.compile(r"\bis-invalid\b"),
    )
