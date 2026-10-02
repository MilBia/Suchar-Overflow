"""
With these settings, tests run faster.
"""

from .base import *  # noqa: F403
from .base import TEMPLATES
from .base import WEBPACK_LOADER
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="KqTCFZ5GA2HTJMzxoysO61eJDYTm32LNzLc9KCjYmvSVXg481f7p9xfL0eo2jLpX",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#test-runner
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/topics/email/#mailers
# In-memory outbox for assertions. (setup_test_environment() would force this
# per-alias anyway, but keeping it explicit matches the other settings layers.)
MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"},
}

# DEBUGGING FOR TEMPLATES
# ------------------------------------------------------------------------------
TEMPLATES[0]["OPTIONS"]["debug"] = True  # type: ignore[index]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "http://media.testserver/"

# WEBPACK (#466)
# ------------------------------------------------------------------------------
# No built bundles in unit tests: render_bundle yields one placeholder tag instead of
# reading webpack-stats.json. e2e.py restores the real loader.
WEBPACK_LOADER = {"DEFAULT": {**WEBPACK_LOADER["DEFAULT"], "LOADER_CLASS": "webpack_loader.loaders.FakeWebpackLoader"}}

# CACHE
# ------------------------------------------------------------------------------
# Use in-memory cache so tests don't require a running Redis instance.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}
