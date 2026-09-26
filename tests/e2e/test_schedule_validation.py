"""E2E tests for schedule date validation in the suchar form (suchar_form.js)."""

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from suchar_overflow.suchary.models import Suchar

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.users.models import User as UserModel


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_past_date_shows_error_message(page: Page, live_server: LiveServer) -> None:
    """Past scheduled date shows the server-provided validation error on submit."""
    page.goto(f"{live_server.url}/suchary/add/")

    page.fill("#id_text", "Testowy suchar do walidacji daty.")

    # Enable the schedule toggle
    page.check("#scheduleCheck")
    page.wait_for_selector("#scheduleContainer:not(.d-none)")

    # Dispatch the submit event programmatically so we control the exact state
    # when the JS submit listener fires — bypasses Flatpickr's minDate guard
    # and the browser's native form-submit HTTP round-trip.
    page.evaluate("""
        const scheduleCheck = document.getElementById('scheduleCheck');
        const publishedAtInput = document.getElementById('id_published_at');
        scheduleCheck.checked = true;
        publishedAtInput.disabled = false;
        publishedAtInput.value = '2020-01-01 12:00';
        document.querySelector('.suchar-form-wrapper form').dispatchEvent(
            new Event('submit', { bubbles: true, cancelable: true })
        );
    """)

    date_error = page.locator("#dateError")
    date_error.wait_for(state="visible")
    # The message text comes from the data-error-text attribute rendered by
    # Django ({% trans %}) — assert the JS actually used it, not a language.
    expected_text = date_error.get_attribute("data-error-text")
    assert expected_text
    assert date_error.inner_text() == expected_text


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_future_date_passes_client_validation(
    page: Page,
    live_server: LiveServer,
) -> None:
    """A valid future date passes client-side validation and the form submits."""
    page.goto(f"{live_server.url}/suchary/add/")

    page.fill("#id_text", "Suchar z przyszłości.")

    page.check("#scheduleCheck")
    page.wait_for_selector("#scheduleContainer:not(.d-none)")
    # The toggle opens flatpickr 100 ms later; close it before writing the
    # value. A value written behind flatpickr's back while it is open is
    # replaced with today 12:00 on close (in the past every afternoon), so
    # setting it first only passed while the submit click beat the timer
    # (#419).
    page.wait_for_selector(".flatpickr-calendar.open")
    # Click away, as a user would (Escape works too since #424).
    page.click("#previewText")
    page.wait_for_selector(".flatpickr-calendar.open", state="detached")

    # The form reads a naive value on the service's wall clock (#405).
    future_str = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    page.evaluate(f"document.getElementById('id_published_at').value = '{future_str}'")
    page.evaluate("document.getElementById('id_published_at').disabled = false")

    page.click("button[type='submit']")

    # Successful submission redirects back to the list
    page.wait_for_url(f"{live_server.url}/suchary/")
    assert "/suchary/" in page.url


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_edit_form_of_scheduled_suchar_opens_with_schedule_enabled(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    """The edit form renders published_at as "Y-m-d H:i"; suchar_form.js must
    parse it (ISO "T" form, not the space form older WebKit rejects) and start
    with the schedule toggle on for a future publication."""
    scheduled = Suchar.objects.create(
        text="Zaplanowany suchar.",
        author=e2e_user,
        published_at=timezone.now() + timedelta(days=2),
    )

    page.goto(f"{live_server.url}/suchary/update/{scheduled.pk}/")

    assert page.is_checked("#scheduleCheck")
    assert page.locator("#scheduleContainer:not(.d-none)").is_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_edit_form_of_suchar_due_within_minutes_keeps_schedule(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    """A suchar due in 3 minutes is still scheduled: its edit form must not
    hide (and disable) the schedule input, or a typo fix would publish it
    immediately. The old 5-minute "is this just the pre-filled now?" buffer
    did exactly that."""
    scheduled = Suchar.objects.create(
        text="Zaraz wychodzi.",
        author=e2e_user,
        published_at=timezone.now() + timedelta(minutes=3),
    )

    page.goto(f"{live_server.url}/suchary/update/{scheduled.pk}/")

    assert page.is_checked("#scheduleCheck")
    assert page.is_enabled("#id_published_at")
