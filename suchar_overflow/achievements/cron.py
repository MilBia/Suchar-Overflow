"""Periodic jobs for ``rqcron`` (#462) — loaded by ``manage.py rqcron suchar_overflow.achievements.cron``.

Replaces the in-process APScheduler jobs. ``rq.cron`` evaluates cron strings in
**UTC** (``rq.utils.now()``), while the contests roll over at 00:05 ``Europe/Warsaw``
(#405), whose UTC offset changes with DST. A fixed cron string cannot hit
"00:05 Polish time", so the two contest jobs fire **hourly at :05** — every Warsaw
offset is a whole hour, so :05 UTC is :05 local — and run
``award_best_suchar_*_if_due``: when the service-local fire time has passed and its
``SchedulerRun`` marker was never written, award it; otherwise do nothing. The first
check after 00:05 local on the 1st therefore is the fire, and the same function
doubles as the catch-up for a fire missed while this service was down (#169).
"""

from typing import TYPE_CHECKING

from django.conf import settings
from rq.cron import register

from suchar_overflow.achievements.tasks import award_best_suchar_month_if_due
from suchar_overflow.achievements.tasks import award_best_suchar_year_if_due
from suchar_overflow.achievements.tasks import award_publication_achievements

if TYPE_CHECKING:
    from collections.abc import Callable

HOURLY_AT_5 = "5 * * * *"
EVERY_MINUTE = "* * * * *"

# Hourly checks: an instance still queued after 50 minutes is superseded by the next one.
_HOURLY_TTL = 50 * 60
# Every minute (#402): with a stopped worker the queue must not pile up (#462). The task is
# idempotent and sweeps a 15-minute overlap, so dropping a few runs is safe.
_MINUTELY_TTL = 120
_JOB_TIMEOUT = 300
_RESULT_TTL = 300
_FAILURE_TTL = 7 * 24 * 60 * 60


def _register(func: Callable[[], object], *, cron: str, ttl: int, name: str) -> None:
    register(
        func,
        queue_name=settings.RQ_QUEUE_NAME,
        cron=cron,
        ttl=ttl,
        name=name,
        job_timeout=_JOB_TIMEOUT,
        result_ttl=_RESULT_TTL,
        failure_ttl=_FAILURE_TTL,
    )


_register(award_best_suchar_month_if_due, cron=HOURLY_AT_5, ttl=_HOURLY_TTL, name="award-best-suchar-month")
_register(award_best_suchar_year_if_due, cron=HOURLY_AT_5, ttl=_HOURLY_TTL, name="award-best-suchar-year")
# Awards COUNT_SUCHAR/STREAK/NIGHT_OWL for suchary whose published_at passed since the
# last run, so a scheduled suchar's achievements land within ~1 min of going live (#389, #402).
_register(award_publication_achievements, cron=EVERY_MINUTE, ttl=_MINUTELY_TTL, name="award-publication-achievements")
