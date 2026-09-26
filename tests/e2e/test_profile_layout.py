"""E2E guard for the profile stats column width (#406).

The profile's stats/feed split used to be a nested viewport grid
(`col-md-4 col-xl-3` inside the dashboard's `col-lg-9`), so at >= 1200px the
stats column shrank to ~150px of text: labels broke word-by-word and the F/D
badges and "Dołączył …" spilled out of their cards. It is now a CSS grid driven
by a container query on `.profile-body` (pages/profile.css). `just test` has no
CSS coverage, so this measures the real layout in a browser.
"""

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

if TYPE_CHECKING:
    from typing import Any

    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.users.models import User as UserModel

User = get_user_model()

# Enough badges to wrap onto several rows in the narrowest stats column. The
# migration-seeded achievements are flushed by transaction=True, so the test
# brings its own (cf. frontend_achievements in test_hidden_achievements.py).
_BADGE_COUNT = 8
_BADGE_SVG = (
    '<svg viewBox="0 0 16 16" width="16" height="16">'
    '<circle cx="8" cy="8" r="7" fill="currentColor"/></svg>'
)

# The narrowest the stats column may get while it sits beside the feed.
_MIN_STATS_WIDTH = 260

# Every element of a stats card must stay inside the card (sub-pixel slack).
# The achievement popover is excluded: it is absolutely positioned and meant to
# float over its neighbours.
_OVERFLOW_JS = """
() => {
  const out = [];
  for (const card of document.querySelectorAll('.profile-stats > .card')) {
    const box = card.getBoundingClientRect();
    for (const el of card.querySelectorAll('*')) {
      if (el.closest('.achievement-details-popover')) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      if (r.left < box.left - 0.5 || r.right > box.right + 0.5) {
        const text = el.textContent.trim().slice(0, 30);
        out.push(`${el.tagName}.${el.className}: ${text}`);
      }
    }
  }
  return out;
}
"""

_WIDTHS_JS = """
() => ({
  stats: document.querySelector('.profile-stats').getBoundingClientRect().width,
  layout: document.querySelector('.profile-layout').getBoundingClientRect().width,
  pageOverflow:
    document.documentElement.scrollWidth - document.documentElement.clientWidth,
})
"""


def _profile_data(owner: UserModel, voter: UserModel) -> None:
    """Published suchary, votes and badges, so every stats card renders filled."""
    for i in range(_BADGE_COUNT):
        achievement, _ = Achievement.objects.get_or_create(
            slug=f"e2e-profile-layout-{i}",
            defaults={
                "name": f"Odznaka testowa {i}",
                "description": "Odznaka tylko do testu układu profilu.",
                "icon_content": _BADGE_SVG,
                "category": Achievement.Category.LIFETIME,
                "event_type": Achievement.EventType.FRONTEND,
                "metric": Achievement.Metric.FRONTEND_EVENT,
                "threshold": 1,
            },
        )
        UserAchievement.objects.get_or_create(user=owner, achievement=achievement)
    published = timezone.now() - timedelta(hours=1)
    for text in (
        "Dlaczego programista nosi okulary? Bo nie widzi C#.",
        "Co mówi zero do ósemki? Fajny pasek!",
    ):
        suchar = Suchar.objects.create(text=text, author=owner, published_at=published)
        Vote.objects.create(user=voter, suchar=suchar, is_funny=True)


@pytest.fixture
def other_user(db: None) -> UserModel:  # noqa: ARG001
    return User.objects.create_user(
        username="innyprofil",
        email="inny@test.example.com",
        password="unused-password-123",  # noqa: S106
    )


@pytest.fixture(params=["own", "other"])
def profile_url(
    request: pytest.FixtureRequest,
    live_server: LiveServer,
    e2e_user: UserModel,
    other_user: UserModel,
) -> str:
    """URL of the logged-in user's own profile, or of someone else's.

    The two differ in the dashboard column around the profile: col-lg-9 beside
    the account menu vs. col-12 col-lg-10 without it.
    """
    if request.param == "own":
        owner, voter = e2e_user, other_user
    else:
        owner, voter = other_user, e2e_user
    _profile_data(owner, voter)
    return f"{live_server.url}/users/{owner.username}/"


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport_width", [375, 992, 1200, 1440, 1920])
def test_profile_stats_column_is_not_squeezed(
    login: Page,
    profile_url: str,
    viewport_width: int,
) -> None:
    page = login
    page.set_viewport_size({"width": viewport_width, "height": 900})
    page.goto(profile_url)
    page.wait_for_selector("#userReceptionChart")

    widths: dict[str, Any] = page.evaluate(_WIDTHS_JS)
    # Either beside the feed with a usable width, or stacked at full width.
    assert (
        widths["stats"] >= _MIN_STATS_WIDTH
        or abs(widths["stats"] - widths["layout"]) < 1
    ), widths
    assert widths["pageOverflow"] <= 0, widths
    assert page.evaluate(_OVERFLOW_JS) == []
    badges = page.locator(".profile-stats .achievement-container")
    assert badges.count() == _BADGE_COUNT


