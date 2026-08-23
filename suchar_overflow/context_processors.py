from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings

import suchar_overflow

if TYPE_CHECKING:
    from django.http import HttpRequest


def site_settings(request: HttpRequest) -> dict[str, Any]:
    """Expose configurable site-level settings to all templates."""
    theme = request.COOKIES.get("theme", "")
    if theme not in ("dark", "light"):
        theme = "light"
    return {
        "FEEDBACK_URL": getattr(settings, "FEEDBACK_URL", ""),
        "APP_VERSION": suchar_overflow.__version__,
        "THEME": theme,
    }
