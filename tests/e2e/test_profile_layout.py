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

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

if TYPE_CHECKING:
    from typing import Any

    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.users.models import User as UserModel

User = get_user_model()

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
    """Published suchary with votes, so best-joke, badges and charts all render."""
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
