"""E2E test for the "ba dum tss" / dust easter egg (features/badumtss.js, #284).

Types the trigger word in a real browser for a logged-in user and checks the
two surfaces: the 🥁 toast and the drifting-dust overlay. This egg is pure
delight — no achievement, so there is nothing to assert in the DB.
"""

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

# A self-resolving Promise, not a bare boolean expression: Playwright would
# rebuild a boolean predicate with in-page eval for its polling loop, which the
# app CSP (no 'unsafe-eval') blocks. A Promise resolves inside one CDP evaluate
# call that bypasses page CSP (see tests/e2e/test_hidden_achievements.py).
_READY_JS = """
    new Promise((resolve) => {
        const check = () => {
            if (window.__baDumTssReady === true) resolve(true);
            else setTimeout(check, 50);
        };
        check();
    })
"""


def _type_trigger(page: Page, word: str = "suchar") -> None:
    page.locator("body").click()
    for ch in word:
        page.keyboard.press(ch)
        page.wait_for_timeout(30)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_badumtss_shows_toast_and_dust(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    _type_trigger(page)

    # 1. The 🥁 toast.
    expect(page.locator("#toast-container .toast")).to_contain_text("ba dum tss")

    # 2. Dust overlay + injected keyframes (full-motion default).
    expect(page.locator("div.ee-dust-overlay > div")).to_have_count(24)
    expect(page.locator("#ee-badumtss-style")).to_have_count(1)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_badumtss_respects_prefers_reduced_motion(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    _type_trigger(page, "badumtss")

    # Toast still fires; the overlay and its @keyframes block do not.
    expect(page.locator("#toast-container .toast")).to_contain_text("ba dum tss")
    expect(page.locator("div.ee-dust-overlay")).to_have_count(0)
    expect(page.locator("#ee-badumtss-style")).to_have_count(0)
