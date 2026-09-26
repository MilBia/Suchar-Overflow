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
    # Checking the toggle with an empty date opens flatpickr 100 ms later.
    # It used to render above the field, over the toggle (#419); since #424 it
    # always opens below (covered by the calendar tests further down), but
    # close it first anyway so this test only exercises the toggle.
    page.wait_for_selector(".flatpickr-calendar.open")
    # Click away, as a user would (Escape works too since #424).
    page.click("#previewText")
    page.wait_for_selector(".flatpickr-calendar.open", state="detached")

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
        document.querySelector('.suchar-form-wrapper form').dispatchEvent(
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


# ---------------------------------------------------------------------------
# Submit spinner exposes a screen-reader status string (#298)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_submit_adds_loading_state_and_status_string(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Submitting the form spins the button and drops a role=status live region
    next to it (not inside the now-disabled button) carrying the flavored copy."""
    page.goto(f"{live_server.url}/suchary/add/")

    # Cancel the actual navigation so the transient loading state stays put;
    # suchar_form.js's own bubble-phase submit handler still runs.
    page.evaluate(
        "document.querySelector('.suchar-form-wrapper form').addEventListener("
        "'submit', (e) => e.preventDefault(), true)",
    )
    page.fill("#id_text", "Poprawny suchar do wysłania.")
    submit_selector = ".suchar-form-wrapper button[type=submit]"
    page.click(submit_selector)

    submit_btn = page.locator(submit_selector)
    expect(submit_btn).to_have_class(re.compile(r"\bis-loading\b"))
    expect(submit_btn).to_be_disabled()

    status = page.locator(f"{submit_selector} + [role=status]")
    expect(status).to_have_count(1)
    expect(status).to_have_class(re.compile(r"\bvisually-hidden\b"))
    expected = submit_btn.get_attribute("data-loading-text") or ""
    assert expected
    expect(status).to_have_text(expected)


# ---------------------------------------------------------------------------
# Schedule calendar placement / keyboard (#424)
# ---------------------------------------------------------------------------

# Two frames: flatpickr positions the calendar right after onOpen, and
# suchar_form.js scrolls it into view one requestAnimationFrame later.
_SETTLE_JS = "new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"

_CALENDAR_BOX_JS = """
    (() => {
        const cal = document.querySelector('.flatpickr-calendar.open');
        // From flatpickr's inline page-coordinate `top`, not the rect's own
        // bottom: the fpFadeInDown opening animation still has the rect
        // translated up to 20 px higher than where it settles.
        const height = cal.getBoundingClientRect().height;
        return {
            bottom: parseFloat(cal.style.top) + height - window.scrollY,
            innerHeight: window.innerHeight,
            below: cal.classList.contains('arrowTop'),
        };
    })()
"""


def _open_calendar_with_toggle_mid_viewport(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Tick "Schedule" with the toggle in the middle of the viewport.

    That is where #419 measured the flip: with the date field at ~440-485 px
    of an 800 px viewport only ~315 px are free below it, less than the
    calendar's ~344 px, so flatpickr's "auto" position drew it above the
    field — over the toggle.
    """
    page.goto(f"{live_server.url}/suchary/add/")
    page.evaluate(
        "document.getElementById('scheduleCheck').scrollIntoView({block: 'center'})",
    )
    page.check("#scheduleCheck")
    page.wait_for_selector(".flatpickr-calendar.open")
    page.evaluate(_SETTLE_JS)


def _assert_one_click_unticks_toggle(page: Page) -> None:
    box = page.locator("#scheduleCheck").bounding_box()
    assert box is not None
    # A raw mouse click, not page.uncheck(): Playwright's actionability check
    # waits out anything intercepting the click, which is exactly the bug —
    # the first click landing on the calendar instead of the toggle.
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    assert not page.is_checked("#scheduleCheck")
    expect(page.locator("#scheduleContainer")).to_have_class(re.compile(r"\bd-none\b"))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_schedule_calendar_opens_below_and_toggle_unticks_in_one_click(
    page: Page,
    live_server: LiveServer,
) -> None:
    """The calendar never covers the toggle, and stays inside the viewport."""
    _open_calendar_with_toggle_mid_viewport(page, live_server)

    cal = page.evaluate(_CALENDAR_BOX_JS)
    assert cal["below"]
    assert cal["bottom"] <= cal["innerHeight"]

    _assert_one_click_unticks_toggle(page)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_schedule_calendar_toggle_unticks_in_one_click_on_narrow_screen(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Same on a phone-sized viewport, where the toggle and the field wrap
    onto separate rows and scrolling the calendar into view moves the toggle
    towards the sticky navbar."""
    page.set_viewport_size({"width": 375, "height": 667})
    _open_calendar_with_toggle_mid_viewport(page, live_server)

    cal = page.evaluate(_CALENDAR_BOX_JS)
    assert cal["below"]
    assert cal["bottom"] <= cal["innerHeight"]

    _assert_one_click_unticks_toggle(page)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_schedule_calendar_closes_on_escape_with_focus_on_toggle(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Opening the calendar from the toggle leaves focus on the toggle, where
    flatpickr's own Escape handling never sees the key."""
    _open_calendar_with_toggle_mid_viewport(page, live_server)
    assert page.evaluate("document.activeElement.id") == "scheduleCheck"

    page.keyboard.press("Escape")

    page.wait_for_selector(".flatpickr-calendar.open", state="detached")
    # Closing is all Escape does: the schedule stays on.
    assert page.is_checked("#scheduleCheck")
