"""E2E test for the "spin the logo" easter egg (features/logo_spin.js, #285).

Mashes the navbar logo in a real browser for a logged-in user and checks the
two surfaces: the short logo spin (a CSS class + injected @keyframes block) and
the meta-suchar toast. This egg is pure delight — no achievement, so there is
nothing to assert in the DB.

The logo is an ``<a href="/">``, so every click navigates home; the count lives
in a sessionStorage "chain" (each click within 3 s of the previous one) and the
effect fires from ``checkAndFire`` on the load that follows the 7th click.
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
            if (window.__logoSpinReady === true) resolve(true);
            else setTimeout(check, 50);
        };
        check();
    })
"""

CLICK_THRESHOLD = 7


def _mash_logo(page: Page, times: int = CLICK_THRESHOLD) -> None:
    """Click the logo ``times`` times; each click reloads home.

    ``window.__logoSpinReady`` is already ``true`` on the loaded page, so it is
    reset to ``false`` before each click — otherwise ``wait_for_function`` would
    resolve instantly against the stale flag and the loop could race ahead of
    (or into the teardown of) the navigation the click triggers.
    """
    for _ in range(times):
        page.evaluate("() => { window.__logoSpinReady = false; }")
        page.locator(".navbar-brand").click()
        page.wait_for_function(_READY_JS, timeout=12_000)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_logo_spin_shows_toast_and_spins(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    _mash_logo(page)

    # The spin class + its @keyframes block land synchronously in checkAndFire,
    # before __logoSpinReady flips true, so they are already present here. The
    # class is stripped after ~0.7 s — assert it before the toast (which lingers
    # ~5 s) so a slow CI runner can't let it vanish first.
    expect(page.locator(".navbar-brand.ee-logo-spin")).to_have_count(1)
    expect(page.locator("#ee-logo-spin-style")).to_have_count(1)

    # The meta-suchar toast (🌀). Any pool entry is fine; assert the icon.
    expect(page.locator("#toast-container .toast")).to_contain_text("🌀")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_logo_spin_below_threshold_does_nothing(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    _mash_logo(page, times=CLICK_THRESHOLD - 1)

    expect(page.locator(".navbar-brand.ee-logo-spin")).to_have_count(0)
    expect(page.locator("#ee-logo-spin-style")).to_have_count(0)
    expect(page.locator("#toast-container .toast")).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_logo_spin_respects_prefers_reduced_motion(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    _mash_logo(page)

    # Toast still fires; the spin class and its @keyframes block do not.
    expect(page.locator("#toast-container .toast")).to_contain_text("🌀")
    expect(page.locator(".navbar-brand.ee-logo-spin")).to_have_count(0)
    expect(page.locator("#ee-logo-spin-style")).to_have_count(0)
