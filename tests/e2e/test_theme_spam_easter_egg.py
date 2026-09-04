"""E2E test for the "Niezdecydowany" theme-toggle-spam easter egg
(features/theme_spam.js, issue #289).

Mashes the theme toggle 10 times in quick succession for a logged-in user and
checks the three surfaces: the "Zdecyduj się" toast, the icon spin overlay (a
CSS class + injected @keyframes block), and the hidden
``frontend-ee-niezdecydowany`` achievement landing in the DB via
``POST /api/achievements/frontend-event``. Also asserts the theme itself is
untouched by the egg — 10 clicks is even, so it ends back where it started.
"""

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.users.models import User as UserModel

NIEZDECYDOWANY_SLUG = "frontend-ee-niezdecydowany"
CLICK_THRESHOLD = 10

# A self-resolving Promise, not a bare boolean expression: Playwright would
# rebuild a boolean predicate with in-page eval for its polling loop, which the
# app CSP (no 'unsafe-eval') blocks. A Promise resolves inside one CDP evaluate
# call that bypasses page CSP (see tests/e2e/test_hidden_achievements.py).
_READY_JS = """
    new Promise((resolve) => {
        const check = () => {
            if (window.__themeSpamReady === true) resolve(true);
            else setTimeout(check, 50);
        };
        check();
    })
"""

_AWARD_POLL_JS = """
    new Promise((resolve) => {{
        const check = () => {{
            fetch('/api/achievements/frontend-owned')
                .then(r => r.json())
                .then(slugs => {{
                    if (slugs.includes('{slug}')) resolve(true);
                    else setTimeout(check, 200);
                }});
        }};
        check();
    }})
"""


@pytest.fixture
def niezdecydowany_achievement(db: None) -> Achievement:  # noqa: ARG001
    """Re-create the migration-0021 row.

    ``transaction=True`` tests truncate tables between runs, wiping the seeded
    achievement — mirror the ``konami_achievement`` fixture pattern.
    """
    ach, _ = Achievement.objects.get_or_create(
        slug=NIEZDECYDOWANY_SLUG,
        defaults={
            "name": "Niezdecydowany",
            "description": "Hidden frontend achievement: Niezdecydowany.",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.FRONTEND,
            "metric": Achievement.Metric.FRONTEND_EVENT,
            "threshold": 1,
            "is_secret": True,
        },
    )
    return ach


def _mash_theme_toggle(page: Page, times: int = CLICK_THRESHOLD) -> None:
    """Click the theme toggle ``times`` times, well within the 5s window."""
    toggle = page.locator("#theme-toggle")
    for _ in range(times):
        toggle.click()
        page.wait_for_timeout(30)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login", "niezdecydowany_achievement")
def test_theme_spam_shows_toast_spin_and_awards_achievement(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    # Pin the starting theme so the parity check below is deterministic rather
    # than depending on the runner's OS-level color-scheme default.
    page.emulate_media(color_scheme="light")
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    starting_theme = page.evaluate(
        "document.documentElement.getAttribute('data-theme')",
    )
    assert starting_theme == "light"

    _mash_theme_toggle(page)

    # 1. "Zdecyduj się" toast.
    expect(page.locator("#toast-container .toast")).to_contain_text("Niezdecydowany")

    # 2. Icon-spin class + injected keyframes (full-motion default).
    expect(page.locator("#ee-theme-spam-style")).to_have_count(1)

    # 3. Hidden achievement awarded through the frontend-event endpoint.
    page.wait_for_function(
        _AWARD_POLL_JS.format(slug=NIEZDECYDOWANY_SLUG),
        timeout=12_000,
    )
    ach = Achievement.objects.get(slug=NIEZDECYDOWANY_SLUG)
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()

    # 4. Theme untouched by the egg — 10 clicks (even) ends back where it
    #    started, and localStorage agrees with the DOM attribute.
    ending_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert ending_theme == "light"
    assert page.evaluate("localStorage.getItem('theme')") == "light"

    # 5. A discriminating check, not just a coincidental parity match: one more
    #    click still causes exactly one flip. If the egg additionally wrote
    #    the theme itself (forcing a value, or double-toggling), this click
    #    would land on something other than the single expected flip.
    page.locator("#theme-toggle").click()
    final_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert final_theme == "dark"
    assert page.evaluate("localStorage.getItem('theme')") == "dark"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login", "niezdecydowany_achievement")
def test_theme_spam_respects_prefers_reduced_motion(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    _mash_theme_toggle(page)

    # Toast + award still happen; no spin, so no @keyframes block is injected.
    expect(page.locator("#toast-container .toast")).to_contain_text("Niezdecydowany")
    expect(page.locator("#ee-theme-spam-style")).to_have_count(0)

    page.wait_for_function(
        _AWARD_POLL_JS.format(slug=NIEZDECYDOWANY_SLUG),
        timeout=12_000,
    )
    ach = Achievement.objects.get(slug=NIEZDECYDOWANY_SLUG)
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()
