"""E2E accessibility behaviour for the audit #364 phase-4 sweep (project.js).

Runtime behaviour for issues #340-#345 that a static render test can't reach:

* #341 — the logout modal moves focus into the dialog, traps Tab, closes on
  Escape and restores focus to the trigger.
* #342 — the ``data-tooltip`` on the anonymous vote buttons appears on keyboard
  focus (not just mouse hover) and wires ``aria-describedby``.
* #340 — ``aria-expanded`` on both dropdown triggers stays in sync with the
  open/closed state through every close path.
* #345 — ``showToast`` announces politely (``role="status"``) by default and
  only interrupts (``role="alert"``) for errors.
"""

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.suchary.models import Suchar as SucharModel


# ---------------------------------------------------------------------------
# #341 — logout modal focus management
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_opening_modal_moves_focus_into_dialog(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/")
    page.click("#logout-button")

    expect(page.locator("#logoutModal")).to_be_visible()
    assert page.evaluate(
        "document.getElementById('logoutModal').contains(document.activeElement)",
    ), "focus was not moved inside the modal on open"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_escape_closes_modal_and_restores_focus_to_trigger(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/")
    page.click("#logout-button")
    expect(page.locator("#logoutModal")).to_be_visible()

    page.keyboard.press("Escape")

    expect(page.locator("#logoutModal")).to_be_hidden()
    assert page.evaluate(
        "document.activeElement === document.getElementById('logout-button')",
    ), "focus was not restored to the trigger after Escape"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_tab_is_trapped_inside_the_modal(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/")
    page.click("#logout-button")
    expect(page.locator("#logoutModal")).to_be_visible()

    first = "#logoutModal .modal-header .btn-close"
    last = "#logoutModal button[type='submit']"

    # Tab off the last focusable wraps back to the first.
    page.locator(last).focus()
    page.keyboard.press("Tab")
    assert page.evaluate(
        f"document.activeElement === document.querySelector({first!r})",
    ), "Tab did not wrap from the last focusable to the first"

    # Shift+Tab off the first wraps to the last.
    page.locator(first).focus()
    page.keyboard.press("Shift+Tab")
    assert page.evaluate(
        f"document.activeElement === document.querySelector({last!r})",
    ), "Shift+Tab did not wrap from the first focusable to the last"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_cancel_button_restores_focus_to_trigger(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/")
    page.click("#logout-button")

    # Deliberately the footer "Cancel" button, not the header close (x): the x
    # is the element openModal() already focused, so closing from it can't tell
    # a real focus-restore apart from a no-op. Cancel moves focus first, so the
    # assertion genuinely exercises the restore path.
    page.locator("#logoutModal .modal-footer .modal-close").click()

    expect(page.locator("#logoutModal")).to_be_hidden()
    assert page.evaluate(
        "document.activeElement === document.getElementById('logout-button')",
    )


# ---------------------------------------------------------------------------
# #342 — tooltip on keyboard focus
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_tooltip_appears_on_keyboard_focus_for_anonymous_vote_button(
    page: Page,
    live_server: LiveServer,
    published_suchar: SucharModel,  # noqa: ARG001
) -> None:
    page.goto(f"{live_server.url}/suchary/")

    btn = page.locator(".btn-vote[data-anonymous='true']").first
    btn.focus()

    tooltip = page.locator(".custom-tooltip-box")
    expect(tooltip).to_be_visible()
    expect(tooltip).to_have_attribute("role", "tooltip")

    described_by = btn.get_attribute("aria-describedby")
    assert described_by, "focused control did not get aria-describedby"
    assert page.locator(f"#{described_by}").count() == 1

    page.evaluate("document.activeElement && document.activeElement.blur()")
    expect(tooltip).to_have_count(0)
    assert btn.get_attribute("aria-describedby") is None


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_tooltip_survives_pointer_leaving_while_focused(
    page: Page,
    live_server: LiveServer,
    published_suchar: SucharModel,  # noqa: ARG001
) -> None:
    """WCAG 1.4.13: hover and focus are independent — losing the pointer must
    not tear the tooltip down while the control still has keyboard focus."""
    page.goto(f"{live_server.url}/suchary/")
    btn = page.locator(".btn-vote[data-anonymous='true']").first

    btn.hover()
    btn.focus()
    expect(page.locator(".custom-tooltip-box")).to_be_visible()

    # Pointer wanders off; focus stays on the button.
    page.mouse.move(1, 1)
    expect(page.locator(".custom-tooltip-box")).to_be_visible()

    # Escape dismisses it without moving focus (SC 1.4.13, Dismissible).
    page.keyboard.press("Escape")
    expect(page.locator(".custom-tooltip-box")).to_have_count(0)
    assert page.evaluate(
        "document.activeElement === document.querySelector"
        "(\".btn-vote[data-anonymous='true']\")",
    )


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_tooltip_is_not_stuck_after_focus_then_hover_then_blur_then_unhover(
    page: Page,
    live_server: LiveServer,
    published_suchar: SucharModel,  # noqa: ARG001
) -> None:
    """focusin shows the tooltip; a following hover must still arm the
    mouseleave cleanup even though showTooltip is a no-op — otherwise blurring
    (mouse still over) then un-hovering leaves the tooltip stuck forever."""
    page.goto(f"{live_server.url}/suchary/")
    btn = page.locator(".btn-vote[data-anonymous='true']").first

    btn.focus()
    btn.hover()
    expect(page.locator(".custom-tooltip-box")).to_be_visible()

    page.evaluate("document.activeElement && document.activeElement.blur()")
    # Mouse is still over the button — the tooltip legitimately stays.
    expect(page.locator(".custom-tooltip-box")).to_be_visible()

    page.mouse.move(1, 1)
    expect(page.locator(".custom-tooltip-box")).to_have_count(0)
    assert btn.get_attribute("aria-describedby") is None


# ---------------------------------------------------------------------------
# #340 — aria-expanded stays in sync
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_sort_dropdown_syncs_aria_expanded(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/suchary/")
    trigger = page.locator("#sortDropdown .dropdown-trigger")

    expect(trigger).to_have_attribute("aria-expanded", "false")
    trigger.click()
    expect(trigger).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("Escape")
    expect(trigger).to_have_attribute("aria-expanded", "false")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_language_dropdown_syncs_aria_expanded_on_outside_click(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/")
    trigger = page.locator("#languageDropdown .dropdown-trigger")

    expect(trigger).to_have_attribute("aria-expanded", "false")
    trigger.click()
    expect(trigger).to_have_attribute("aria-expanded", "true")

    page.locator("body").click(position={"x": 2, "y": 2})
    expect(trigger).to_have_attribute("aria-expanded", "false")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_language_search_field_routes_the_widget_keys(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Focus auto-jumps to `.language-search`; Escape must still close the menu
    (and not stay trapped in the field), restoring focus to the trigger."""
    page.goto(f"{live_server.url}/")
    trigger = page.locator("#languageDropdown .dropdown-trigger")
    trigger.click()

    search = page.locator("#languageDropdown .language-search")
    expect(search).to_be_focused()

    page.keyboard.press("Escape")
    expect(trigger).to_have_attribute("aria-expanded", "false")
    expect(trigger).to_be_focused()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_sort_dropdown_closes_when_focus_tabs_out(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/suchary/")
    trigger = page.locator("#sortDropdown .dropdown-trigger")
    trigger.click()
    expect(trigger).to_have_attribute("aria-expanded", "true")

    # Move focus onto the last option, then Tab past it — out of the widget.
    page.locator("#sortDropdown .dropdown-item").last.focus()
    page.keyboard.press("Tab")

    expect(trigger).to_have_attribute("aria-expanded", "false")


# ---------------------------------------------------------------------------
# #341 — Shift+Tab from the dialog card itself is trapped
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_shift_tab_from_the_modal_card_does_not_escape(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/")
    page.click("#logout-button")
    expect(page.locator("#logoutModal")).to_be_visible()

    # Land focus on the .modal card itself (tabindex="-1"), then Shift+Tab.
    page.evaluate("document.querySelector('#logoutModal .modal').focus()")
    page.keyboard.press("Shift+Tab")

    assert page.evaluate(
        "document.getElementById('logoutModal').contains(document.activeElement)",
    ), "Shift+Tab from the modal card leaked focus to the page behind it"
    assert page.evaluate(
        "document.activeElement === "
        "document.querySelector(\"#logoutModal button[type='submit']\")",
    )


# ---------------------------------------------------------------------------
# #345 — toast politeness
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_toast_container_is_polite_and_toasts_default_to_status(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/")
    page.wait_for_function("typeof window.showToast === 'function'")

    expect(page.locator("#toast-container")).to_have_attribute("aria-live", "polite")

    page.evaluate("window.showToast('ok', 'T', 'success')")
    expect(page.locator("#toast-container .toast").last).to_have_attribute(
        "role",
        "status",
    )

    page.evaluate("window.showToast('bad', 'T', 'error')")
    expect(page.locator("#toast-container .toast-error").last).to_have_attribute(
        "role",
        "alert",
    )
