import datetime
import logging
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from suchar_overflow.achievements.management.commands.achievements_catch_up import CATCH_UPS
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import SchedulerRun
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.achievements.tasks import award_best_suchar_month_if_due
from suchar_overflow.achievements.tasks import award_best_suchar_year_if_due
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()


# ---------------------------------------------------------------------------
# award_best_suchar_month_if_due — catch-up on process start (#169)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def testaward_best_suchar_month_if_due_calls_award_when_never_run() -> None:
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        award_best_suchar_month_if_due()

    mock_award.assert_called_once_with(
        "month",
        reference_date=datetime.date(2024, 5, 31),
    )


@pytest.mark.django_db
def testaward_best_suchar_month_if_due_calls_award_when_run_is_stale() -> None:
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    SchedulerRun.objects.create(
        job_id="award-best-suchar-month",
        ran_at=datetime.datetime(2024, 4, 1, 0, 5, tzinfo=datetime.UTC),
    )
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        award_best_suchar_month_if_due()

    mock_award.assert_called_once_with(
        "month",
        reference_date=datetime.date(2024, 5, 31),
    )


@pytest.mark.django_db
def testaward_best_suchar_month_if_due_skips_award_when_run_is_current() -> None:
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    SchedulerRun.objects.create(
        job_id="award-best-suchar-month",
        ran_at=datetime.datetime(2024, 6, 1, 0, 5, tzinfo=datetime.UTC),
    )
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        award_best_suchar_month_if_due()

    mock_award.assert_not_called()


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def testaward_best_suchar_month_if_due_awards_the_missed_period_not_current() -> None:
    """A restart on June 15 with May's fire missed must award May's best
    suchar, not evaluate the (incomplete) current month (see #169)."""
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    may_winner = User.objects.create_user(
        username="may-winner",
        email="may-winner@example.com",
        password="pw",
    )
    june_poster = User.objects.create_user(
        username="june-poster",
        email="june-poster@example.com",
        password="pw",
    )
    voter = User.objects.create_user(
        username="voter169",
        email="voter169@example.com",
        password="pw",
    )

    may_at = datetime.datetime(2024, 5, 15, 12, 0, tzinfo=datetime.UTC)
    may_suchar = Suchar.objects.create(text="May joke", author=may_winner)
    may_suchar.created_at = may_suchar.published_at = may_at
    may_suchar.save()
    Vote.objects.create(suchar=may_suchar, user=voter, is_funny=True)

    june_at = datetime.datetime(2024, 6, 10, 12, 0, tzinfo=datetime.UTC)
    june_suchar = Suchar.objects.create(text="June joke", author=june_poster)
    june_suchar.created_at = june_suchar.published_at = june_at
    june_suchar.save()

    with patch("django.utils.timezone.now", return_value=frozen_now):
        award_best_suchar_month_if_due()

    assert UserAchievement.objects.filter(
        user=may_winner,
        achievement__slug="best-suchar-month",
    ).exists()
    assert not UserAchievement.objects.filter(
        user=june_poster,
        achievement__slug="best-suchar-month",
    ).exists()


# ---------------------------------------------------------------------------
# award_best_suchar_year_if_due — catch-up on process start (#168)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def testaward_best_suchar_year_if_due_calls_award_when_never_run() -> None:
    """Migration 0015 seeds a real "award-best-suchar-year" SchedulerRun row
    at test-db build time so a fresh deploy doesn't retroactively award the
    previous year; delete it here to exercise the true "never run" case."""
    SchedulerRun.objects.filter(job_id="award-best-suchar-year").delete()
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        award_best_suchar_year_if_due()

    mock_award.assert_called_once_with(
        "year",
        reference_date=datetime.date(2023, 12, 31),
    )


@pytest.mark.django_db
def testaward_best_suchar_year_if_due_calls_award_when_run_is_stale() -> None:
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    SchedulerRun.objects.update_or_create(
        job_id="award-best-suchar-year",
        defaults={"ran_at": datetime.datetime(2022, 1, 1, 0, 5, tzinfo=datetime.UTC)},
    )
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        award_best_suchar_year_if_due()

    mock_award.assert_called_once_with(
        "year",
        reference_date=datetime.date(2023, 12, 31),
    )


@pytest.mark.django_db
def testaward_best_suchar_year_if_due_skips_award_when_run_is_current() -> None:
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    SchedulerRun.objects.update_or_create(
        job_id="award-best-suchar-year",
        defaults={"ran_at": datetime.datetime(2024, 1, 1, 0, 5, tzinfo=datetime.UTC)},
    )
    with (
        patch("django.utils.timezone.now", return_value=frozen_now),
        patch("suchar_overflow.achievements.tasks.award_best_suchar") as mock_award,
    ):
        award_best_suchar_year_if_due()

    mock_award.assert_not_called()


