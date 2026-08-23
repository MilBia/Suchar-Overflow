import datetime
import logging
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import SchedulerRun
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.achievements.tasks import award_best_suchar
from suchar_overflow.achievements.tasks import award_winners
from suchar_overflow.achievements.tasks import compute_period_range
from suchar_overflow.achievements.tasks import due_monthly_run_at
from suchar_overflow.achievements.tasks import due_yearly_run_at
from suchar_overflow.achievements.tasks import find_best_suchary
from suchar_overflow.achievements.tests.conftest import freeze_to_first_of_current_month
from suchar_overflow.achievements.tests.conftest import last_month_mid
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()


# ---------------------------------------------------------------------------
# compute_period_range (pure function, shared by the command and the task)
# ---------------------------------------------------------------------------


def test_compute_period_range_month() -> None:
    start_dt, end_dt, suffix = compute_period_range(
        "month",
        datetime.date(2024, 2, 15),
    )
    assert start_dt == datetime.datetime(2024, 2, 1, 0, 0, tzinfo=start_dt.tzinfo)
    assert end_dt == datetime.datetime(2024, 3, 1, 0, 0, tzinfo=end_dt.tzinfo)
    assert suffix == "month"


def test_compute_period_range_month_december_rolls_into_next_year() -> None:
    start_dt, end_dt, _suffix = compute_period_range(
        "month",
        datetime.date(2024, 12, 10),
    )
    assert start_dt == datetime.datetime(2024, 12, 1, 0, 0, tzinfo=start_dt.tzinfo)
    assert end_dt == datetime.datetime(2025, 1, 1, 0, 0, tzinfo=end_dt.tzinfo)


def test_compute_period_range_year() -> None:
    start_dt, end_dt, suffix = compute_period_range(
        "year",
        datetime.date(2024, 6, 1),
    )
    assert start_dt == datetime.datetime(2024, 1, 1, 0, 0, tzinfo=start_dt.tzinfo)
    assert end_dt == datetime.datetime(2025, 1, 1, 0, 0, tzinfo=end_dt.tzinfo)
    assert suffix == "year"


def test_compute_period_range_unknown_period_raises() -> None:
    with pytest.raises(ValueError, match="Unknown period"):
        compute_period_range("week", datetime.date(2024, 6, 1))


# ---------------------------------------------------------------------------
# find_best_suchary — returns ALL Suchary tied for the top vote count (#171)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_find_best_suchary_returns_single_winner_when_no_tie() -> None:
    mid = last_month_mid()
    author = User.objects.create_user(
        username="solo",
        email="solo@example.com",
        password="pw",  # noqa: S106
    )
    other = User.objects.create_user(
        username="solo-other",
        email="solo-other@example.com",
        password="pw",  # noqa: S106
    )
    s_win = Suchar.objects.create(text="Winner", author=author)
    s_win.created_at = mid
    s_win.save()
    s_lose = Suchar.objects.create(text="Loser", author=other)
    s_lose.created_at = mid
    s_lose.save()
    Vote.objects.create(suchar=s_win, user=other, is_funny=True)

    start_dt, end_dt, _suffix = compute_period_range("month", mid.date())
    winners = find_best_suchary(start_dt, end_dt)

    assert [s.pk for s in winners] == [s_win.pk]


