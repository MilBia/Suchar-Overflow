from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AchievementsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "suchar_overflow.achievements"
    verbose_name = _("Achievements")

    def ready(self) -> None:
        # Periodic jobs no longer start here: the `cron` service runs them via
        # `rqcron` (achievements/cron.py, #462), so a web worker starts no scheduler.
        import suchar_overflow.achievements.signals  # noqa: F401
