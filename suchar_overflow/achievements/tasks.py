import logging
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import close_old_connections
from django.db import connection
from django.db.models import Count
from django.db.models import Max
from django.utils import timezone

from suchar_overflow.achievements.engine import AchievementEngine
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import SchedulerRun
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar

if TYPE_CHECKING:
    from suchar_overflow.users.models import User

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


def due_yearly_run_at(now: datetime, last_ran_at: datetime | None) -> datetime | None:
    """Return the yearly cron fire (Jan 1, 00:05 UTC) due at or before
    ``now`` if it was never recorded by ``award_best_suchar``, else ``None``.

    Used at process startup to detect a run missed while the process was
    down — see ``due_monthly_run_at`` for why the in-memory jobstore needs
    this at all (#169; extended to the yearly job in #168).
    """
    due_at = now.replace(month=1, day=1, hour=0, minute=5, second=0, microsecond=0)
    if due_at > now:
        due_at = due_at.replace(year=due_at.year - 1)
    if last_ran_at is None or last_ran_at < due_at:
        return due_at
    return None


def find_best_suchary(start_dt: datetime, end_dt: datetime) -> list[Suchar]:
    """Return all Suchary tied for the most votes published within [start_dt, end_dt).

    The window is measured on ``published_at``, not ``created_at`` (#371): a
    suchar written on Jan 30 but scheduled for Feb 5 collects no votes at all
    in January (nobody can see it — #331 makes voting on an unpublished
    suchar a 404), yet a ``created_at`` window would enter it in January's
    contest and never in February's, so it could never win any period despite
    real votes after publication. ``published_at`` is NOT NULL
    (``default=timezone.now``) and indexed, so this drops no rows and keeps
    using an index; for a suchar published the moment it was written — the
    common case — the two columns agree and nothing changes.

    No ``published_at__lte=now()`` guard is needed on top: an unpublished
    suchar cannot be voted on (#331), so it can only ever reach a 0-vote max,
    which is already excluded below. Adding one would also change what
    ``award_periodic --date`` reports for an in-progress period. On the cron
    and catch-up paths that #331 assumption isn't even needed: both only ever
    call this with a *completed* period, so ``end_dt <= now()`` there by
    construction, and ``published_at__lt=end_dt`` already implies
    ``published_at <= now()`` — the guard would be provably a no-op on those
    paths. #331 only matters for the one path that scores an in-progress
    period: a manual ``award_periodic --date <today>``.

    Postgres doesn't guarantee row order among ties on a plain
    ``.order_by("-vote_count")``, so rather than picking an arbitrary single
    "winner" (see #171) this returns every Suchar at the top vote count —
    ``award_winners`` decides what to do with a tie. Empty list if no Suchar
    was published in the range, or if every Suchar published has zero votes (a
    0-vote max doesn't count as a "best" — nobody actually won anything).
    """
    candidates = (
        Suchar.objects.filter(
            published_at__gte=start_dt,
            published_at__lt=end_dt,
        )
        .annotate(vote_count=Count("votes"))
        .select_related("author")
    )
    max_votes = candidates.aggregate(max_votes=Max("vote_count"))["max_votes"]
    if not max_votes:
        return []
    return list(candidates.filter(vote_count=max_votes).order_by("id"))


def award_winners(winners: list[Suchar], suffix: str) -> list[tuple[str, User, bool]]:
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


def _award_achievement(slug: str, users: set[User]) -> list[tuple[str, User, bool]]:
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
    for user in sorted(users, key=lambda u: u.username):
        _, created = UserAchievement.objects.get_or_create(
            user=user,
            achievement=achievement,
        )
        results.append((slug, user, created))
    return results


#: Job id for the publication catch-up run's ``SchedulerRun`` marker.
PUBLICATION_ACHIEVEMENTS_JOB_ID = "award-publication-achievements"