@pytest.mark.django_db
def test_find_best_suchary_returns_all_suchary_tied_for_top_vote_count() -> None:
    mid = last_month_mid()
    author_a = User.objects.create_user(
        username="tie-a",
        email="tie-a@example.com",
        password="pw",  # noqa: S106
    )
    author_b = User.objects.create_user(
        username="tie-b",
        email="tie-b@example.com",
        password="pw",  # noqa: S106
    )
    author_c = User.objects.create_user(
        username="tie-c",
        email="tie-c@example.com",
        password="pw",  # noqa: S106
    )
    s_a = Suchar.objects.create(text="A", author=author_a)
    s_a.created_at = mid
    s_a.save()
    s_b = Suchar.objects.create(text="B", author=author_b)
    s_b.created_at = mid
    s_b.save()
    s_c = Suchar.objects.create(text="C, fewer votes", author=author_c)
    s_c.created_at = mid
    s_c.save()

    # s_a and s_b each get 2 votes, s_c gets 1 — s_a and s_b tie for the top spot.
    Vote.objects.create(suchar=s_a, user=author_b, is_funny=True)
    Vote.objects.create(suchar=s_a, user=author_c, is_funny=True)
    Vote.objects.create(suchar=s_b, user=author_a, is_funny=True)
    Vote.objects.create(suchar=s_b, user=author_c, is_funny=True)
    Vote.objects.create(suchar=s_c, user=author_a, is_funny=True)

    start_dt, end_dt, _suffix = compute_period_range("month", mid.date())
    winners = find_best_suchary(start_dt, end_dt)

    assert {s.pk for s in winners} == {s_a.pk, s_b.pk}


@pytest.mark.django_db
def test_find_best_suchary_returns_empty_list_when_no_suchars() -> None:
    mid = last_month_mid()
    start_dt, end_dt, _suffix = compute_period_range("month", mid.date())

    assert find_best_suchary(start_dt, end_dt) == []


@pytest.mark.django_db
def test_find_best_suchary_returns_empty_list_when_all_suchary_have_zero_votes() -> (
    None
):
    """A period where Suchary were posted but none received any votes has no
    winner — the max vote count of 0 doesn't count as a "best" tie (#171)."""
    mid = last_month_mid()
    author_a = User.objects.create_user(
        username="zero-a",
        email="zero-a@example.com",
        password="pw",  # noqa: S106
    )
    author_b = User.objects.create_user(
        username="zero-b",
        email="zero-b@example.com",
        password="pw",  # noqa: S106
    )
    for author in (author_a, author_b):
        s = Suchar.objects.create(text=f"No votes for {author.username}", author=author)
        s.created_at = mid
        s.save()

    start_dt, end_dt, _suffix = compute_period_range("month", mid.date())

    assert find_best_suchary(start_dt, end_dt) == []


