"""E2E guard for utility classes the templates use and the SCSS must define (#504).

`.border`, `.alert`/`.alert-success`, `.rounded`-style radius and `.fw-normal` were
used in templates with no matching rule, so their elements rendered unstyled.
`just test` has no CSS coverage, so these assert computed styles in a real
browser, in both themes.
"""

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.users.models import User as UserModel

User = get_user_model()

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

_THEMES = ["light", "dark"]

_SET_THEME_JS = "(theme) => { document.documentElement.dataset.theme = theme; }"

_STYLE_JS = """
([selector, props]) => {
  const el = document.querySelector(selector);
  if (!el) return null;
  const cs = getComputedStyle(el);
  return Object.fromEntries(props.map((p) => [p, cs.getPropertyValue(p)]));
}
"""


def _style(page: Page, selector: str, *props: str) -> dict[str, str]:
    result = page.evaluate(_STYLE_JS, [selector, list(props)])
    assert result is not None, f"no element matches {selector!r}"
    return result


@pytest.fixture(params=_THEMES)
def theme(request: pytest.FixtureRequest) -> str:
    return request.param


def test_filter_chips_and_bar_are_styled(login: Page, live_server: LiveServer, theme: str) -> None:
    page = login
    page.goto(f"{live_server.url}/suchary/?tag=x&q=a&author=e2etestuser")
    page.evaluate(_SET_THEME_JS, theme)

    chip = _style(page, "div.badge.border", "border-top-width", "border-top-style")
    assert chip["border-top-width"] == "1px"
    assert chip["border-top-style"] == "solid"

    bar = _style(page, "div.bg-light.border.p-3", "border-top-left-radius")
    assert float(bar["border-top-left-radius"].removesuffix("px")) > 0


def test_alert_success_is_styled_and_alert_danger_unchanged(page: Page, live_server: LiveServer, theme: str) -> None:
    page.goto(f"{live_server.url}/accounts/password_reset/done/")
    page.evaluate(_SET_THEME_JS, theme)

    alert = _style(
        page,
        ".alert-success",
        "border-top-width",
        "padding-top",
        "color",
        "border-top-left-radius",
    )
    assert alert["border-top-width"] == "1px"
    assert alert["padding-top"] == "16px"
    assert alert["color"] != _style(page, "body", "color")["color"]

    # A bare `.alert` must not disturb `.alert-danger`, which carries its own look.
    page.evaluate(
        """() => {
          const d = document.createElement('div');
          d.id = 'probe-danger';
          d.className = 'alert alert-danger';
          document.body.append(d);
        }"""
    )
    danger = _style(page, "#probe-danger", "border-top-width", "padding-top", "margin-bottom", "font-weight")
    assert danger == {
        "border-top-width": "1px",
        "padding-top": "16px",
        "margin-bottom": "24px",
        "font-weight": "500",
    }


def test_profile_rank_number_is_not_bold(
    login: Page,
    live_server: LiveServer,
    e2e_user: UserModel,
    theme: str,
) -> None:
    voter = User.objects.create_user(username="ranguser", email="rang@test.example.com", password="unused-pass-123")
    suchar = Suchar.objects.create(
        text="Suchar do rangi.",
        author=e2e_user,
        published_at=timezone.now() - timedelta(hours=1),
    )
    Vote.objects.create(user=voter, suchar=suchar, is_funny=True)

    page = login
    page.goto(f"{live_server.url}/users/{e2e_user.username}/")
    page.evaluate(_SET_THEME_JS, theme)

    assert _style(page, "span.fw-normal", "font-weight")["font-weight"] == "400"
