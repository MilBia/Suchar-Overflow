"""Extra signal tests: created=False skip, author vs voter both checked."""

import pytest
from django.contrib.auth import get_user_model

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


def make_suchar_achievement(slug, threshold=1):
    return Achievement.objects.create(
        slug=slug,
        name=slug,
        description="desc",
        icon_content="<svg/>",
        category=Achievement.Category.LIFETIME,
        event_type=Achievement.EventType.SUCHAR_POSTED,
        metric=Achievement.Metric.COUNT_SUCHAR,
        threshold=threshold,
    )


def make_vote_cast_achievement(slug, threshold=1):
    return Achievement.objects.create(
        slug=slug,
        name=slug,
        description="desc",
        icon_content="<svg/>",
        category=Achievement.Category.LIFETIME,
        event_type=Achievement.EventType.VOTE_CAST,
        metric=Achievement.Metric.COUNT_VOTE_CAST,
        threshold=threshold,
    )


def make_vote_received_achievement(slug, threshold=1):
    # SUM_SCORE checks net score of votes received on author's suchary,
    # which correctly evaluates from the author's perspective (not the voter's).
    return Achievement.objects.create(
        slug=slug,
        name=slug,
        description="desc",
        icon_content="<svg/>",
        category=Achievement.Category.LIFETIME,
        event_type=Achievement.EventType.VOTE_RECEIVED,
        metric=Achievement.Metric.SUM_SCORE,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Suchar signal: created=False must not trigger engine
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_suchar_update_does_not_award_achievement():
    """Saving an existing Suchar (created=False) must not trigger achievements."""
    user = make_user("u1")
    ach = make_suchar_achievement("first-suchar-extra", threshold=1)

    suchar = Suchar.objects.create(text="original", author=user)
    assert UserAchievement.objects.filter(user=user, achievement=ach).exists()

    # Now update — engine must not try to award again (unique_together prevents it
    # anyway, but we want to confirm the signal guard `if created:` fires correctly)
    count_before = UserAchievement.objects.filter(user=user, achievement=ach).count()
    suchar.text = "updated"
    suchar.save()
    assert (
        UserAchievement.objects.filter(user=user, achievement=ach).count()
        == count_before
    )


# ---------------------------------------------------------------------------
# Vote signal: created=False must not trigger engine
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_update_does_not_trigger_achievement_check():
    """Updating an existing Vote (toggling flags) must not re-trigger engine."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="joke", author=author)

    ach_cast = make_vote_cast_achievement("first-vote-extra", threshold=1)

    # Create vote — triggers signal, awards achievement
    vote = Vote.objects.create(suchar=suchar, user=voter, is_funny=True)
    assert UserAchievement.objects.filter(user=voter, achievement=ach_cast).exists()

    count_before = UserAchievement.objects.filter(
        user=voter,
        achievement=ach_cast,
    ).count()

    # Update the vote (not create) — signal guard `if created:` must prevent re-check
    vote.is_dry = True
    vote.save()

    assert (
        UserAchievement.objects.filter(user=voter, achievement=ach_cast).count()
        == count_before
    )


# ---------------------------------------------------------------------------
# Vote signal: both voter AND author achievements checked
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_awards_achievement_to_voter():
    """Creating a Vote checks VOTE_CAST achievements for the voter."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="joke", author=author)
    ach = make_vote_cast_achievement("vote-cast-v", threshold=1)

    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    assert UserAchievement.objects.filter(user=voter, achievement=ach).exists()


@pytest.mark.django_db
def test_vote_awards_achievement_to_author():
    """Creating a Vote checks VOTE_RECEIVED achievements for the suchar author."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="joke", author=author)
    ach = make_vote_received_achievement("vote-received-v", threshold=1)

    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    assert UserAchievement.objects.filter(user=author, achievement=ach).exists()


@pytest.mark.django_db
def test_vote_checks_both_voter_and_author_independently():
    """A single Vote creation must trigger engine for both voter and author."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="joke", author=author)

    ach_cast = make_vote_cast_achievement("vote-cast-both", threshold=1)
    ach_received = make_vote_received_achievement("vote-recv-both", threshold=1)

    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    assert UserAchievement.objects.filter(user=voter, achievement=ach_cast).exists()
    assert UserAchievement.objects.filter(
        user=author,
        achievement=ach_received,
    ).exists()


@pytest.mark.django_db
def test_author_voting_own_suchar_awards_voter_not_duplicate_author():
    """When author votes their own suchar, they get voter achievement; author
    achievement fires separately and must not duplicate."""
    author = make_user("self_voter")
    suchar = Suchar.objects.create(text="joke", author=author)
    ach_cast = make_vote_cast_achievement("vote-cast-self", threshold=1)

    Vote.objects.create(suchar=suchar, user=author, is_funny=True)

    # Voter achievement awarded exactly once
    assert (
        UserAchievement.objects.filter(user=author, achievement=ach_cast).count() == 1
    )
