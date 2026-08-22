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
        # django-stubs' mypy plugin calls django.setup(), which runs this
        # method outside of any real serving process — skip starting a
        # scheduler thread that would write to the DB as a side effect.
        if "mypy" in sys.modules:
            return
        if self._is_no_scheduler_command(sys.argv):
            return

        # The scheduled job uses the sync Django ORM; run it in a plain thread
        # so there is no running asyncio loop (uvicorn sets one up before
        # importing asgi.py).
        threading.Thread(target=self._start_scheduler, daemon=True).start()

    @staticmethod
    def _is_no_scheduler_command(argv: list[str]) -> bool:
        """True if argv invokes a management command in ``_NO_SCHEDULER``.

        The command name is the first non-flag token after ``argv[0]``, so a
        global flag before it (e.g. ``--settings=...``) doesn't defeat the
        check — but unlike a blanket membership scan across all of ``argv``,
        this won't misfire on a command whose own argument happens to spell
        one of these words (e.g. ``manage.py test -k check``).
        """
        command = next((arg for arg in argv[1:] if not arg.startswith("-")), None)
        return command in _NO_SCHEDULER

    @staticmethod
    def _start_scheduler():
        from apscheduler.schedulers.background import BackgroundScheduler

        from suchar_overflow.achievements.tasks import award_best_suchar

        # In-memory jobstore (apscheduler's default): the job re-registers on
        # every process start, so it doesn't need DB-backed persistence.
        # See SchedulerRun (achievements/models.py) for last-run visibility.
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            award_best_suchar,
            "cron",
            args=["month"],
            day=1,
            hour=0,
            minute=5,
            id="award-best-suchar-month",
        )
        scheduler.start()
