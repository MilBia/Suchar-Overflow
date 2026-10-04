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

# Transitions are switched off first, so computed styles read right after the
# theme change are the final values, not mid-transition ones (#504 review).
_SET_THEME_JS = """
(theme) => {
  const style = document.createElement('style');
  style.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; }';
  document.head.append(style);
  document.documentElement.dataset.theme = theme;
}
"""

# WCAG AA for normal-size text; the alert's text sits on its own translucent tint
# composited over the page background (#504 review: measure, don't compute by hand).
_MIN_CONTRAST = 4.5

_CONTRAST_JS = """
() => {
  const parse = (v) => v.match(/[\\d.]+/g).map(Number);
  const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  const page = parse(getComputedStyle(document.body).backgroundColor);
  const [r, g, b, a = 1] = parse(getComputedStyle(document.querySelector('.alert-success')).backgroundColor);
  const bg = [r, g, b].map((c, i) => c * a + page[i] * (1 - a));
  const fg = parse(getComputedStyle(document.querySelector('.alert-success')).color);
  const [hi, lo] = [lum(fg), lum(bg)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
"""

# Contrast of a probe element's text against whatever it is painted on: every ancestor's
# background composited bottom-up (#508). `selector` probes are appended inside a surface card.
_PROBE_CONTRAST_JS = """
([className]) => {
  const parse = (v) => v.match(/[\\d.]+/g).map(Number);
  const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  const surface = document.createElement('div');
  surface.style.background = 'var(--bg-surface)';
  const el = document.createElement('div');
  el.className = className;
  el.textContent = 'x';
  surface.append(el);
  document.body.append(surface);
  const layers = [];
  for (let n = el; n; n = n.parentElement) layers.unshift(parse(getComputedStyle(n).backgroundColor));
  let bg = [255, 255, 255];
  for (const [r, g, b, a = 1] of layers) bg = [r, g, b].map((c, i) => c * a + bg[i] * (1 - a));
  const fg = parse(getComputedStyle(el).color);
  const [hi, lo] = [lum(fg), lum(bg)].sort((x, y) => y - x);
  surface.remove();
  return (hi + 0.05) / (lo + 0.05);
}
"""

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
        "background-color",
    )
    assert alert["border-top-width"] == "1px"
    assert alert["padding-top"] == "16px"
    assert alert["border-top-left-radius"] == "12px"  # --radius-md
    assert alert["color"] != _style(page, "body", "color")["color"]
    assert alert["background-color"] not in {"rgba(0, 0, 0, 0)", "transparent"}
    contrast = page.evaluate(_CONTRAST_JS)
    assert contrast >= _MIN_CONTRAST, f"alert-success contrast {contrast:.2f}:1 in {theme} theme"

    # A bare `.alert` must not disturb `.alert-danger`, which carries its own look.
    page.evaluate(
        """() => {
          const d = document.createElement('div');
          d.id = 'probe-danger';
          d.className = 'alert alert-danger';
          document.body.append(d);
        }""",
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


@pytest.mark.parametrize(
    "class_name",
    ["alert alert-danger", "invalid-feedback", "char-counter is-error", "error-bubble"],
)
def test_error_red_text_meets_contrast(login: Page, live_server: LiveServer, theme: str, class_name: str) -> None:
    # The suchar form loads both the global sheet and the page sheet that owns `.char-counter`.
    page = login
    page.goto(f"{live_server.url}/suchary/add/")
    page.evaluate(_SET_THEME_JS, theme)
    contrast = page.evaluate(_PROBE_CONTRAST_JS, [class_name])
    assert contrast >= _MIN_CONTRAST, f"{class_name!r} contrast {contrast:.2f}:1 in {theme} theme"


@pytest.mark.parametrize(
    ("width", "expected"),
    [(600, "normal"), (820, "normal"), (1100, "flex-end")],
)
def test_justify_content_lg_end_starts_at_992px(page: Page, live_server: LiveServer, width: int, expected: str) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{live_server.url}/suchary/")
    value = _style(page, "form.search-toolbar", "justify-content")["justify-content"]
    assert value == expected, f"justify-content at {width}px"
