import sys
import threading

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

_NO_SCHEDULER = frozenset(
    {
        "migrate",
        "makemigrations",
        "collectstatic",
        "compress",
        "check",
        "shell",
        "createsuperuser",
    },
)


class AchievementsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "suchar_overflow.achievements"
    verbose_name = _("Achievements")

    def ready(self):
        import suchar_overflow.achievements.signals  # noqa: F401

        if "pytest" in sys.modules:
            return
        if len(sys.argv) > 1 and sys.argv[1] in _NO_SCHEDULER:
            return

        # DjangoJobStore uses sync ORM; run in a plain thread so there is
        # no running asyncio loop (uvicorn sets one up before importing asgi.py).
        threading.Thread(target=self._start_scheduler, daemon=True).start()

    @staticmethod
    def _start_scheduler():
        from apscheduler.schedulers.background import BackgroundScheduler
        from django_apscheduler.jobstores import DjangoJobStore

        from suchar_overflow.achievements.tasks import award_best_suchar

        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_jobstore(DjangoJobStore(), "default")
        scheduler.add_job(
            award_best_suchar,
            "cron",
            args=["month"],
            day=1,
            hour=0,
            minute=5,
            id="award-best-suchar-month",
            replace_existing=True,
            jobstore="default",
        )
        scheduler.start()