#: On the very first run (no ``SchedulerRun`` marker) only suchary published
#: within this window are re-checked. Anything older was already handled by the
#: ``post_save`` path when it was created, or by an earlier process — a fresh
#: deploy must not sweep the whole table. Matches the job's hourly cadence.
PUBLICATION_CATCHUP_FLOOR = timedelta(hours=1)

#: How far the catch-up window reaches back *before* the previous run.
#: ``SucharForm.clean_published_at`` accepts a ``published_at`` up to 5 min in
#: the past relative to the save, and a transaction may commit slightly after
#: ``now`` was sampled — either (or both, additively) can place a
#: just-published suchar's ``published_at`` before the last run's ``ran_at``,
#: where a bare ``published_at__gt=last_ran_at`` would drop it forever (nothing
#: else re-checks a suchar once its ``published_at`` has passed). Set to 3x the
#: form's skew allowance for comfortable headroom; the engine is idempotent, so
#: re-scanning this much already-processed history each run is free.
PUBLICATION_CATCHUP_OVERLAP = timedelta(minutes=15)


def award_publication_achievements(
    reference_time: datetime | None = None,
) -> None:
    """Re-run the achievement engine for suchary that became visible since the
    last run (#389).

    ``SucharCountRule`` / ``StreakLoginRule`` / ``NightOwlRule`` only count
    *published* suchary, so creating a scheduled suchar no longer awards its
    author a ``COUNT_SUCHAR`` / ``STREAK_LOGIN`` / ``NIGHT_OWL`` tier at
    ``post_save`` time. Nothing fires the engine when a scheduled suchar's
    ``published_at`` simply passes, so this hourly job — and its boot-time
    catch-up in ``AchievementsConfig._catch_up_missed_publication_run`` — walks
    every suchar whose ``published_at`` crossed
    ``(SchedulerRun.ran_at - PUBLICATION_CATCHUP_OVERLAP, now]`` and re-checks
    its author, bounding the award lag to ~1h.

    Iterates suchary and passes ``instance=suchar`` rather than looping distinct
    authors: ``NightOwlRule`` returns ``None`` without a ``Suchar`` instance.
    Idempotent — the engine skips already-owned achievements, so the
    ``PUBLICATION_CATCHUP_OVERLAP`` window overlap, or a restart gap
    re-processing a suchar, is a no-op.

    A failure while checking one suchar is logged and skipped, not propagated:
    otherwise a single poison record would abort the loop before the
    ``SchedulerRun`` marker is rewritten, and every subsequent hourly run would
    re-hit it and stall the same way.

    Runs in the scheduler's daemon thread; closes stale ORM connections on the
    way out for the same reason as ``award_best_suchar`` (skipped inside an
    atomic block, e.g. pytest-django's per-test transaction).
    """
    try:
        now = reference_time or timezone.now()
        last_ran_at = (
            SchedulerRun.objects.filter(job_id=PUBLICATION_ACHIEVEMENTS_JOB_ID)
            .values_list("ran_at", flat=True)
            .first()
        )
        since = (
            last_ran_at - PUBLICATION_CATCHUP_OVERLAP
            if last_ran_at is not None
            else now - PUBLICATION_CATCHUP_FLOOR
        )
        newly_published = (
            Suchar.objects.filter(published_at__gt=since, published_at__lte=now)
            .select_related("author")
            # Deterministic, chronological processing order (the plain queryset
            # has no ordering); `published_at` is indexed, `id` breaks ties.
            .order_by("published_at", "id")
            .iterator()
        )
        for suchar in newly_published:
            try:
                AchievementEngine.check_achievements(
                    suchar.author,
                    Achievement.EventType.SUCHAR_POSTED,
                    suchar,
                )
            except Exception:
                logger.exception(
                    "Failed to check publication achievements for suchar #%s; "
                    "skipping it and continuing",
                    suchar.pk,
                )
        SchedulerRun.objects.update_or_create(
            job_id=PUBLICATION_ACHIEVEMENTS_JOB_ID,
            defaults={"ran_at": now},
        )
    finally:
        if not connection.in_atomic_block:
            close_old_connections()


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
