"""E2E tests for the suchar form's live UI behaviors (suchar_form.js)."""

import pytest

# ---------------------------------------------------------------------------
# Live text preview
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_text_preview_updates_as_user_types(page, live_server, login):
    """Typing in #id_text updates #previewText in real time."""
    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

    page.fill("#id_text", "Dlaczego komputer nie śpi? Bo ma za dużo otwartych kart.")

    preview = page.locator("#previewText")
    assert "Dlaczego komputer" in preview.inner_text()
    # With real content the muted/italic placeholder classes should be gone.
    classes = preview.get_attribute("class") or ""
    assert "text-muted" not in classes
    assert "fst-italic" not in classes


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_text_preview_shows_placeholder_when_cleared(page, live_server, login):
    """Clearing the textarea restores the Polish placeholder text in #previewText."""
    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

    page.fill("#id_text", "Jakiś suchar")
    page.fill("#id_text", "")
    # Trigger the input event so the JS handler fires after fill clears the field.
    page.locator("#id_text").dispatch_event("input")

    preview = page.locator("#previewText")
    assert "Tutaj pojawi się" in preview.inner_text()
    classes = preview.get_attribute("class") or ""
    assert "text-muted" in classes
    assert "fst-italic" in classes


# ---------------------------------------------------------------------------
# Tags live preview
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_tags_preview_creates_badges_for_each_tag(page, live_server, login):
    """Typing comma-separated tags in #id_tags_input creates badge elements."""
    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

    page.fill("#id_tags_input", "python, it, humor")
    page.locator("#id_tags_input").dispatch_event("input")

    badges = page.locator("#previewTags .badge")
    assert badges.count() == 3  # noqa: PLR2004
    texts = [badges.nth(i).inner_text() for i in range(3)]
    assert "#python" in texts
    assert "#it" in texts
    assert "#humor" in texts


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_tags_preview_clears_when_input_is_emptied(page, live_server, login):
    """Clearing the tags input removes all badges from the preview."""
    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

    page.fill("#id_tags_input", "python, it")
    page.locator("#id_tags_input").dispatch_event("input")
    assert page.locator("#previewTags .badge").count() > 0

    page.fill("#id_tags_input", "")
    page.locator("#id_tags_input").dispatch_event("input")

    assert page.locator("#previewTags .badge").count() == 0


# ---------------------------------------------------------------------------
# Schedule checkbox
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_schedule_checkbox_shows_date_container(page, live_server, login):
    """Checking #scheduleCheck removes .d-none from #scheduleContainer."""
    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

    container = page.locator("#scheduleContainer")
    assert "d-none" in (container.get_attribute("class") or "")

    page.check("#scheduleCheck")
    page.wait_for_selector("#scheduleContainer:not(.d-none)")

    assert "d-none" not in (container.get_attribute("class") or "")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_schedule_checkbox_hides_date_container(page, live_server, login):
    """Unchecking #scheduleCheck adds .d-none back to #scheduleContainer."""
    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

    page.check("#scheduleCheck")
    page.wait_for_selector("#scheduleContainer:not(.d-none)")

    page.uncheck("#scheduleCheck")

    container = page.locator("#scheduleContainer")
    container.wait_for(state="hidden")
    assert "d-none" in (container.get_attribute("class") or "")


# ---------------------------------------------------------------------------
# Schedule validation error clears on edit
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_schedule_error_clears_when_date_input_is_changed(page, live_server, login):
    """After a past-date validation error, editing the input hides #dateError."""
    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

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
    assert "d-none" in (date_error.get_attribute("class") or "")
    assert "is-invalid" not in (
        page.locator("#id_published_at").get_attribute("class") or ""
    )
