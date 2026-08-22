import logging
from datetime import date
from datetime import datetime
from datetime import timedelta

from django.db import close_old_connections
from django.db import connection
from django.db.models import Count
from django.db.models import Max
from django.utils import timezone

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import SchedulerRun
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar

logger = logging.getLogger(__name__)


def compute_period_range(
    period: str,
    reference_date: date,
) -> tuple[datetime, datetime, str]:
    """Compute the [start, end) datetime range and slug suffix for a period.

    ``period`` is ``"month"`` or ``"year"``; the range covers the calendar
    month/year that ``reference_date`` falls in.
    """
    if period == "month":
        start_date = reference_date.replace(day=1)
        end_date = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        suffix = "month"
    elif period == "year":
        start_date = reference_date.replace(month=1, day=1)
        end_date = start_date.replace(year=start_date.year + 1)
        suffix = "year"
    else:
        msg = f"Unknown period: {period!r}"
        raise ValueError(msg)

    current_tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.combine(start_date, datetime.min.time()),
        current_tz,
    )
    end_dt = timezone.make_aware(
        datetime.combine(end_date, datetime.min.time()),
        current_tz,
    )
    return start_dt, end_dt, suffix


def due_monthly_run_at(now: datetime, last_ran_at: datetime | None) -> datetime | None:
    """Return the monthly cron fire (day=1, 00:05 UTC) due at or before
    ``now`` if it was never recorded by ``award_best_suchar``, else ``None``.

    Used at process startup to detect a run missed while the process was
    down: apscheduler's default in-memory jobstore only knows about future
    fire times, so a restart silently skips any fire that should already
    have happened rather than catching it up on its own (see #169).
    """
    due_at = now.replace(day=1, hour=0, minute=5, second=0, microsecond=0)
    if due_at > now:
        previous_month_end = due_at - timedelta(days=1)
        due_at = previous_month_end.replace(
            day=1,
            hour=0,
            minute=5,
            second=0,
            microsecond=0,
        )
    if last_ran_at is None or last_ran_at < due_at:
        return due_at
    return None


def find_best_suchary(start_dt: datetime, end_dt: datetime) -> list[Suchar]:
    """Return all Suchary tied for the most votes created within [start_dt, end_dt).

    Postgres doesn't guarantee row order among ties on a plain
    ``.order_by("-vote_count")``, so rather than picking an arbitrary single
    "winner" (see #171) this returns every Suchar at the top vote count —
    ``award_winners`` decides what to do with a tie. Empty list if no Suchar
    was posted in the range, or if every Suchar posted has zero votes (a
    0-vote max doesn't count as a "best" — nobody actually won anything).
    """
    candidates = (
        Suchar.objects.filter(
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        )
        .annotate(vote_count=Count("votes"))
        .select_related("author")
    )
    max_votes = candidates.aggregate(max_votes=Max("vote_count"))["max_votes"]
    if not max_votes:
        return []
    return list(candidates.filter(vote_count=max_votes).order_by("id"))


def award_winners(winners: list[Suchar], suffix: str) -> list[tuple[str, object, bool]]:
    """Award the periodic best-suchar achievement (slug ``best-suchar-{suffix}``)
    to every distinct author among ``winners``. When the winners span more
    than one distinct author (a genuine tie), also award the hidden
    ``best-suchar-{suffix}-tie`` achievement to each of them.

    Returns a ``(achievement_slug, user, created)`` tuple per award attempt,
    for callers (e.g. the ``award_periodic`` management command) that want to
    report what happened.
    """
    if not winners:
        return []

    authors = {suchar.author for suchar in winners}
    results = _award_achievement(f"best-suchar-{suffix}", authors)
    if len(authors) > 1:
        results += _award_achievement(f"best-suchar-{suffix}-tie", authors)
    return results


def _award_achievement(slug: str, users: set) -> list[tuple[str, object, bool]]:
    try:
        achievement = Achievement.objects.get(slug=slug)
    except Achievement.DoesNotExist:
        logger.warning(
            "Achievement with slug '%s' not found; skipping award for %s",
            slug,
            [user.pk for user in users],
        )
        return []

    results = []
    for user in users:
        _, created = UserAchievement.objects.get_or_create(
            user=user,
            achievement=achievement,
        )
        results.append((slug, user, created))
    return results


def award_best_suchar(period: str, reference_date: date | None = None) -> None:
    """Award the best-suchar achievement for the given period ('month' or 'year').

    Defaults ``reference_date`` to yesterday so when called on the 1st of a
    new period the previous period is evaluated (same logic as the
    management command). Pass an explicit ``reference_date`` to evaluate a
    different period — e.g. the catch-up path in
    ``AchievementsConfig._catch_up_missed_monthly_run`` uses it to award a
    period that was missed while the process was down, rather than
    whatever period "yesterday" falls in at the time the process restarts.

    Runs in a long-lived daemon thread rather than a request cycle, so Django
    never closes its thread-local DB connection for us — this cron job runs
    once a month in that same thread, so without an explicit close the next
    run would reuse a connection the DB (or a proxy in front of it) has
    likely already dropped for being idle. Skipped inside an atomic block
    (e.g. pytest-django's per-test transaction) since closing there would
    kill the connection the caller's transaction depends on.
    """
    try:
        if reference_date is None:
            reference_date = timezone.now().date() - timedelta(days=1)
        start_dt, end_dt, suffix = compute_period_range(period, reference_date)

        winners = find_best_suchary(start_dt, end_dt)
        award_winners(winners, suffix)

        SchedulerRun.objects.update_or_create(
            job_id=f"award-best-suchar-{suffix}",
            defaults={"ran_at": timezone.now()},
        )
    finally:
        if not connection.in_atomic_block:
            close_old_connections()
