"""RQ worker hooks (#461)."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import TracebackType

    from rq.job import Job

# A child of "django": production's ``mail_admins`` handler sits on that logger, so a
# job that gave up reaches the admins the way a 500 does. ``rq.worker`` itself does not
# propagate to it (see LOGGING in base.py).
logger = logging.getLogger("django.rq")


def mail_admins_on_final_failure(
    job: Job,
    exc_type: type[BaseException],
    exc_value: BaseException,
    traceback: TracebackType | None,
) -> bool:
    """``RQ_EXCEPTION_HANDLERS`` entry: report a job once its retries are exhausted.

    RQ calls the handlers on every failed attempt, before it re-queues a job that still
    has ``Retry`` attempts left; those are skipped, so a flaky SMTP server mails the
    admins once per undelivered message, not once per attempt. Returns ``True`` so RQ's
    remaining handlers (and its default move to the failed registry) still run.
    """
    if job.should_retry:
        return True
    logger.error(
        "RQ job %s (%s) failed permanently",
        job.id,
        job.func_name,
        exc_info=(exc_type, exc_value, traceback),
    )
    return True