# Dashboard chrome around the profile (#415): `card-body p-0` used to render
# cards.css's 32px, the dashboard nested a second .container inside base.html's,
# and the account menu clipped "BEZPIECZEŃSTWO" at ~992px.
_DASHBOARD_JS = """
() => {
  const pad = (sel) => {
    const el = document.querySelector(sel);
    return el ? getComputedStyle(el).paddingLeft : null;
  };
  const content = document.querySelector('.profile-body');
  // Each menu label must fit inside its own row: the rows sit in an
  // overflow-hidden .list-group, so a label running past its row is cut off
  // there (the card itself is wider and would not notice).
  const clipped = [];
  for (const row of document.querySelectorAll('.dashboard-card .list-group > *')) {
    const box = row.getBoundingClientRect();
    for (const el of row.querySelectorAll('span')) {
      const r = el.getBoundingClientRect();
      if (r.right > box.right + 0.5 || r.left < box.left - 0.5) {
        clipped.push(el.textContent.trim());
      }
    }
  }
  return {
    nestedContainers: document.querySelectorAll('.container .container').length,
    profileBodyPad: pad('.profile-body'),
    profileCardBodyPad: pad('.card:has(> .profile-cover) > .card-body'),
    menuCardBodyPad: pad('.dashboard-card > .card-body'),
    contentLeft: content.getBoundingClientRect().left
      + parseFloat(getComputedStyle(content).paddingLeft),
    clipped,
  };
}
"""


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport_width", [375, 992, 1200])
def test_dashboard_chrome(
    login: Page,
    profile_url: str,
    viewport_width: int,
) -> None:
    page = login
    page.set_viewport_size({"width": viewport_width, "height": 900})
    page.goto(profile_url)
    page.wait_for_selector("#userReceptionChart")

    result: dict[str, Any] = page.evaluate(_DASHBOARD_JS)
    assert result["nestedContainers"] == 0, result
    assert result["profileCardBodyPad"] == "0px", result
    if result["menuCardBodyPad"] is not None:
        assert result["menuCardBodyPad"] == "0px", result
    assert result["clipped"] == [], result
    if viewport_width == 375:  # noqa: PLR2004
        # 16px container gutter + 1px card border + 16px .profile-body inset.
        assert result["profileBodyPad"] == "16px", result
        assert result["contentLeft"] <= 33.5, result  # noqa: PLR2004


# The badge popover stays on screen when shown (#415): centred on a badge near
# the card's right edge it ran past the viewport. Resolves once the popover has
# finished its 0.1s delay + 0.3s transition (a Promise, not a bare expression —
# the app CSP has no 'unsafe-eval').
_POPOVER_RECT_JS = """
() => new Promise((resolve) => {
  const pop = [...document.querySelectorAll('.achievement-details-popover')].at(-1);
  const poll = () => {
    if (getComputedStyle(pop).opacity !== '1') return setTimeout(poll, 50);
    const r = pop.getBoundingClientRect();
    resolve({
      left: r.left,
      right: r.right,
      clientWidth: document.documentElement.clientWidth,
    });
  };
  poll();
})
"""


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("viewport_width", [375, 768, 1200])
def test_achievement_popover_stays_on_screen(
    login: Page,
    profile_url: str,
    viewport_width: int,
) -> None:
    page = login
    page.set_viewport_size({"width": viewport_width, "height": 900})
    page.goto(profile_url)
    page.wait_for_selector("#userReceptionChart")

    page.locator(".achievement-badge-icon-wrapper").last.focus()
    rect: dict[str, Any] = page.evaluate(_POPOVER_RECT_JS)
    assert rect["left"] >= 0, rect
    assert rect["right"] <= rect["clientWidth"], rect
