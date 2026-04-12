from django.conf import settings

import suchar_overflow


def site_settings(request):
    """Expose configurable site-level settings to all templates."""
    return {
        "FEEDBACK_URL": getattr(settings, "FEEDBACK_URL", ""),
        "APP_VERSION": suchar_overflow.__version__,
    }
