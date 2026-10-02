"""Container healthcheck for the RQ ``worker`` and ``cron`` services (#460, #462).

Exit status 0 when healthy, 1 otherwise (the reason goes to stderr):

* default: every queue in ``RQ_QUEUES`` has at least one registered worker;
* ``--cron``: a ``CronScheduler`` heartbeat is younger than ``--max-age`` seconds.
"""

from datetime import timedelta
from typing import Any

import django_rq
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.core.management.base import CommandParser
from django.utils import timezone
from rq import Worker
from rq.cron import CronScheduler

# The scheduler beats at least every 60 s (CronScheduler.calculate_sleep_interval caps its sleep).
DEFAULT_CRON_MAX_AGE_SECONDS = 150


class Command(BaseCommand):
    help = "Fail when an RQ queue has no worker (or, with --cron, the cron scheduler has no fresh heartbeat)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--cron", action="store_true", help="Check the cron scheduler instead of the workers.")
        parser.add_argument(
            "--max-age",
            type=int,
            default=DEFAULT_CRON_MAX_AGE_SECONDS,
            help="With --cron: oldest acceptable heartbeat, in seconds.",
        )

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401, ARG002
        try:
            if options["cron"]:
                self._check_cron(options["max_age"])
            else:
                self._check_workers()
        except CommandError:
            raise
        except Exception as exc:
            msg = f"RQ healthcheck could not reach the queue: {exc}"
            raise CommandError(msg) from exc

    def _check_workers(self) -> None:
        missing = []
        for name in settings.RQ_QUEUES:
            queue = django_rq.get_queue(name)
            if Worker.count(connection=queue.connection, queue=queue) == 0:
                missing.append(name)
        if missing:
            msg = f"No worker is listening on queue(s): {', '.join(missing)}"
            raise CommandError(msg)

    def _check_cron(self, max_age: int) -> None:
        connection = django_rq.get_queue(settings.RQ_QUEUE_NAME).connection
        now = timezone.now()
        beats = [scheduler.last_heartbeat for scheduler in CronScheduler.all(connection)]
        if not any(beat is not None and now - beat <= timedelta(seconds=max_age) for beat in beats):
            msg = f"No cron scheduler heartbeat within the last {max_age} s"
            raise CommandError(msg)