@pytest.mark.django_db
@pytest.mark.usefixtures("periodic_achievements")
def testaward_best_suchar_year_if_due_awards_the_missed_period_not_current() -> None:
    """A restart in June 2024 with the 2023 fire missed must award 2023's
    best suchar, not evaluate the (incomplete) current year (see #168)."""
    SchedulerRun.objects.filter(job_id="award-best-suchar-year").delete()
    frozen_now = datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.UTC)
    year_winner = User.objects.create_user(
        username="year-winner",
        email="year-winner@example.com",
        password="pw",
    )
    current_year_poster = User.objects.create_user(
        username="current-year-poster",
        email="current-year-poster@example.com",
        password="pw",
    )
    voter = User.objects.create_user(
        username="voter168",
        email="voter168@example.com",
        password="pw",
    )

    year_at = datetime.datetime(2023, 5, 15, 12, 0, tzinfo=datetime.UTC)
    year_suchar = Suchar.objects.create(text="2023 joke", author=year_winner)
    year_suchar.created_at = year_suchar.published_at = year_at
    year_suchar.save()
    Vote.objects.create(suchar=year_suchar, user=voter, is_funny=True)

    current_year_at = datetime.datetime(2024, 6, 10, 12, 0, tzinfo=datetime.UTC)
    current_year_suchar = Suchar.objects.create(
        text="2024 joke",
        author=current_year_poster,
    )
    current_year_suchar.created_at = current_year_suchar.published_at = current_year_at
    current_year_suchar.save()

    with patch("django.utils.timezone.now", return_value=frozen_now):
        award_best_suchar_year_if_due()

    assert UserAchievement.objects.filter(
        user=year_winner,
        achievement__slug="best-suchar-year",
    ).exists()
    assert not UserAchievement.objects.filter(
        user=current_year_poster,
        achievement__slug="best-suchar-year",
    ).exists()


# ---------------------------------------------------------------------------
# achievements_catch_up — the command the `cron` service runs before `rqcron` (#462).
# Unlike the monthly/yearly fires there is no sparse fire to reconstruct for the
# publication sweep: the task itself processes everything since its own
# SchedulerRun marker.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_catch_up_command_awards_a_suchar_published_while_down() -> None:
    """A suchar whose published_at passed while the cron service was down is picked
    up on the next start — its author gets the COUNT_SUCHAR tier without having
    to post again.
    """
    now = datetime.datetime.now(tz=datetime.UTC)
    author = User.objects.create_user(
        username="downtime-author",
        email="downtime-author@example.com",
        password="pw",
    )
    ach = Achievement.objects.create(
        slug="catchup-count-1",
        name="catchup-count-1",
        description="desc",
        icon_content="<svg/>",
        category=Achievement.Category.LIFETIME,
        event_type=Achievement.EventType.SUCHAR_POSTED,
        metric=Achievement.Metric.COUNT_SUCHAR,
        threshold=1,
    )
    # Last run was 3h ago; the service was down since.
    SchedulerRun.objects.create(
        job_id="award-publication-achievements",
        ran_at=now - datetime.timedelta(hours=3),
    )
    suchar = Suchar.objects.create(
        text="scheduled",
        author=author,
        published_at=now + datetime.timedelta(days=1),
    )
    # It actually went live 1h ago, mid-downtime.
    Suchar.objects.filter(pk=suchar.pk).update(
        published_at=now - datetime.timedelta(hours=1),
    )

    call_command("achievements_catch_up")

    assert UserAchievement.objects.filter(user=author, achievement=ach).exists()


_CMD = "suchar_overflow.achievements.management.commands.achievements_catch_up"


@pytest.mark.parametrize("failing", ["monthly", "yearly", "publication-achievement"])
def test_catch_up_command_runs_the_others_when_one_raises(
    failing: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A transient failure in one catch-up (e.g. a DB hiccup at startup) must not
    skip the others — nor the scheduler the cron script starts afterwards (PR #170 review)."""
    mocks = {label: MagicMock(name=label) for label, _ in CATCH_UPS}
    mocks[failing].side_effect = RuntimeError("boom")
    patched = tuple((label, mocks[label]) for label, _ in CATCH_UPS)
    with (
        patch(f"{_CMD}.CATCH_UPS", patched),
        caplog.at_level(logging.ERROR, logger=_CMD),
    ):
        call_command("achievements_catch_up")

    for mock in mocks.values():
        mock.assert_called_once_with()
    assert "boom" in caplog.text
    assert failing in caplog.text
