"""
Settings for Playwright E2E tests.

Extends test.py but allows CSRF and trusted origins needed when
pytest-django's live_server serves at http://127.0.0.1:<port>.
"""

import os

from .test import *  # noqa: F403

# live_server binds to 127.0.0.1 — trust it for CSRF checks
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

# Django 4+ CSRF middleware validates the Origin header against this list.
# Playwright sends Origin: http://127.0.0.1:<port> on every POST.
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1", "http://localhost"]

# Playwright runs tests inside an async event loop. Django's ORM normally
# blocks sync DB access from async contexts; this flag disables that guard
# so that pytest-django fixtures (db, live_server) can set up the database.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
