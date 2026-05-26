"""E2E tests for the 5 hidden frontend achievements (hidden_achievements.js).

Strategy per achievement:
- odkrywca: seed localStorage to 4, navigate to /achievements/ (5th visit fires)
- zbieracz_sucharow: seed sessionStorage to 4, navigate to /suchary/ (5th fires)
- niecierpliwy: seed sessionStorage to 2, dispatch short-text form submit (3rd)
- stluczona_mysz: click the same vote button 5 times (in-memory counter)
- recenzent_totalny: POST directly to the API from the authenticated browser
  context (hovered-Set is per-page; list paginates at 10 so the real hover
  path cannot accumulate across navigations — direct fetch tests auth+CSRF+API)
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar

User = get_user_model()

TEST_PASSWORD = "e2e-test-password-123"  # noqa: S105

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POLL_JS = """
    new Promise((resolve) => {{
        const check = () => {{
            fetch('/api/achievements/frontend-owned')
                .then(r => r.json())
                .then(slugs => {{
                    if (slugs.includes('{slug}')) resolve(true);
                    else setTimeout(check, 300);
                }});
        }};
        check();
    }})
"""

_DIRECT_AWARD_JS = """
    new Promise((resolve, reject) => {{
        const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
                      document.querySelector('meta[name="csrf-token"]')
                        ?.getAttribute('content') ||
                      '';
        fetch('/api/achievements/frontend-event', {{
            method: 'POST',
            headers: {{
                'Content-Type': 'application/json',
                'X-CSRFToken': token,
            }},
            body: JSON.stringify({{ event_slug: '{slug}' }}),
        }})
        .then(r => r.json())
        .then(resolve)
        .catch(reject);
    }})
