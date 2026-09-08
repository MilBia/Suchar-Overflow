"""Static-markup guards for the frontend accessibility sweep (audit #364 phase 4).

Covers the parts of issues #340-#345 that live in rendered template output rather
than in runtime JS behaviour (that is exercised by ``tests/e2e/test_a11y.py``):

* #343 — every inline ``svgs/*.svg`` icon renders with ``aria-hidden="true"`` and
  icon-only controls (the brand link, the search submit button) carry an
  ``aria-label`` so they still have an accessible name.
* #344 — the previously hard-coded English ``aria-label``s are translated. The
  msgids are Polish (per the maintainer's i18n convention), so ``gettext`` on a
  suite that never compiles ``.mo`` files returns the msgid unchanged — the
  assertions compare against ``gettext(...)`` rather than a bare literal anyway.
* #345 — ``#toast-container`` is ``aria-live="polite"`` and carries the
  translated ``data-*`` fallbacks ``project.js`` reads.
* #340 — the language / sort dropdowns expose ``role="listbox"`` / ``role="option"``
  and ``aria-haspopup`` / ``aria-expanded`` on the trigger.
* #341 — the logout modal card is programmatically focusable and labelled.
"""

import re
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.models import Suchar

if TYPE_CHECKING:
    from collections.abc import Iterator

SVG_TAG_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)


def _get(client: Client, url: str) -> str:
    response = client.get(url)
    assert response.status_code == HTTPStatus.OK, (url, response.status_code)
    return response.content.decode()


def _svg_open_tags(html: str) -> Iterator[str]:
    return iter(SVG_TAG_RE.findall(html))


@pytest.fixture
def published_suchar(db: None) -> Suchar:  # noqa: ARG001
    return Suchar.objects.create(
        text="Dlaczego krab nigdy nie dzieli się jedzeniem? Bo jest skorupiakiem.",
        author=make_user("a11y_author"),
        published_at=timezone.now() - timedelta(minutes=5),
    )


# ---------------------------------------------------------------------------
# #343 — decorative SVG icons
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_every_inline_svg_on_home_is_aria_hidden() -> None:
    html = _get(Client(), reverse("home"))
    tags = list(_svg_open_tags(html))
    assert tags, "expected at least one inline <svg> on the home page"
    offenders = [t for t in tags if 'aria-hidden="true"' not in t]
    assert not offenders, f"inline <svg> without aria-hidden: {offenders}"


@pytest.mark.django_db
def test_every_inline_svg_on_suchary_list_is_aria_hidden(
    published_suchar: Suchar,  # noqa: ARG001
) -> None:
    html = _get(Client(), reverse("suchary:list"))
    offenders = [t for t in _svg_open_tags(html) if 'aria-hidden="true"' not in t]
    assert not offenders, f"inline <svg> without aria-hidden: {offenders}"


@pytest.mark.django_db
def test_icon_only_controls_keep_an_accessible_name() -> None:
    """The brand link wraps only logo.svg; the search button only icon-search.svg."""
    home = _get(Client(), reverse("home"))
    assert re.search(r'<a[^>]*class="navbar-brand[^"]*"[^>]*aria-label="', home)


@pytest.mark.django_db
def test_search_submit_button_has_aria_label(
    published_suchar: Suchar,  # noqa: ARG001
) -> None:
    html = _get(Client(), reverse("suchary:list"))
    # The submit button holds only an SVG — assert the label is on the <button>
    # itself, not merely somewhere on the page (the search <input> has one too).
    assert re.search(
        r'<button[^>]*type="submit"[^>]*aria-label="' + re.escape(gettext("Szukaj")),
        html,
        re.DOTALL,
    )


@pytest.mark.django_db
def test_achievement_card_icon_wrapper_is_hidden_from_a11y_tree() -> None:
    achievement = Achievement.objects.create(
        name="A11y Test",
        slug="a11y-test-card",
        description="Decorative icon must be hidden from the a11y tree.",
        icon_content='<svg aria-hidden="true"></svg>',
    )
    html = render_to_string(
        "achievements/_card.html",
        {"achievement": achievement, "locked": False, "is_secret": False},
    )
    assert re.search(
        r'class="achievement-icon-wrapper[^"]*"\s+aria-hidden="true"',
        html,
    )


@pytest.mark.django_db
def test_profile_badge_grid_is_keyboard_reachable_and_described() -> None:
    """#343's singled-out spot: the profile badge must be focusable, named and
    describe-linked to its (CSS-hidden) description — name alone isn't enough."""
    profile_user = make_user("a11y_profile")
    achievement = Achievement.objects.create(
        name="Cichy Zabójca Suszu",
        slug="a11y-badge-grid",
        description="Its description must reach the screen reader too.",
        icon_content="<svg></svg>",
    )
    UserAchievement.objects.create(user=profile_user, achievement=achievement)

    client = Client()
    client.force_login(profile_user)
    html = _get(
        client,
        reverse("users:detail", kwargs={"username": profile_user.username}),
    )
    badge = re.search(
        r'<div class="achievement-badge-icon-wrapper[^"]*"[^>]*>',
        html,
        re.DOTALL,
    )
    assert badge is not None
    tag = badge.group(0)
    assert 'tabindex="0"' in tag
    assert 'aria-label="Cichy Zabójca Suszu"' in tag
    descr_id = re.search(r'aria-describedby="([^"]+)"', tag)
    assert descr_id is not None
    # The description it points at is really in the DOM (visually hidden by CSS,
    # but aria-describedby still resolves it).
    assert re.search(
        rf'id="{re.escape(descr_id.group(1))}"[^>]*>{re.escape(achievement.description)}',
        html,
    )
    # The duplicate decorative icon inside the popover stays hidden.
    assert re.search(
        r'class="achievement-details-icon[^"]*"\s+aria-hidden="true"',
        html,
    )


