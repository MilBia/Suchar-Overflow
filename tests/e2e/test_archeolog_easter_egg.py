"""E2E test for the "Archeolog" scroll-to-bottom easter egg
(features/archeolog.js, issue #290).

Scrolls to the bottom of the *last* page of a suchar list with at least 5
pages total for a logged-in user and checks the toast plus the hidden
``frontend-ee-archeolog`` achievement landing in the DB via
``POST /api/achievements/frontend-event``. Also checks the negative case: a
list under 5 pages never awards it, even scrolled all the way to its bottom.
"""

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone
from playwright.sync_api import expect

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.users.models import User as UserModel

ARCHEOLOG_SLUG = "frontend-ee-archeolog"
# Matches SucharListView's _PER_PAGE (10) — 45 suchary makes exactly 5 pages.
SUCHARY_FOR_FIVE_PAGES = 45

# A self-resolving Promise, not a bare boolean expression: Playwright would
# rebuild a boolean predicate with in-page eval for its polling loop, which the
# app CSP (no 'unsafe-eval') blocks. A Promise resolves inside one CDP evaluate
# call that bypasses page CSP (see tests/e2e/test_hidden_achievements.py).
_READY_JS = """
    new Promise((resolve) => {
        const check = () => {
            if (window.__archeologReady === true) resolve(true);
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
def archeolog_achievement(db: None) -> Achievement:  # noqa: ARG001
    """Re-create the migration-0022 row.

    ``transaction=True`` tests truncate tables between runs, wiping the seeded
    achievement — mirror the ``niezdecydowany_achievement`` fixture pattern.
    """
    ach, _ = Achievement.objects.get_or_create(
        slug=ARCHEOLOG_SLUG,
        defaults={
            "name": "Archeolog",
            "description": "Hidden frontend achievement: Archeolog.",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.FRONTEND,
            "metric": Achievement.Metric.FRONTEND_EVENT,
            "threshold": 1,
            "is_secret": True,
        },
    )
    return ach


def _seed_suchary(count: int, author: UserModel) -> None:
    now = timezone.now()
    Suchar.objects.bulk_create(
        [
            Suchar(
                text=f"Suchar numer {i} do przewinięcia.",
                author=author,
                created_at=now - timedelta(minutes=i),
                published_at=now - timedelta(minutes=i),
            )
            for i in range(count)
        ],
    )


def _scroll_to_bottom(page: Page) -> None:
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login", "archeolog_achievement")
def test_archeolog_awards_on_last_page_of_a_five_page_list(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    _seed_suchary(SUCHARY_FOR_FIVE_PAGES, e2e_user)

    page.goto(f"{live_server.url}/suchary/?page=5")
    page.wait_for_function(_READY_JS, timeout=12_000)

    _scroll_to_bottom(page)

    expect(page.locator("#toast-container .toast")).to_contain_text("Archeolog")

    page.wait_for_function(
        _AWARD_POLL_JS.format(slug=ARCHEOLOG_SLUG),
        timeout=12_000,
    )
    ach = Achievement.objects.get(slug=ARCHEOLOG_SLUG)
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login", "archeolog_achievement")
def test_archeolog_does_not_award_on_an_earlier_page(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    _seed_suchary(SUCHARY_FOR_FIVE_PAGES, e2e_user)

    # Page 2 of 5: reaching its bottom has a next page, so it's ineligible.
    page.goto(f"{live_server.url}/suchary/?page=2")
    page.wait_for_function(_READY_JS, timeout=12_000)

    _scroll_to_bottom(page)
    page.wait_for_timeout(500)

    expect(page.locator("#toast-container .toast")).to_have_count(0)
    ach = Achievement.objects.get(slug=ARCHEOLOG_SLUG)
    assert not UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login", "archeolog_achievement")
def test_archeolog_does_not_award_on_a_list_under_five_pages(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    # Only 2 pages total — the last page's bottom is reachable, but the list
    # is too short for the achievement to be obtainable (issue #290).
    _seed_suchary(15, e2e_user)

    page.goto(f"{live_server.url}/suchary/?page=2")
    page.wait_for_function(_READY_JS, timeout=12_000)

    _scroll_to_bottom(page)
    page.wait_for_timeout(500)

    expect(page.locator("#toast-container .toast")).to_have_count(0)
    ach = Achievement.objects.get(slug=ARCHEOLOG_SLUG)
    assert not UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()
