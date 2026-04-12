from django.conf import settings


def site_settings(request):
    """Expose configurable site-level settings to all templates."""
    return {
        "FEEDBACK_URL": getattr(settings, "FEEDBACK_URL", ""),
    }