# ---------------------------------------------------------------------------
# #344 — translated aria-labels
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_navbar_toggler_and_theme_toggle_labels_are_translated() -> None:
    html = _get(Client(), reverse("home"))
    assert f'aria-label="{gettext("Przełącz nawigację")}"' in html
    assert f'aria-label="{gettext("Przełącz motyw")}"' in html
    # The old hard-coded English strings are gone.
    assert 'aria-label="Toggle navigation"' not in html
    assert 'aria-label="Toggle theme"' not in html


@pytest.mark.django_db
def test_close_buttons_use_translated_label() -> None:
    client = Client()
    client.force_login(make_user("a11y_close"))
    html = _get(client, reverse("home"))
    assert f'aria-label="{gettext("Zamknij")}"' in html
    assert 'aria-label="Close"' not in html


@pytest.mark.django_db
def test_bell_button_label_matches_the_polish_msgid_convention() -> None:
    client = Client()
    client.force_login(make_user("a11y_bell"))
    html = _get(client, reverse("home"))
    assert re.search(
        r'id="bell-btn"[^>]*aria-label="' + re.escape(gettext("Powiadomienia")),
        html,
        re.DOTALL,
    )
    assert 'aria-label="Notifications"' not in html


@pytest.mark.django_db
def test_language_search_field_has_an_accessible_name() -> None:
    html = _get(Client(), reverse("home"))
    assert re.search(
        r'class="language-search"[^>]*aria-label="'
        + re.escape(gettext("Szukaj języka")),
        html,
        re.DOTALL,
    )


@pytest.mark.django_db
def test_anonymous_vote_tooltip_is_polish_msgid(
    published_suchar: Suchar,  # noqa: ARG001
) -> None:
    html = _get(Client(), reverse("suchary:list"))
    assert f'data-tooltip="{gettext("Zaloguj się, aby głosować")}"' in html
    assert 'data-tooltip="Log in to vote"' not in html


# ---------------------------------------------------------------------------
# #345 — toast live region
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_toast_container_is_polite_with_translated_fallbacks() -> None:
    html = _get(Client(), reverse("home"))
    container = re.search(r'<div class="toast-container".*?>', html, re.DOTALL)
    assert container, "toast container not found"
    block = container.group(0)
    assert 'aria-live="polite"' in block
    assert 'aria-live="assertive"' not in block
    assert f'data-close-text="{gettext("Zamknij")}"' in block
    assert f'data-default-title="{gettext("Powiadomienie")}"' in block


# ---------------------------------------------------------------------------
# #340 — dropdown ARIA semantics
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_language_dropdown_exposes_listbox_semantics() -> None:
    html = _get(Client(), reverse("home"))
    trigger = re.search(
        r'<button[^>]*class="dropdown-trigger"[^>]*>',
        html,
        re.DOTALL,
    )
    assert trigger, "language dropdown trigger not found"
    assert 'aria-haspopup="listbox"' in trigger.group(0)
    assert 'aria-expanded="false"' in trigger.group(0)
    assert re.search(r'class="language-list"[^>]*role="listbox"', html)
    assert re.search(r'class="dropdown-item[^"]*"\s+role="option"', html)
    assert 'aria-selected="true"' in html


@pytest.mark.django_db
def test_sort_dropdown_exposes_listbox_semantics(
    published_suchar: Suchar,  # noqa: ARG001
) -> None:
    html = _get(Client(), reverse("suchary:list"))
    assert re.search(
        r'<button[^>]*class="dropdown-trigger"[^>]*aria-haspopup="listbox"',
        html,
        re.DOTALL,
    )
    assert re.search(r'class="dropdown-menu"[^>]*role="listbox"', html)
    assert re.search(r'class="dropdown-item[^"]*"\s+role="option"', html)


# ---------------------------------------------------------------------------
# #341 — logout modal is focusable + labelled
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_logout_modal_card_is_programmatically_focusable() -> None:
    client = Client()
    client.force_login(make_user("a11y_modal"))
    html = _get(client, reverse("home"))
    modal = re.search(r'<div class="modal"[^>]*>', html)
    assert modal, "logout modal card not found"
    assert 'tabindex="-1"' in modal.group(0)
    assert 'aria-labelledby="logoutModalTitle"' in modal.group(0)
    assert 'id="logoutModalTitle"' in html
