from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class AchievementsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "suchar_overflow.achievements"
    verbose_name = _("Achievements")

    def ready(self):
        import suchar_overflow.achievements.signals  # noqa: F401

        if getattr(settings, "SCHEDULER_AUTOSTART", False):
            self._start_scheduler()

    def _start_scheduler(self):
        from suchar_overflow.achievements.tasks import award_best_suchar

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            award_best_suchar,
            CronTrigger.from_crontab("5 0 1 * *"),
            args=["month"],
            id="award-best-suchar-month",
            replace_existing=True,
        )
        scheduler.start()
