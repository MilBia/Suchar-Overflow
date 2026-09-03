"""Tests for the "Recydywa" / repeat-offender achievement (#297).

Two layers, matching the "Mistrz Suszu" (#294) design:

* :class:`EditCountRule` is a threshold-independent metric — it reports the
  highest ``edit_count`` among the user's suchary.
* ``Suchar.edit_count`` is incremented by ``SucharUpdateView.post`` on every
  successful save inside the edit window, which then fires the
  ``suchar_edited`` signal; ``achievements.signals`` re-runs the engine for
  the author. The engine only awards, never revokes.
"""

import re
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from suchar_overflow.achievements.engine import EditCountRule
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.signals import suchar_edited

if TYPE_CHECKING:
    from django.test import Client

RECYDYWA_SLUG = "recydywa"
RECYDYWA_THRESHOLD = 5


@pytest.fixture
def recydywa_achievement() -> Achievement:
    achievement, _ = Achievement.objects.get_or_create(
        slug=RECYDYWA_SLUG,
        defaults={
            "name": "Recydywa",
            "description": "desc",
            "icon_content": "<svg/>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.SUCHAR_EDITED,
            "metric": Achievement.Metric.EDIT_COUNT,
            "threshold": RECYDYWA_THRESHOLD,
            "is_secret": True,
        },
    )
    return achievement


def _bump_edit_count(suchar: Suchar) -> None:
    Suchar.objects.filter(pk=suchar.pk).update(edit_count=F("edit_count") + 1)


# ---------------------------------------------------------------------------
# EditCountRule — threshold-independent metric
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rule_returns_none_without_any_suchar() -> None:
    user = make_user("author")
    assert EditCountRule.compute_value(user) is None


@pytest.mark.django_db
def test_rule_reports_highest_edit_count_among_authored_suchary() -> None:
    user = make_user("author")
    Suchar.objects.create(text="a", author=user, edit_count=2)
    Suchar.objects.create(text="b", author=user, edit_count=7)
    Suchar.objects.create(text="c", author=user, edit_count=0)
    assert EditCountRule.compute_value(user) == 7  # noqa: PLR2004


@pytest.mark.django_db
def test_rule_ignores_other_authors_edits() -> None:
    user = make_user("author")
    other = make_user("other")
    Suchar.objects.create(text="mine", author=user, edit_count=1)
    Suchar.objects.create(text="theirs", author=other, edit_count=9)
    assert EditCountRule.compute_value(user) == 1


@pytest.mark.django_db
def test_rule_evaluate_true_once_threshold_reached() -> None:
    user = make_user("author")
    Suchar.objects.create(text="a", author=user, edit_count=RECYDYWA_THRESHOLD)
    assert EditCountRule.evaluate(user, threshold=RECYDYWA_THRESHOLD)


@pytest.mark.django_db
def test_rule_evaluate_false_below_threshold() -> None:
    user = make_user("author")
    Suchar.objects.create(text="a", author=user, edit_count=RECYDYWA_THRESHOLD - 1)
    assert not EditCountRule.evaluate(user, threshold=RECYDYWA_THRESHOLD)


# ---------------------------------------------------------------------------
# suchar_edited signal -> engine
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("recydywa_achievement")
def test_fifth_edit_awards_recydywa() -> None:
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)

    for _ in range(RECYDYWA_THRESHOLD):
        _bump_edit_count(suchar)
        suchar_edited.send(sender=Suchar, author=author, suchar=suchar)

    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug=RECYDYWA_SLUG,
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("recydywa_achievement")
def test_fourth_edit_does_not_award() -> None:
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)

    for _ in range(RECYDYWA_THRESHOLD - 1):
        _bump_edit_count(suchar)
        suchar_edited.send(sender=Suchar, author=author, suchar=suchar)

    assert not UserAchievement.objects.filter(
        user=author,
        achievement__slug=RECYDYWA_SLUG,
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("recydywa_achievement")
def test_recydywa_is_not_awarded_twice() -> None:
    author = make_user("author")
    suchar = Suchar.objects.create(
        text="joke",
        author=author,
        edit_count=RECYDYWA_THRESHOLD,
    )

    for _ in range(3):
        suchar_edited.send(sender=Suchar, author=author, suchar=suchar)

    assert (
        UserAchievement.objects.filter(
            user=author,
            achievement__slug=RECYDYWA_SLUG,
        ).count()
        == 1
    )


# ---------------------------------------------------------------------------
# SucharUpdateView — increments the counter and awards through the real path
# ---------------------------------------------------------------------------


def _rendered_publish_value(html: str) -> str:
    """The ``published_at`` value the edit form actually renders.

    ``suchar_form.html`` emits ``<input name="published_at" value="Y-m-d H:i">``
    for a scheduled suchar. A browser resends exactly that string on the next
    edit — so a repeated-edit run must post it back verbatim, not a synthetic
    date. If this stops matching, the edit form no longer round-trips
    ``published_at`` and every edit would republish the suchar (capping
    ``edit_count`` at 1 and making "Recydywa" unreachable).
    """
    match = re.search(r'name="published_at"[^>]*value="([^"]*)"', html)
    assert match is not None
    assert match.group(1), "edit form rendered an empty published_at"
    return match.group(1)


def _edit_once(client: Client, url: str, text: str) -> None:
    """GET the edit form, then POST it back the way a browser would.

    Asserts the save redirected (302) — an unpublished suchar staying
    editable is exactly what makes repeated edits, and thus "Recydywa",
    possible.
    """
    page = client.get(url)
    assert page.status_code == HTTPStatus.OK
    response = client.post(
        url,
        {"text": text, "published_at": _rendered_publish_value(page.content.decode())},
    )
    assert response.status_code == HTTPStatus.FOUND


@pytest.mark.django_db
@pytest.mark.usefixtures("recydywa_achievement")
def test_update_view_increments_edit_count(client: Client) -> None:
    author = make_user("author")
    future = timezone.now() + timedelta(days=1)
    suchar = Suchar.objects.create(text="joke", author=author, published_at=future)
    client.force_login(author)
    url = reverse("suchary:update", kwargs={"pk": suchar.pk})

    _edit_once(client, url, "edited once")

    suchar.refresh_from_db()
    assert suchar.edit_count == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("recydywa_achievement")
def test_five_edits_through_the_view_award_recydywa(client: Client) -> None:
    author = make_user("author")
    future = timezone.now() + timedelta(days=1)
    suchar = Suchar.objects.create(text="joke", author=author, published_at=future)
    client.force_login(author)
    url = reverse("suchary:update", kwargs={"pk": suchar.pk})

    for i in range(RECYDYWA_THRESHOLD):
        _edit_once(client, url, f"edit {i}")

    suchar.refresh_from_db()
    assert suchar.edit_count == RECYDYWA_THRESHOLD
    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug=RECYDYWA_SLUG,
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("recydywa_achievement")
def test_too_late_page_does_not_increment_edit_count(client: Client) -> None:
    author = make_user("author")
    past = timezone.now() - timedelta(seconds=1)
    suchar = Suchar.objects.create(text="joke", author=author, published_at=past)
    client.force_login(author)
    url = reverse("suchary:update", kwargs={"pk": suchar.pk})

    response = client.post(url, {"text": "too late"})

    assert response.status_code == HTTPStatus.FORBIDDEN
    suchar.refresh_from_db()
    assert suchar.edit_count == 0
