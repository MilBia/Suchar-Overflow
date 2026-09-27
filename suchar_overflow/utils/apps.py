from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UtilsConfig(AppConfig):
    """Cross-cutting code shared by the other apps (#455).

    Error handlers, middleware, context processors, logging and DB-connection
    helpers, and shared API schemas. It has no models.
    """

    name = "suchar_overflow.utils"
    verbose_name = _("Narzędzia")
