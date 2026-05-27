from django.conf import settings

import suchar_overflow


def site_settings(request):
    """Expose configurable site-level settings to all templates."""
    theme = request.COOKIES.get("theme", "")
    if theme not in ("dark", "light"):
        theme = "light"
    return {
        "FEEDBACK_URL": getattr(settings, "FEEDBACK_URL", ""),
        "APP_VERSION": suchar_overflow.__version__,
        "THEME": theme,
    }