# ---------------------------------------------------------------------------
# award_winners — awards every distinct tied author, plus the hidden
# "-tie" achievement when more than one distinct author tied (#171)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_winners_single_winner_gets_no_tie_achievement() -> None:
    winner = User.objects.create_user(
        username="award-solo",
        email="award-solo@example.com",
        password="pw",  # noqa: S106
    )
    s = Suchar.objects.create(text="Solo joke", author=winner)

    award_winners([s], "month")

    assert UserAchievement.objects.filter(
        user=winner,
        achievement__slug="best-suchar-month",
    ).exists()
    assert not UserAchievement.objects.filter(
        user=winner,
        achievement__slug="best-suchar-month-tie",
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_winners_different_authors_tied_both_get_main_and_tie_achievement() -> (
    None
):
    author_a = User.objects.create_user(
        username="award-tie-a",
        email="award-tie-a@example.com",
        password="pw",  # noqa: S106
    )
    author_b = User.objects.create_user(
        username="award-tie-b",
        email="award-tie-b@example.com",
        password="pw",  # noqa: S106
    )
    s_a = Suchar.objects.create(text="Tie A", author=author_a)
    s_b = Suchar.objects.create(text="Tie B", author=author_b)

    award_winners([s_a, s_b], "month")

    for author in (author_a, author_b):
        assert UserAchievement.objects.filter(
            user=author,
            achievement__slug="best-suchar-month",
        ).exists()
        assert UserAchievement.objects.filter(
            user=author,
            achievement__slug="best-suchar-month-tie",
        ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_winners_results_are_ordered_by_username() -> None:
    """award_winners dedupes authors into a set, whose iteration order is
    unspecified — results must be sorted by username so CLI/log output is
    deterministic across runs (PR #172 review nit)."""
    author_z = User.objects.create_user(
        username="zzz-order",
        email="zzz-order@example.com",
        password="pw",  # noqa: S106
    )
    author_a = User.objects.create_user(
        username="aaa-order",
        email="aaa-order@example.com",
        password="pw",  # noqa: S106
    )
    s_z = Suchar.objects.create(text="Z", author=author_z)
    s_a = Suchar.objects.create(text="A", author=author_a)

    results = award_winners([s_z, s_a], "month")

    # Two award_winners calls happen here (main + tie achievement), each
    # producing its own sorted run — check ordering within each, not across
    # the concatenated list.
    main_usernames = [
        user.username for slug, user, _created in results if slug == "best-suchar-month"
    ]
    tie_usernames = [
        user.username
        for slug, user, _created in results
        if slug == "best-suchar-month-tie"
    ]
    assert main_usernames == sorted(main_usernames)
    assert tie_usernames == sorted(tie_usernames)


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_winners_same_author_tied_with_self_gets_no_tie_achievement() -> None:
    """Two Suchary by the same author tied for the top spot, no other author
    involved — this is a plain win, not a tie between different people."""
    author = User.objects.create_user(
        username="award-self-tie",
        email="award-self-tie@example.com",
        password="pw",  # noqa: S106
    )
    s1 = Suchar.objects.create(text="Self A", author=author)
    s2 = Suchar.objects.create(text="Self B", author=author)

    award_winners([s1, s2], "month")

    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug="best-suchar-month",
    ).exists()
    assert not UserAchievement.objects.filter(
        user=author,
        achievement__slug="best-suchar-month-tie",
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_winners_empty_list_does_nothing() -> None:
    award_winners([], "month")

    assert UserAchievement.objects.count() == 0


# ---------------------------------------------------------------------------
# award_best_suchar task
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_best_suchar_month_awards_winner() -> None:
    frozen_now = freeze_to_first_of_current_month()
    winner = User.objects.create_user(
        username="winner",
        email="w@example.com",
        password="pw",  # noqa: S106
    )
    loser = User.objects.create_user(
        username="loser",
        email="l@example.com",
        password="pw",  # noqa: S106
    )

    mid = last_month_mid()
    s_win = Suchar.objects.create(text="Funny", author=winner)
    s_win.created_at = mid
    s_win.save()
    s_lose = Suchar.objects.create(text="Bad", author=loser)
    s_lose.created_at = mid
    s_lose.save()

    for i in range(3):
        u = User.objects.create_user(
            username=f"v{i}",
            email=f"v{i}@example.com",
            password="pw",  # noqa: S106
        )
        Vote.objects.create(suchar=s_win, user=u, is_funny=True)
    Vote.objects.create(suchar=s_lose, user=winner, is_funny=True)

    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month")

    assert UserAchievement.objects.filter(
        user=winner,
        achievement__slug="best-suchar-month",
    ).exists()
    assert not UserAchievement.objects.filter(
        user=loser,
        achievement__slug="best-suchar-month",
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_best_suchar_month_tie_awards_all_tied_authors() -> None:
    """When different authors tie for the top vote count in the period,
    every one of them gets the main achievement plus the hidden tie
    achievement (#171)."""
    frozen_now = freeze_to_first_of_current_month()
    author_a = User.objects.create_user(
        username="task-tie-a",
        email="task-tie-a@example.com",
        password="pw",  # noqa: S106
    )
    author_b = User.objects.create_user(
        username="task-tie-b",
        email="task-tie-b@example.com",
        password="pw",  # noqa: S106
    )

    mid = last_month_mid()
    s_a = Suchar.objects.create(text="Tie A", author=author_a)
    s_a.created_at = mid
    s_a.save()
    s_b = Suchar.objects.create(text="Tie B", author=author_b)
    s_b.created_at = mid
    s_b.save()

    Vote.objects.create(suchar=s_a, user=author_b, is_funny=True)
    Vote.objects.create(suchar=s_b, user=author_a, is_funny=True)

    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month")

    for author in (author_a, author_b):
        assert UserAchievement.objects.filter(
            user=author,
            achievement__slug="best-suchar-month",
        ).exists()
        assert UserAchievement.objects.filter(
            user=author,
            achievement__slug="best-suchar-month-tie",
        ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_best_suchar_uses_explicit_reference_date_when_given() -> None:
    """An explicit reference_date overrides the yesterday default — used by
    the startup catch-up path (#169) to award a period other than the one
    "yesterday" falls in at restart time."""
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    winner = User.objects.create_user(
        username="explicit-ref",
        email="explicit-ref@example.com",
        password="pw",  # noqa: S106
    )
    s = Suchar.objects.create(text="May joke", author=winner)
    s.created_at = datetime.datetime(2024, 5, 15, 12, 0, tzinfo=datetime.UTC)
    s.save()
    voter = User.objects.create_user(
        username="voter-explicit-ref",
        email="voter-explicit-ref@example.com",
        password="pw",  # noqa: S106
    )
    Vote.objects.create(suchar=s, user=voter, is_funny=True)

    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month", reference_date=datetime.date(2024, 5, 31))

    assert UserAchievement.objects.filter(
        user=winner,
        achievement__slug="best-suchar-month",
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_best_suchar_month_no_suchars_does_not_crash() -> None:
    frozen_now = freeze_to_first_of_current_month()
    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month")  # should not raise
    assert UserAchievement.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_best_suchar_month_missing_achievement_does_not_crash() -> None:
    """If the achievement slug doesn't exist in the DB the task exits gracefully."""
    frozen_now = freeze_to_first_of_current_month()
    winner = User.objects.create_user(
        username="w2",
        email="w2@example.com",
        password="pw",  # noqa: S106
    )
    mid = last_month_mid()
    s = Suchar.objects.create(text="Joke", author=winner)
    s.created_at = mid
    s.save()
    voter = User.objects.create_user(
        username="vw2",
        email="vw2@example.com",
        password="pw",  # noqa: S106
    )
    Vote.objects.create(suchar=s, user=voter, is_funny=True)

    with (
        patch(
            "suchar_overflow.achievements.tasks.timezone.now",
            return_value=frozen_now,
        ),
        patch(
            "suchar_overflow.achievements.tasks.Achievement.objects.get",
            side_effect=Achievement.DoesNotExist,
        ),
    ):
        award_best_suchar("month")  # should not raise

    assert not UserAchievement.objects.filter(
        achievement__slug="best-suchar-month",
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_best_suchar_is_idempotent() -> None:
    """Calling the task twice doesn't create duplicate UserAchievements."""
    frozen_now = freeze_to_first_of_current_month()
    winner = User.objects.create_user(
        username="idem",
        email="idem@example.com",
        password="pw",  # noqa: S106
    )
    mid = last_month_mid()
    s = Suchar.objects.create(text="Idempotent joke", author=winner)
    s.created_at = mid
    s.save()
    voter = User.objects.create_user(
        username="votidem",
        email="vi@example.com",
        password="pw",  # noqa: S106
    )
    Vote.objects.create(suchar=s, user=voter, is_funny=True)

    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month")
        award_best_suchar("month")

    assert (
        UserAchievement.objects.filter(
            user=winner,
            achievement__slug="best-suchar-month",
        ).count()
        == 1
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_best_suchar_raises_on_unknown_period() -> None:
    frozen_now = freeze_to_first_of_current_month()
    with (
        patch(
            "suchar_overflow.achievements.tasks.timezone.now",
            return_value=frozen_now,
        ),
        pytest.raises(ValueError, match="Unknown period"),
    ):
        award_best_suchar("week")


# ---------------------------------------------------------------------------
# award_best_suchar records a SchedulerRun (replaces django-apscheduler's
# DjangoJobStore visibility now that the scheduler uses an in-memory jobstore)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_best_suchar_records_scheduler_run() -> None:
    frozen_now = freeze_to_first_of_current_month()
    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month")

    run = SchedulerRun.objects.get(job_id="award-best-suchar-month")
    assert run.ran_at == frozen_now


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_best_suchar_updates_existing_scheduler_run() -> None:
    frozen_now = freeze_to_first_of_current_month()
    with patch(
        "suchar_overflow.achievements.tasks.timezone.now",
        return_value=frozen_now,
    ):
        award_best_suchar("month")
        award_best_suchar("month")

    assert SchedulerRun.objects.filter(job_id="award-best-suchar-month").count() == 1


# ---------------------------------------------------------------------------
# award_best_suchar closes stale ORM connections (it runs in a long-lived
# daemon thread, not a request cycle, so Django never closes them for us)
# and logs when the expected Achievement is missing from the DB.
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_award_best_suchar_closes_old_connections() -> None:
    frozen_now = freeze_to_first_of_current_month()
    with (
        patch(
            "suchar_overflow.achievements.tasks.timezone.now",
            return_value=frozen_now,
        ),
        patch(
            "suchar_overflow.achievements.tasks.close_old_connections",
        ) as mock_close_old_connections,
    ):
        award_best_suchar("month")

    assert mock_close_old_connections.called


@pytest.mark.django_db
def test_award_best_suchar_skips_close_old_connections_inside_atomic_block() -> None:
    """Inside an atomic block (e.g. this test's own transaction), closing the
    connection would kill the transaction the caller depends on — see the
    ``connection.in_atomic_block`` guard in ``award_best_suchar``."""
    frozen_now = freeze_to_first_of_current_month()
    with (
        patch(
            "suchar_overflow.achievements.tasks.timezone.now",
            return_value=frozen_now,
        ),
        patch(
            "suchar_overflow.achievements.tasks.close_old_connections",
        ) as mock_close_old_connections,
    ):
        award_best_suchar("month")

    mock_close_old_connections.assert_not_called()


# ---------------------------------------------------------------------------
# due_monthly_run_at — catch-up detection for the in-memory jobstore (#169)
# ---------------------------------------------------------------------------


def test_due_monthly_run_at_returns_due_date_when_never_run() -> None:
    now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    assert due_monthly_run_at(now, None) == datetime.datetime(
        2024,
        6,
        1,
        0,
        5,
        tzinfo=datetime.UTC,
    )


def test_due_monthly_run_at_returns_due_date_when_last_run_before_it() -> None:
    now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    last_ran_at = datetime.datetime(2024, 4, 1, 0, 5, tzinfo=datetime.UTC)
    assert due_monthly_run_at(now, last_ran_at) == datetime.datetime(
        2024,
        6,
        1,
        0,
        5,
        tzinfo=datetime.UTC,
    )


def test_due_monthly_run_at_none_when_last_run_on_due_date() -> None:
    now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    last_ran_at = datetime.datetime(2024, 6, 1, 0, 5, tzinfo=datetime.UTC)
    assert due_monthly_run_at(now, last_ran_at) is None


def test_due_monthly_run_at_none_when_last_run_after_due_date() -> None:
    now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    last_ran_at = datetime.datetime(2024, 6, 1, 0, 6, tzinfo=datetime.UTC)
    assert due_monthly_run_at(now, last_ran_at) is None


def test_due_monthly_run_at_before_first_of_month_fire_uses_previous_month() -> None:
    """On the 1st, before 00:05 UTC, this month's cron hasn't fired yet — the
    due date falls back to the previous month's fire time."""
    now = datetime.datetime(2024, 6, 1, 0, 0, tzinfo=datetime.UTC)
    last_ran_at = datetime.datetime(2024, 5, 1, 0, 5, tzinfo=datetime.UTC)
    assert due_monthly_run_at(now, last_ran_at) is None


def test_due_monthly_run_at_before_first_of_month_fire_still_detects_gap() -> None:
    now = datetime.datetime(2024, 6, 1, 0, 0, tzinfo=datetime.UTC)
    last_ran_at = datetime.datetime(2024, 4, 1, 0, 5, tzinfo=datetime.UTC)
    assert due_monthly_run_at(now, last_ran_at) == datetime.datetime(
        2024,
        5,
        1,
        0,
        5,
        tzinfo=datetime.UTC,
    )


def test_due_monthly_run_at_january_rolls_back_to_december() -> None:
    now = datetime.datetime(2024, 1, 1, 0, 0, tzinfo=datetime.UTC)
    last_ran_at = datetime.datetime(2023, 12, 1, 0, 5, tzinfo=datetime.UTC)
    assert due_monthly_run_at(now, last_ran_at) is None


# ---------------------------------------------------------------------------
# due_yearly_run_at — catch-up detection for the in-memory jobstore (#168)
# ---------------------------------------------------------------------------


def test_due_yearly_run_at_returns_due_date_when_never_run() -> None:
    now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    assert due_yearly_run_at(now, None) == datetime.datetime(
        2024,
        1,
        1,
        0,
        5,
        tzinfo=datetime.UTC,
    )


def test_due_yearly_run_at_returns_due_date_when_last_run_before_it() -> None:
    now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    last_ran_at = datetime.datetime(2022, 1, 1, 0, 5, tzinfo=datetime.UTC)
    assert due_yearly_run_at(now, last_ran_at) == datetime.datetime(
        2024,
        1,
        1,
        0,
        5,
        tzinfo=datetime.UTC,
    )


def test_due_yearly_run_at_none_when_last_run_on_due_date() -> None:
    now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    last_ran_at = datetime.datetime(2024, 1, 1, 0, 5, tzinfo=datetime.UTC)
    assert due_yearly_run_at(now, last_ran_at) is None


def test_due_yearly_run_at_none_when_last_run_after_due_date() -> None:
    now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    last_ran_at = datetime.datetime(2024, 1, 1, 0, 6, tzinfo=datetime.UTC)
    assert due_yearly_run_at(now, last_ran_at) is None


def test_due_yearly_run_at_before_first_of_year_fire_uses_previous_year() -> None:
    """On Jan 1, before 00:05 UTC, this year's cron hasn't fired yet — the
    due date falls back to the previous year's fire time."""
    now = datetime.datetime(2024, 1, 1, 0, 0, tzinfo=datetime.UTC)
    last_ran_at = datetime.datetime(2023, 1, 1, 0, 5, tzinfo=datetime.UTC)
    assert due_yearly_run_at(now, last_ran_at) is None


def test_due_yearly_run_at_before_first_of_year_fire_still_detects_gap() -> None:
    now = datetime.datetime(2024, 1, 1, 0, 0, tzinfo=datetime.UTC)
    last_ran_at = datetime.datetime(2022, 1, 1, 0, 5, tzinfo=datetime.UTC)
    assert due_yearly_run_at(now, last_ran_at) == datetime.datetime(
        2023,
        1,
        1,
        0,
        5,
        tzinfo=datetime.UTC,
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def test_award_best_suchar_logs_warning_when_achievement_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    frozen_now = freeze_to_first_of_current_month()
    winner = User.objects.create_user(
        username="w3",
        email="w3@example.com",
        password="pw",  # noqa: S106
    )
    mid = last_month_mid()
    s = Suchar.objects.create(text="Joke", author=winner)
    s.created_at = mid
    s.save()
    voter = User.objects.create_user(
        username="vw3",
        email="vw3@example.com",
        password="pw",  # noqa: S106
    )
    Vote.objects.create(suchar=s, user=voter, is_funny=True)

    with (
        patch(
            "suchar_overflow.achievements.tasks.timezone.now",
            return_value=frozen_now,
        ),
        patch(
            "suchar_overflow.achievements.tasks.Achievement.objects.get",
            side_effect=Achievement.DoesNotExist,
        ),
        caplog.at_level(logging.WARNING, logger="suchar_overflow.achievements.tasks"),
    ):
        award_best_suchar("month")  # should not raise

    assert "best-suchar-month" in caplog.text
