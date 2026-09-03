"""E2E test for the Konami-code easter egg (features/konami.js, issue #283).

Drives the real key sequence in a browser for a logged-in user and checks the
three surfaces: the wink toast, the falling-cracker overlay, and the hidden
``frontend-ee-konami`` achievement landing in the DB via
``POST /api/achievements/frontend-event``.
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

KONAMI_SLUG = "frontend-ee-konami"

# Playwright key names for ↑ ↑ ↓ ↓ ← → ← → B A.
KONAMI_KEYS = [
    "ArrowUp",
    "ArrowUp",
    "ArrowDown",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "ArrowLeft",
    "ArrowRight",
    "b",
    "a",
]

# A self-resolving Promise, not a bare boolean expression: Playwright would
# rebuild a boolean predicate with in-page eval for its polling loop, which the
# app CSP (no 'unsafe-eval') blocks. A Promise resolves inside one CDP evaluate
# call that bypasses page CSP (see tests/e2e/test_hidden_achievements.py).
_KONAMI_READY_JS = """
    new Promise((resolve) => {
        const check = () => {
            if (window.__konamiReady === true) resolve(true);
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
def konami_achievement(db: None) -> Achievement:  # noqa: ARG001
    """Re-create the migration-0020 row.

    ``transaction=True`` tests truncate tables between runs, wiping the seeded
    achievement — mirror the ``frontend_achievements`` fixture pattern.
    """
    ach, _ = Achievement.objects.get_or_create(
        slug=KONAMI_SLUG,
        defaults={
            "name": "Kod Konami",
            "description": "Hidden frontend achievement: Kod Konami.",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.FRONTEND,
            "metric": Achievement.Metric.FRONTEND_EVENT,
            "threshold": 1,
            "is_secret": True,
        },
    )
    return ach


def _enter_konami(page: Page) -> None:
    page.locator("body").click()
    for key in KONAMI_KEYS:
        page.keyboard.press(key)
        page.wait_for_timeout(30)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login", "konami_achievement")
def test_konami_code_shows_toast_rain_and_awards_achievement(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_KONAMI_READY_JS, timeout=12_000)

    _enter_konami(page)

    # 1. Wink toast.
    expect(page.locator("#toast-container .toast")).to_contain_text("Kod Konami")

    # 2. Falling-cracker overlay + injected keyframes (full-motion default).
    #    Web-first assertions only — `locator.count()` is a non-retrying snapshot.
    expect(page.locator("div[aria-hidden='true'] svg rect")).to_have_count(42)
    expect(page.locator("#ee-konami-style")).to_have_count(1)

    # 3. Hidden achievement awarded through the frontend-event endpoint.
    page.wait_for_function(
        _AWARD_POLL_JS.format(slug=KONAMI_SLUG),
        timeout=12_000,
    )
    ach = Achievement.objects.get(slug=KONAMI_SLUG)
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login", "konami_achievement")
def test_konami_code_respects_prefers_reduced_motion(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_KONAMI_READY_JS, timeout=12_000)

    _enter_konami(page)

    # Toast + award still happen; the overlay is a motion-free static scatter,
    # so no @keyframes block is injected and there are fewer particles.
    expect(page.locator("#toast-container .toast")).to_contain_text("Kod Konami")
    expect(page.locator("#ee-konami-style")).to_have_count(0)
    expect(page.locator("div[aria-hidden='true'] svg rect")).to_have_count(16)

    page.wait_for_function(
        _AWARD_POLL_JS.format(slug=KONAMI_SLUG),
        timeout=12_000,
    )
    ach = Achievement.objects.get(slug=KONAMI_SLUG)
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()
