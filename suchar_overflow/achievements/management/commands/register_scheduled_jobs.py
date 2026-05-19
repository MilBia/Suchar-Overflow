import django_rq
from django.core.management.base import BaseCommand

from suchar_overflow.achievements.tasks import award_best_suchar

_SCHEDULED_JOBS = [
    {
        "cron": "5 0 1 * *",  # 1st of every month at 00:05 UTC
        "func": award_best_suchar,
        "args": ["month"],
        "id": "award-best-suchar-month",
    },
]


class Command(BaseCommand):
    help = "Registers recurring scheduled jobs with rq-scheduler (idempotent)"

    def handle(self, *args, **options):
        scheduler = django_rq.get_scheduler("default")

        existing_ids = {job.id for job in scheduler.get_jobs()}

        for spec in _SCHEDULED_JOBS:
            if spec["id"] in existing_ids:
                scheduler.cancel(spec["id"])
                self.stdout.write(f"Replaced existing job: {spec['id']}")

            scheduler.cron(
                spec["cron"],
                func=spec["func"],
                args=spec["args"],
                id=spec["id"],
                use_local_timezone=False,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Registered: {spec['id']} ({spec['cron']})"),
            )
