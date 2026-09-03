"""Tests for the "Mistrz Suszu" / Dry Master achievement (#294).

Two layers, matching the design:

* :class:`DryMasterRule` is a threshold-independent metric — it only counts
  the user's suchary that already carry the ``is_overdried`` latch.
* ``_maybe_mark_overdried`` in ``achievements.signals`` does the
  time-sensitive work: on every vote event it latches ``Suchar.is_overdried``
  when, within an hour of publication, a suchar has >=10 dry votes and no
  funny votes. It never clears the flag (engine awards, never revokes).
"""

import datetime

import pytest
from django.utils import timezone

from suchar_overflow.achievements.engine import AchievementEngine
from suchar_overflow.achievements.engine import DryMasterRule
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote
from suchar_overflow.suchary.signals import vote_changed

DRY_SLUG = "dry-master"
DRY_THRESHOLD = 10


@pytest.fixture
def dry_master_achievement() -> Achievement:
    achievement, _ = Achievement.objects.get_or_create(
        slug=DRY_SLUG,
        defaults={
            "name": "Mistrz Suszu",
            "description": "desc",
            "icon_content": "<svg/>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.VOTE_RECEIVED,
            "metric": Achievement.Metric.DRY_MASTER,
            "threshold": 1,
            "is_secret": True,
        },
    )
    return achievement


def _cast_dry_votes(suchar: Suchar, count: int, *, prefix: str = "d") -> None:
    for i in range(count):
        Vote.objects.create(
            suchar=suchar,
            user=make_user(f"{prefix}{i}"),
            is_dry=True,
        )


def _backdate(suchar: Suchar, *, minutes_ago: int) -> None:
    """Move the suchar's publication window into the past and refresh it."""
    moment = timezone.now() - datetime.timedelta(minutes=minutes_ago)
    Suchar.objects.filter(pk=suchar.pk).update(
        created_at=moment,
        published_at=moment,
    )
    suchar.refresh_from_db()


# ---------------------------------------------------------------------------
# DryMasterRule — threshold-independent metric
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rule_returns_none_without_overdried_suchar() -> None:
    user = make_user("author")
    Suchar.objects.create(text="joke", author=user)
    assert DryMasterRule.compute_value(user) is None


@pytest.mark.django_db
def test_rule_counts_overdried_suchary() -> None:
    user = make_user("author")
    Suchar.objects.create(text="a", author=user, is_overdried=True)
    Suchar.objects.create(text="b", author=user, is_overdried=True)
    Suchar.objects.create(text="c", author=user)
    assert DryMasterRule.compute_value(user) == 2  # noqa: PLR2004


@pytest.mark.django_db
def test_rule_evaluate_true_at_threshold_one() -> None:
    user = make_user("author")
    Suchar.objects.create(text="a", author=user, is_overdried=True)
    assert DryMasterRule.evaluate(user, threshold=1)


# ---------------------------------------------------------------------------
# _maybe_mark_overdried — the 1h / 10-dry / 0-funny latch
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("dry_master_achievement")
def test_ten_dry_votes_in_window_latches_and_awards() -> None:
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)

    _cast_dry_votes(suchar, DRY_THRESHOLD)

    suchar.refresh_from_db()
    assert suchar.is_overdried is True
    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug=DRY_SLUG,
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("dry_master_achievement")
def test_one_funny_vote_blocks_the_latch() -> None:
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)

    Vote.objects.create(suchar=suchar, user=make_user("f"), is_funny=True)
    _cast_dry_votes(suchar, DRY_THRESHOLD)

    suchar.refresh_from_db()
    assert suchar.is_overdried is False
    assert not UserAchievement.objects.filter(
        user=author,
        achievement__slug=DRY_SLUG,
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("dry_master_achievement")
def test_nine_dry_votes_do_not_latch() -> None:
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)

    _cast_dry_votes(suchar, DRY_THRESHOLD - 1)

    suchar.refresh_from_db()
    assert suchar.is_overdried is False


@pytest.mark.django_db
@pytest.mark.usefixtures("dry_master_achievement")
def test_votes_before_publication_do_not_latch() -> None:
    """A scheduled suchar must not latch before it goes live — the vote
    endpoint does not block votes on an unpublished suchar, so the window
    is bounded below by ``published_at`` (#294 review 2.1)."""
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)
    future = timezone.now() + datetime.timedelta(hours=2)
    Suchar.objects.filter(pk=suchar.pk).update(published_at=future)
    suchar.refresh_from_db()

    _cast_dry_votes(suchar, DRY_THRESHOLD)

    suchar.refresh_from_db()
    assert suchar.is_overdried is False
    assert not UserAchievement.objects.filter(
        user=author,
        achievement__slug=DRY_SLUG,
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("dry_master_achievement")
def test_votes_after_the_window_do_not_latch() -> None:
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)
    _backdate(suchar, minutes_ago=61)

    _cast_dry_votes(suchar, DRY_THRESHOLD)

    suchar.refresh_from_db()
    assert suchar.is_overdried is False
    assert not UserAchievement.objects.filter(
        user=author,
        achievement__slug=DRY_SLUG,
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("dry_master_achievement")
def test_removing_the_only_funny_vote_latches_via_vote_changed() -> None:
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)
    funny_voter = make_user("f")
    funny_vote = Vote.objects.create(
        suchar=suchar,
        user=funny_voter,
        is_funny=True,
    )
    _cast_dry_votes(suchar, DRY_THRESHOLD)
    suchar.refresh_from_db()
    assert suchar.is_overdried is False

    # The toggle/removal path in the vote endpoint deletes the row and then
    # emits vote_changed with the suchar (no post_save(created=True) fires).
    funny_vote.delete()
    vote_changed.send(
        sender=Vote,
        voter=funny_voter,
        author=author,
        suchar=suchar,
    )

    suchar.refresh_from_db()
    assert suchar.is_overdried is True
    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug=DRY_SLUG,
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("dry_master_achievement")
def test_latch_and_award_survive_dry_votes_being_removed() -> None:
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)
    _cast_dry_votes(suchar, DRY_THRESHOLD)
    suchar.refresh_from_db()
    assert suchar.is_overdried is True

    Vote.objects.filter(suchar=suchar).delete()
    for voter in author.__class__.objects.exclude(pk=author.pk):
        vote_changed.send(
            sender=Vote,
            voter=voter,
            author=author,
            suchar=suchar,
        )
    AchievementEngine.check_achievements(
        author,
        Achievement.EventType.VOTE_RECEIVED,
    )

    suchar.refresh_from_db()
    assert suchar.is_overdried is True
    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug=DRY_SLUG,
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("dry_master_achievement")
def test_latch_is_not_awarded_twice() -> None:
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)
    _cast_dry_votes(suchar, DRY_THRESHOLD)

    extra_dry_voter = make_user("extra")
    Vote.objects.create(suchar=suchar, user=extra_dry_voter, is_dry=True)

    assert (
        UserAchievement.objects.filter(
            user=author,
            achievement__slug=DRY_SLUG,
        ).count()
        == 1
    )
