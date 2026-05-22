"""
Settings for Playwright E2E tests.

Extends test.py but allows CSRF and trusted origins needed when
pytest-django's live_server serves at http://127.0.0.1:<port>.
"""

from .test import *  # noqa: F403
from .test import ALLOWED_HOSTS

# live_server binds to 127.0.0.1 — trust it for CSRF checks
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "127.0.0.1", "localhost"]

# Django 4+ CSRF middleware validates the Origin header against this list.
# Playwright sends Origin: http://127.0.0.1:<port> on every POST.
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1", "http://localhost"]
