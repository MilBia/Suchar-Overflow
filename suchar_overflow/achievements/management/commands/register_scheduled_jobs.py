from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
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
    help = "Lists APScheduler jobs registered on server startup (for diagnostics)"

    def handle(self, *args, **options):
        scheduler = BackgroundScheduler()

        for spec in _SCHEDULED_JOBS:
            scheduler.add_job(
                spec["func"],
                CronTrigger.from_crontab(spec["cron"]),
                args=spec["args"],
                id=spec["id"],
                replace_existing=True,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Would register: {spec['id']} ({spec['cron']})",
                ),
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Jobs listed above start automatically on server startup.",
            ),
        )
