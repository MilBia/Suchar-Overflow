from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UtilsConfig(AppConfig):
    """Cross-cutting code shared by the other apps (#455).

    Error handlers, middleware, context processors, logging and DB-connection
    helpers, and shared API schemas. It has no models.
    """

    name = "suchar_overflow.utils"
    # A bare "utils" label is generic enough to clash with a third-party app, and
    # renaming a label becomes a migration problem once the app has models.
    label = "suchar_utils"
    verbose_name = _("Narzędzia")
