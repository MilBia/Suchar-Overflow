import copy
from typing import Any

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import DATABASES
from .base import LOGGING
from .base import REDIS_URL
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env("DJANGO_SECRET_KEY")
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["example.com"])

# DATABASES
# ------------------------------------------------------------------------------
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

# CACHES
# ------------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # Mimicking memcache behavior.
            # https://github.com/jazzband/django-redis#memcached-exceptions-behavior
            "IGNORE_EXCEPTIONS": True,
        },
    },
}

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-proxy-ssl-header
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-ssl-redirect
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-secure
SESSION_COOKIE_SECURE = True
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-name
SESSION_COOKIE_NAME = "__Secure-sessionid"
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-secure
CSRF_COOKIE_SECURE = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-name
CSRF_COOKIE_NAME = "__Secure-csrftoken"
# https://docs.djangoproject.com/en/dev/topics/security/#ssl-https
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-seconds
# Cautious 6-day ramp value by default. Raise via env (to >= 31536000, one
# year) once HTTPS is proven stable on every subdomain — see SECURE_HSTS_PRELOAD.
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=518400)
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-include-subdomains
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=True,
)
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-preload
# Off by default: the browser preload list rejects a `preload` directive whose
# max-age is under 31536000 (one year), and the ramp value above is far lower —
# shipping both together is an inconsistent header (issue #353). Opt in via env
# *together with* a >= 1-year DJANGO_SECURE_HSTS_SECONDS once the domain is ready
# to commit to the (hard-to-undo) preload list.
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)
# Fail fast rather than emit the exact inconsistent header #353 is about: an
# operator who flips on DJANGO_SECURE_HSTS_PRELOAD but forgets to raise
# DJANGO_SECURE_HSTS_SECONDS would otherwise ship `preload` with a sub-year
# max-age, silently rejected by hstspreload.org. Django's own security.W021
# check only catches SECURE_HSTS_SECONDS == 0, not the 1-year list minimum.
if SECURE_HSTS_PRELOAD and SECURE_HSTS_SECONDS < 31536000:  # noqa: PLR2004
    msg = (
        "SECURE_HSTS_PRELOAD requires SECURE_HSTS_SECONDS >= 31536000 "
        f"(one year); got {SECURE_HSTS_SECONDS}. Raise "
        "DJANGO_SECURE_HSTS_SECONDS or unset DJANGO_SECURE_HSTS_PRELOAD."
    )
    raise ImproperlyConfigured(msg)
# https://docs.djangoproject.com/en/dev/ref/middleware/#x-content-type-options-nosniff
SECURE_CONTENT_TYPE_NOSNIFF = env.bool(
    "DJANGO_SECURE_CONTENT_TYPE_NOSNIFF",
    default=True,
)

# STATIC & MEDIA
# ------------------------
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#default-from-email
DEFAULT_FROM_EMAIL = env(
    "DJANGO_DEFAULT_FROM_EMAIL",
    default="Suchar Overflow <noreply@example.com>",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#server-email
SERVER_EMAIL = env("DJANGO_SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-subject-prefix
EMAIL_SUBJECT_PREFIX = env(
    "DJANGO_EMAIL_SUBJECT_PREFIX",
    default="[Suchar Overflow] ",
)
# https://docs.djangoproject.com/en/dev/topics/email/#mailers
# SMTP credentials come from the env vars documented in
# .envs/.production/.django.example. Defaults keep the pre-migration
# behaviour (localhost:25, no auth) when they are left unset.
MAILERS = {
    "default": {
        "BACKEND": env(
            "DJANGO_EMAIL_BACKEND",
            default="django.core.mail.backends.smtp.EmailBackend",
        ),
        "OPTIONS": {
            "host": env("EMAIL_HOST", default="localhost"),
            "port": env.int("EMAIL_PORT", default=25),
            "username": env("EMAIL_HOST_USER", default=""),
            "password": env("EMAIL_HOST_PASSWORD", default=""),
            # STARTTLS (port 587) vs. implicit TLS / SMTPS (port 465) — set at
            # most one. Django's SMTP backend rejects both being True.
            "use_tls": env.bool("EMAIL_USE_TLS", default=False),
            "use_ssl": env.bool("EMAIL_USE_SSL", default=False),
            "timeout": env.int("EMAIL_TIMEOUT", default=5),
        },
    },
}

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL regex.
ADMIN_URL = env("DJANGO_ADMIN_URL")


# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
# Extends base.py's LOGGING (formatter "verbose", handler "console") rather
# than redefining it from scratch — deepcopy so mutating nested dicts below
# doesn't leak back into base.LOGGING. The only tangible addition here is
# sending an email to the site admins on every HTTP 500 error when
# DEBUG=False.
logging_config: dict[str, Any] = copy.deepcopy(LOGGING)
logging_config["filters"] = {
    "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
}
logging_config["handlers"]["mail_admins"] = {
    "level": "ERROR",
    "filters": ["require_debug_false"],
    "class": "django.utils.log.AdminEmailHandler",
}
logging_config["loggers"] = {
    "django.request": {
        "handlers": ["mail_admins"],
        "level": "ERROR",
        "propagate": True,
    },
    "django.security.DisallowedHost": {
        "level": "ERROR",
        "handlers": ["console", "mail_admins"],
        "propagate": True,
    },
}
LOGGING = logging_config


# COMPRESSOR
# ------------------------------------------------------------------------------
COMPRESS_ENABLED = True
COMPRESS_OFFLINE = True
