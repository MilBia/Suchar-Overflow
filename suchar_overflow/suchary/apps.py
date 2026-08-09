from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SucharyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "suchar_overflow.suchary"
    verbose_name = _("Suchary")
