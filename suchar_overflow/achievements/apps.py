import logging
import sys
import threading

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

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
    def _catch_up_missed_monthly_run():
        """Run ``award_best_suchar`` immediately if the last due monthly
        cron fire was never recorded (e.g. the process was down when the
        in-memory jobstore would have fired it — see #169).

        Passes the missed fire's own date as ``reference_date`` rather than
        letting ``award_best_suchar`` default to "yesterday" — at catch-up
        time "yesterday" is relative to whenever the process happens to
        restart, not to the period that was actually missed.
        """
        from datetime import timedelta

        from django.utils import timezone

        from suchar_overflow.achievements.models import SchedulerRun
        from suchar_overflow.achievements.tasks import award_best_suchar
        from suchar_overflow.achievements.tasks import due_monthly_run_at

        job_id = "award-best-suchar-month"
        last_run = (
            SchedulerRun.objects.filter(job_id=job_id)
            .values_list("ran_at", flat=True)
            .first()
        )
        due_at = due_monthly_run_at(timezone.now(), last_run)
        if due_at is not None:
            logger.info(
                "Missed scheduler run detected for %s; catching up now",
                job_id,
            )
            award_best_suchar("month", reference_date=due_at.date() - timedelta(days=1))

    @staticmethod
    def _start_scheduler():
        from apscheduler.schedulers.background import BackgroundScheduler

        from suchar_overflow.achievements.tasks import award_best_suchar

        AchievementsConfig._catch_up_missed_monthly_run()

        # In-memory jobstore (apscheduler's default): the job re-registers on
        # every process start, so it doesn't need DB-backed persistence.
        # See SchedulerRun (achievements/models.py) for last-run visibility.
        # _catch_up_missed_monthly_run() above covers a run missed while the
        # process was down.
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
