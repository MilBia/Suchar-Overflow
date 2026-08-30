"""E2E tests for the leaderboard sliding indicators (pages/leaderboard.js).

Regression guard for the debounced single ``resize`` listener introduced in
PR #235 (issue #208): the refactor collects repositioning callbacks in a
``resizeHandlers`` array and registers one debounced ``window`` listener at the
end of ``DOMContentLoaded``.  Real failure modes of that indirection (issue
#248): a callback pushed to the array *after* the listener is registered, or an
empty array, would leave the sliders stranded at their pre-resize geometry.
"""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

# Tolerance for comparing a slider's viewport rect against its active button's.
# The sliders are ``position: absolute`` inside a ``position: relative`` /
# ``border: 1px`` container, so ``left`` (measured from the padding box) sits a
# border-width off the button's border-box left.  Measured on the actual page
# while implementing #248: left delta settles at ~1px, width delta at ~0px, at
# both a 1280px and a 400px viewport.  2px leaves headroom for CI sub-pixel.
_ALIGN_TOLERANCE_PX = 2.0

_MEASURE_JS = """
    () => {
        const slider = document.querySelector(
            '#leaderboardTabs .leaderboard-tab-slider');
        const btn = document.querySelector('#leaderboardTabs .nav-link.active');
        const s = slider.getBoundingClientRect();
        const b = btn.getBoundingClientRect();
        return {
            left_delta: Math.abs(s.left - b.left),
            width_delta: Math.abs(s.width - b.width),
            btn_width: b.width,
        };
    }
"""

# A self-polling Promise, not a bare boolean expression: Playwright would rebuild
# a bare predicate with in-page ``eval`` for its polling loop, which the app CSP
# (no 'unsafe-eval') blocks.  A Promise resolves inside a single CDP evaluate
# call that bypasses page CSP (same shape as tests/e2e/test_hidden_achievements).
_TAB_SLIDER_ALIGNED_JS = """
    new Promise((resolve) => {{
        const tol = {tol};
        const check = () => {{
            const slider =
                document.querySelector('#leaderboardTabs .leaderboard-tab-slider');
            const btn =
                document.querySelector('#leaderboardTabs .nav-link.active');
            if (slider && btn) {{
                const s = slider.getBoundingClientRect();
                const b = btn.getBoundingClientRect();
                if (Math.abs(s.left - b.left) <= tol &&
                    Math.abs(s.width - b.width) <= tol) {{
                    resolve(true);
                    return;
                }}
            }}
            setTimeout(check, 50);
        }};
        check();
    }})
"""

_TIMEFRAME_SLIDER_ALIGNED_JS = """
    new Promise((resolve) => {{
        const tol = {tol};
        const check = () => {{
            const selector = document.querySelector('.chart-timeframe-selector');
            const slider = selector
                && selector.querySelector('.chart-timeframe-slider');
            const btn = selector && selector.querySelector('button.active');
            if (slider && btn) {{
                const s = slider.getBoundingClientRect();
                const b = btn.getBoundingClientRect();
                if (Math.abs(s.left - b.left) <= tol &&
                    Math.abs(s.width - b.width) <= tol) {{
                    resolve(true);
                    return;
                }}
            }}
            setTimeout(check, 50);
        }};
        check();
    }})
"""


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_tab_slider_repositions_after_window_resize(
    page: Page,
    live_server: LiveServer,
) -> None:
    """The tab slider tracks the active tab's new geometry after a resize."""
    page.goto(f"{live_server.url}/stats/leaderboard/")

    # leaderboard.js places the slider on the initially-active tab from a
    # setTimeout(50) — wait for that to settle before interacting, or a click
    # landing inside that window gets clobbered by the stale deferred callback.
    page.wait_for_function(
        _TAB_SLIDER_ALIGNED_JS.format(tol=_ALIGN_TOLERANCE_PX),
        timeout=5000,
    )

    # Park the slider on the middle ("Funny") tab so the resize below moves
    # *both* its left and its width — the first tab's left is pinned to the
    # container padding and barely shifts.
    page.click("#funny-tab")
    page.wait_for_function(
        _TAB_SLIDER_ALIGNED_JS.format(tol=_ALIGN_TOLERANCE_PX),
        timeout=5000,
    )
    wide_btn_width = page.evaluate(_MEASURE_JS)["btn_width"]

    # Shrink well below the tab strip's 500px max-width so the three equal-flex
    # tabs each get materially narrower.
    page.set_viewport_size({"width": 400, "height": 800})

    # If the debounced resize handler never runs, the slider keeps its wide
    # geometry while the button shrank -> this poll times out and the test fails.
    page.wait_for_function(
        _TAB_SLIDER_ALIGNED_JS.format(tol=_ALIGN_TOLERANCE_PX),
        timeout=5000,
    )

    result = page.evaluate(_MEASURE_JS)
    assert result["left_delta"] <= _ALIGN_TOLERANCE_PX
    assert result["width_delta"] <= _ALIGN_TOLERANCE_PX
    # Guard the guard: confirm the resize genuinely perturbed the layout, so the
    # poll above actually exercised the repositioning path.
    assert result["btn_width"] < wide_btn_width - 5


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_tab_slider_follows_keyboard_navigation(
    page: Page,
    live_server: LiveServer,
) -> None:
    """Arrow-key tab navigation moves the slider, not just clicks.

    project.js ``activateTab`` (the arrow-key handler) fires no ``click``; it
    dispatches a ``tab:activated`` CustomEvent that leaderboard.js listens on.
    Broken wiring -> the slider stays on the first tab -> this poll times out.
    """
    page.goto(f"{live_server.url}/stats/leaderboard/")

    page.wait_for_function(
        _TAB_SLIDER_ALIGNED_JS.format(tol=_ALIGN_TOLERANCE_PX),
        timeout=5000,
    )

    # ArrowRight on the first tab activates the second ("Funny") via keyboard.
    page.locator("#overall-tab").press("ArrowRight")
    assert page.evaluate(
        "document.querySelector('#funny-tab').classList.contains('active')",
    )

    page.wait_for_function(
        _TAB_SLIDER_ALIGNED_JS.format(tol=_ALIGN_TOLERANCE_PX),
        timeout=5000,
    )
    result = page.evaluate(_MEASURE_JS)
    assert result["left_delta"] <= _ALIGN_TOLERANCE_PX
    assert result["width_delta"] <= _ALIGN_TOLERANCE_PX


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_timeframe_slider_stays_aligned_after_window_resize(
    page: Page,
    live_server: LiveServer,
) -> None:
    """The timeframe slider stays glued to the active button across a resize.

    Unlike the tab strip, the timeframe buttons are content-sized and their
    geometry relative to the selector is viewport-independent, so this asserts
    that resizing does not *break* the alignment — it is not a registration
    guard for the timeframe ``resizeHandlers`` entry (that entry's callback is a
    no-op here by construction).  The tab-strip test above is the real guard.
    """
    page.goto(f"{live_server.url}/stats/leaderboard/")
    page.wait_for_function(
        _TIMEFRAME_SLIDER_ALIGNED_JS.format(tol=_ALIGN_TOLERANCE_PX),
        timeout=5000,
    )

    page.set_viewport_size({"width": 400, "height": 800})

    page.wait_for_function(
        _TIMEFRAME_SLIDER_ALIGNED_JS.format(tol=_ALIGN_TOLERANCE_PX),
        timeout=5000,
    )
