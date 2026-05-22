"""E2E tests for schedule date validation in the suchar form (suchar_form.js)."""

from datetime import datetime
from datetime import timedelta

import pytest


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_past_date_shows_polish_error_message(page, live_server, login):
    """Past scheduled date shows a Polish validation error on submit."""
    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

    page.fill("#id_text", "Testowy suchar do walidacji daty.")

    # Enable the schedule toggle
    page.check("#scheduleCheck")
    page.wait_for_selector("#scheduleContainer:not(.d-none)")

    # Inject a past date directly (flatpickr intercepts normal fill)
    page.evaluate(
        "document.getElementById('id_published_at').value = '2020-01-01 12:00'",
    )
    page.evaluate("document.getElementById('id_published_at').disabled = false")

    page.click("button[type='submit']")

    date_error = page.locator("#dateError")
    date_error.wait_for(state="visible")
    assert "przeszłości" in date_error.inner_text()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_future_date_passes_client_validation(page, live_server, login):
    """A valid future date passes client-side validation and the form submits."""
    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

    page.fill("#id_text", "Suchar z przyszłości.")

    page.check("#scheduleCheck")
    page.wait_for_selector("#scheduleContainer:not(.d-none)")

    future_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")  # noqa: DTZ005
    page.evaluate(f"document.getElementById('id_published_at').value = '{future_str}'")
    page.evaluate("document.getElementById('id_published_at').disabled = false")

    page.click("button[type='submit']")

    # Successful submission redirects back to the list
    page.wait_for_url(f"{live_server.url}/suchary/")
    assert "/suchary/" in page.url