"""


def _wait_for_award(page, slug, timeout=12_000):
    """Poll the frontend-owned endpoint until *slug* appears, or raise on timeout."""
    page.wait_for_function(
        _POLL_JS.format(slug=slug),
        timeout=timeout,
    )


# Slugs and minimal metadata for the 5 hidden frontend achievements.
# Mirrors data from migration 0008_achievement_frontend_data.py.
_FRONTEND_ACHIEVEMENT_DEFS = [
    ("frontend-odkrywca", "Odkrywca"),
    ("frontend-zbieracz-sucharow", "Zbieracz Sucharów"),
    ("frontend-niecierpliwy", "Niecierpliwy"),
    ("frontend-stluczona-mysz", "Stłuczona Mysz"),
    ("frontend-recenzent-totalny", "Recenzent Totalny"),
]

# ---------------------------------------------------------------------------
# Fixtures specific to this module
# ---------------------------------------------------------------------------


@pytest.fixture
def frontend_achievements(db):
    """Ensure all 5 hidden frontend achievements exist in the test DB.

    transaction=True tests truncate tables between runs, wiping the data
    seeded by migration 0008.  This fixture re-creates them as needed.
    """
    rows = []
    for slug, name in _FRONTEND_ACHIEVEMENT_DEFS:
        ach, _ = Achievement.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": f"Hidden frontend achievement: {name}.",
                "icon_content": "<svg></svg>",
                "category": Achievement.Category.LIFETIME,
                "event_type": Achievement.EventType.FRONTEND,
                "metric": Achievement.Metric.FRONTEND_EVENT,
                "threshold": 1,
                "is_secret": True,
            },
        )
        rows.append(ach)
    return rows


@pytest.fixture
def other_user(db):
    """A second user who authors suchars so the test user can vote on them."""
    return User.objects.create_user(
        username="other_e2e_user",
        email="other_e2e@test.example.com",
        password=TEST_PASSWORD,
    )


@pytest.fixture
def suchar_by_other(db, other_user):
    """One published suchar authored by *other_user*."""
    return Suchar.objects.create(
        text="Dlaczego programiści nie lubią lasu? Bo drzewa mają za dużo gałęzi.",
        author=other_user,
        published_at=timezone.now() - timedelta(minutes=5),
    )


# ---------------------------------------------------------------------------
# Achievement 1 — frontend-odkrywca
# Visit /achievements/ 5 times (localStorage key: odkrywca_visits).
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_odkrywca_achievement_awarded_after_five_visits(
    page,
    live_server,
    login,
    e2e_user,
    frontend_achievements,
):
    """Visiting /achievements/ 5 times earns the Odkrywca achievement."""
    # Navigate once so localStorage is available for the right origin.
    page.goto(f"{live_server.url}/achievements/")
    page.wait_for_load_state("networkidle")

    # Pre-seed to 4 — next real navigation is the 5th visit.
    page.evaluate("localStorage.setItem('odkrywca_visits', '4')")
    # Clear the per-session award guard so the award can fire again.
    page.evaluate("sessionStorage.removeItem('awarded_frontend-odkrywca')")

    # 5th navigation: JS reads 4, increments to 5, posts award.
    page.goto(f"{live_server.url}/achievements/")
    page.wait_for_load_state("networkidle")

    _wait_for_award(page, "frontend-odkrywca")

    ach = Achievement.objects.get(slug="frontend-odkrywca")
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()


# ---------------------------------------------------------------------------
# Achievement 2 — frontend-zbieracz-sucharow
# Load /suchary/ 5 times without voting (sessionStorage: zbieracz_pages).
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_zbieracz_sucharow_awarded_after_five_list_visits(  # noqa: PLR0913
    page,
    live_server,
    login,
    e2e_user,
    suchar_by_other,
    frontend_achievements,
):
    """Browsing /suchary/ 5 times without voting earns Zbieracz Sucharów."""
    # Navigate once so sessionStorage is available for the right origin.
    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_load_state("networkidle")

    # Pre-seed to 4 — next real navigation tips it to 5.
    page.evaluate("sessionStorage.setItem('zbieracz_pages', '4')")
    page.evaluate("sessionStorage.removeItem('awarded_frontend-zbieracz-sucharow')")

    # 5th visit — JS reads 4, increments to 5, clears key, posts award.
    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_load_state("networkidle")

    _wait_for_award(page, "frontend-zbieracz-sucharow")

    ach = Achievement.objects.get(slug="frontend-zbieracz-sucharow")
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()


# ---------------------------------------------------------------------------
# Achievement 3 — frontend-niecierpliwy
# Submit the suchar form with <10 chars 3 times (sessionStorage: niecierpliwy_count).
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_niecierpliwy_awarded_after_three_short_submissions(
    page,
    live_server,
    login,
    e2e_user,
    frontend_achievements,
):
    """Submitting the suchar form with <10 chars 3 times earns Niecierpliwy."""
    page.goto(f"{live_server.url}/suchary/add/")
    page.wait_for_load_state("networkidle")

    # Pre-seed to 2 — the next short submit is the 3rd.
    page.evaluate("sessionStorage.setItem('niecierpliwy_count', '2')")
    page.evaluate("sessionStorage.removeItem('awarded_frontend-niecierpliwy')")

    # Fill a short text and fire the submit event programmatically.
    # The JS 'submit' listener runs synchronously, sees < 10 chars, increments to 3,
    # and calls award() which fires awardAchievement() (async fetch).
    # We dispatch the event without letting the browser navigate so we can poll.
    page.fill("#id_text", "Hej")
    page.evaluate(
        "document.querySelector('#id_text').closest('form')"
        ".dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}))",
    )

    _wait_for_award(page, "frontend-niecierpliwy")

    ach = Achievement.objects.get(slug="frontend-niecierpliwy")
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()


# ---------------------------------------------------------------------------
# Achievement 4 — frontend-stluczona-mysz
# Click a vote button on the same suchar 5 times.
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_stluczona_mysz_awarded_after_five_clicks_on_same_button(  # noqa: PLR0913
    page,
    live_server,
    login,
    e2e_user,
    suchar_by_other,
    frontend_achievements,
):
    """Clicking a vote button on the same suchar 5 times earns Stłuczona Mysz."""
    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_load_state("networkidle")

    pk = suchar_by_other.pk
    funny_btn = page.locator(
        f"button.btn-vote[data-suchar-id='{pk}'][data-vote-type='funny']",
    )

    # 5 clicks — the JS in-memory counter fires the award on the 5th.
    # Small pauses ensure the event listener sees each click separately.
    for _ in range(5):
        funny_btn.click()
        page.wait_for_timeout(150)

    _wait_for_award(page, "frontend-stluczona-mysz")

    ach = Achievement.objects.get(slug="frontend-stluczona-mysz")
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()


# ---------------------------------------------------------------------------
# Achievement 5 — frontend-recenzent-totalny
# Hover 20 different suchar cards for 3+ seconds each.
#
# The list view paginates at 10, so accumulating 20 hover-seconds across
# page loads is impossible with the in-page Set (it resets on navigation).
# Instead we POST the award directly from the authenticated browser context
# using the same fetch() call that hidden_achievements.js itself uses.
# This validates the complete E2E path: session auth → CSRF cookie → API
# endpoint → UserAchievement row created in DB.
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_recenzent_totalny_awarded_via_direct_api_post(
    page,
    live_server,
    login,
    e2e_user,
    frontend_achievements,
):
    """Posting recenzent-totalny from an authenticated browser creates the DB award."""
    # Navigate to any page to establish CSRF cookie in the browser.
    page.goto(f"{live_server.url}/suchary/")
    page.wait_for_load_state("networkidle")

    result = page.evaluate(_DIRECT_AWARD_JS.format(slug="frontend-recenzent-totalny"))
    assert result == {"ok": True}

    ach = Achievement.objects.get(slug="frontend-recenzent-totalny")
    assert UserAchievement.objects.filter(user=e2e_user, achievement=ach).exists()
