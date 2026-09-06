"""E2E test for the "Publika Rozgrzana" combo easter egg
(features/publika_rozgrzana.js, issue #296).

Casts 10 "funny" votes in a row on the suchar list for a logged-in user and
checks the two surfaces of the payoff: the "Publika Rozgrzana" toast and the
hidden ``frontend-ee-publika-rozgrzana`` achievement landing in the DB via
``POST /api/achievements/frontend-event`` — plus the combo-meter showing the
running count mid-run, and a "dry" vote breaking the chain.
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
    from playwright.sync_api import Locator
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.users.models import User as UserModel

PUBLIKA_ROZGRZANA_SLUG = "frontend-ee-publika-rozgrzana"
THRESHOLD = 10

# A self-resolving Promise, not a bare boolean expression: Playwright would
# rebuild a boolean predicate with in-page eval for its polling loop, which the
# app CSP (no 'unsafe-eval') blocks. A Promise resolves inside one CDP evaluate
# call that bypasses page CSP (see tests/e2e/test_hidden_achievements.py).
_READY_JS = """
    new Promise((resolve) => {
        const check = () => {
            if (window.__publikaRozgrzanaReady === true) resolve(true);
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
def publika_rozgrzana_achievement(db: None) -> Achievement:  # noqa: ARG001
    """Re-create the migration-0023 row.

    ``transaction=True`` tests truncate tables between runs, wiping the seeded
    achievement — mirror the ``archeolog_achievement`` fixture pattern.
    """
    ach, _ = Achievement.objects.get_or_create(
        slug=PUBLIKA_ROZGRZANA_SLUG,
        defaults={
            "name": "Publika Rozgrzana",
            "description": "Hidden frontend achievement: Publika Rozgrzana.",
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
                text=f"Suchar numer {i} do rozgrzania publiki.",
                author=author,
                created_at=now - timedelta(minutes=i),
                published_at=now - timedelta(minutes=i),
            )
            for i in range(count)
        ],
    )


def _vote(page: Page, button: Locator) -> None:
    """Click one vote button and wait for the endpoint round-trip."""
    with page.expect_response("**/api/suchary/*/vote"):
        button.click()
    page.wait_for_timeout(50)


def _funny(page: Page, start: int, end: int) -> None:
    """Click funny buttons ``[start, end)`` — each card's funny button once."""
    buttons = page.locator('.btn-vote[data-vote-type="funny"]')
    for i in range(start, end):
        _vote(page, buttons.nth(i))


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login", "publika_rozgrzana_achievement")
def test_publika_rozgrzana_meter_toast_and_award(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    _seed_suchary(THRESHOLD, e2e_user)

    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    # Mid-run: the combo-meter tracks the running count.
    _funny(page, 0, 5)
    expect(page.locator("#ee-publika-meter")).to_contain_text(f"5/{THRESHOLD}")

    # Votes 6-10 finish the run; the 10th fires the payoff and clears the meter.
    _funny(page, 5, THRESHOLD)

    expect(page.locator("#toast-container .toast")).to_contain_text("Publika Rozgrzana")
    expect(page.locator("#ee-publika-meter")).to_have_count(0)

    page.wait_for_function(
        _AWARD_POLL_JS.format(slug=PUBLIKA_ROZGRZANA_SLUG),
        timeout=12_000,
    )
    ach = Achievement.objects.get(slug=PUBLIKA_ROZGRZANA_SLUG)
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login", "publika_rozgrzana_achievement")
def test_publika_rozgrzana_dry_vote_breaks_the_chain(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    _seed_suchary(THRESHOLD, e2e_user)

    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    # Four funny votes on cards 1-4, then a dry vote on card 0 (never funnied).
    _funny(page, 1, 5)
    expect(page.locator("#ee-publika-meter")).to_contain_text(f"4/{THRESHOLD}")

    _vote(page, page.locator('.btn-vote[data-vote-type="dry"]').nth(0))
    expect(page.locator("#ee-publika-meter")).to_have_count(0)

    # Five more funny votes (cards 5-9) only get the fresh chain to 5 — no payoff.
    _funny(page, 5, THRESHOLD)
    expect(page.locator("#ee-publika-meter")).to_contain_text(f"5/{THRESHOLD}")
    expect(
        page.locator('#toast-container .toast:has-text("Publika Rozgrzana")'),
    ).to_have_count(0)
    ach = Achievement.objects.get(slug=PUBLIKA_ROZGRZANA_SLUG)
    assert not UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login", "publika_rozgrzana_achievement")
def test_publika_rozgrzana_unvote_breaks_the_chain(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    _seed_suchary(THRESHOLD, e2e_user)

    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    funny = page.locator('.btn-vote[data-vote-type="funny"]')

    _funny(page, 0, 3)
    expect(page.locator("#ee-publika-meter")).to_contain_text(f"3/{THRESHOLD}")

    # Re-click card 0's funny button — this removes the vote, which is not
    # "a funny vote in a row" — so the meter disappears.
    _vote(page, funny.nth(0))
    expect(page.locator("#ee-publika-meter")).to_have_count(0)

    # Cards 3-4 start a fresh chain at 2, not a continuation to 5.
    _funny(page, 3, 5)
    expect(page.locator("#ee-publika-meter")).to_contain_text(f"2/{THRESHOLD}")
    expect(
        page.locator('#toast-container .toast:has-text("Publika Rozgrzana")'),
    ).to_have_count(0)
    ach = Achievement.objects.get(slug=PUBLIKA_ROZGRZANA_SLUG)
    assert not UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login", "publika_rozgrzana_achievement")
def test_publika_rozgrzana_respects_prefers_reduced_motion(
    page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    _seed_suchary(THRESHOLD, e2e_user)

    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    _funny(page, 0, 3)
    # Meter + count still render; the pulse @keyframes block is not injected.
    expect(page.locator("#ee-publika-meter")).to_contain_text(f"3/{THRESHOLD}")
    expect(page.locator("#ee-publika-style")).to_have_count(0)

    _funny(page, 3, THRESHOLD)  # continue the same chain to 10

    expect(page.locator("#toast-container .toast")).to_contain_text("Publika Rozgrzana")
    page.wait_for_function(
        _AWARD_POLL_JS.format(slug=PUBLIKA_ROZGRZANA_SLUG),
        timeout=12_000,
    )
    ach = Achievement.objects.get(slug=PUBLIKA_ROZGRZANA_SLUG)
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()
