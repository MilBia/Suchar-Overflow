"""E2E test for the "tumbleweed after inactivity" easter egg
(features/tumbleweed.js, #288).

Sits idle on ``/suchary/`` in a real browser for a logged-in user and checks
the two surfaces: the rolling tumbleweed overlay (an ``<svg>`` + its injected
``@keyframes`` block) and the "cisza… aż tak sucho?" caption. This egg is pure
delight — no achievement, so there is nothing to assert in the DB.

The trigger is a 120 s inactivity timer; ``page.clock`` fast-forwards past it
instead of the suite waiting two real minutes (issue #288 → #281).
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
# __tumbleweedReady is set synchronously in the DOMContentLoaded handler, so the
# executor's first check() resolves it — the clock-controlled setTimeout branch
# is never taken.
_READY_JS = """
    new Promise((resolve) => {
        const check = () => {
            if (window.__tumbleweedReady === true) resolve(true);
            else setTimeout(check, 50);
        };
        check();
    })
"""

# Past the 120 s idle threshold, but comfortably inside the ~4.4 s overlay
# lifetime that starts when it fires — so the roll is still on screen to assert.
_IDLE_JUMP_MS = 121_000


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_tumbleweed_rolls_after_inactivity(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.clock.install()
    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    page.clock.fast_forward(_IDLE_JUMP_MS)

    overlay = page.locator("div.ee-tumbleweed-overlay")
    expect(overlay).to_have_count(1)
    expect(overlay.locator("svg")).to_have_count(1)
    expect(overlay).to_contain_text("aż tak sucho")
    expect(page.locator("#ee-tumbleweed-style")).to_have_count(1)

    # …then it clears itself (issue #288: "po czym znika"). The removal is a
    # clock-driven setTimeout, so it only fires once the clock is moved on.
    page.clock.fast_forward(10_000)
    expect(overlay).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_tumbleweed_respects_prefers_reduced_motion(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.clock.install()
    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    page.clock.fast_forward(_IDLE_JUMP_MS)

    # The caption still lands, as a toast; the overlay and its @keyframes do not.
    expect(page.locator("#toast-container .toast")).to_contain_text("aż tak sucho")
    expect(page.locator("div.ee-tumbleweed-overlay")).to_have_count(0)
    expect(page.locator("#ee-tumbleweed-style")).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_tumbleweed_inert_outside_suchary(
    page: Page,
    live_server: LiveServer,
) -> None:
    page.clock.install()
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    page.clock.fast_forward(_IDLE_JUMP_MS)

    expect(page.locator("div.ee-tumbleweed-overlay")).to_have_count(0)
    expect(page.locator("#toast-container .toast")).to_have_count(0)
