"""Base settings to build other settings files upon."""

from pathlib import Path
from urllib.parse import quote

import environ
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
# suchar_overflow/
APPS_DIR = BASE_DIR / "suchar_overflow"
env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))
# Secrets kept out of git (e.g. third-party API keys), loaded only when the file
# exists. Like .env above, a variable already in the OS environment wins.
# read_env() only setdefault()s, so the first source to set a name wins: OS env,
# then .env (when DJANGO_READ_DOT_ENV_FILE), then this file.
# .gitignore and .dockerignore both exclude it (#453), so it is a local-only
# mechanism: the production image never contains it and production compose does
# not mount it — production secrets go in .envs/.production/.django.
SECRETS_ENV_FILE = BASE_DIR / ".envs" / ".secrets"
if SECRETS_ENV_FILE.is_file():
    env.read_env(str(SECRETS_ENV_FILE))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "Europe/Warsaw"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "pl"
# https://docs.djangoproject.com/en/dev/ref/settings/#languages


LANGUAGES = [
    ("ar", _("Arabic")),
    ("bg", _("Bulgarian")),
    ("bn", _("Bengali")),
    ("ca", _("Catalan")),
    ("cs", _("Czech")),
    ("da", _("Danish")),
    ("de", _("German")),
    ("el", _("Greek")),
    ("en", _("English")),
    ("es", _("Spanish")),
    ("et", _("Estonian")),
    ("fa", _("Persian")),
    ("fi", _("Finnish")),
    ("fr", _("French")),
    ("he", _("Hebrew")),
    ("hi", _("Hindi")),
    ("hr", _("Croatian")),
    ("hu", _("Hungarian")),
    ("id", _("Indonesian")),
    ("is", _("Icelandic")),
    ("it", _("Italian")),
    ("ja", _("Japanese")),
    ("kn", _("Kannada")),
    ("ko", _("Korean")),
    ("lt", _("Lithuanian")),
    ("lv", _("Latvian")),
    ("ml", _("Malayalam")),
    ("mr", _("Marathi")),
    ("nb", _("Norwegian")),
    ("nl", _("Dutch")),
    ("pa", _("Punjabi")),
    ("pl", _("Polish")),
    ("pt", _("Portuguese")),
    ("pt-br", _("Brazilian Portuguese")),
    ("ro", _("Romanian")),
    ("ru", _("Russian")),
    ("sk", _("Slovak")),
    ("sl", _("Slovenian")),
    ("sr", _("Serbian")),
    ("sv", _("Swedish")),
    ("sw", _("Swahili")),
    ("ta", _("Tamil")),
    ("te", _("Telugu")),
    ("th", _("Thai")),
    ("tr", _("Turkish")),
    ("uk", _("Ukrainian")),
    ("ur", _("Urdu")),
    ("vi", _("Vietnamese")),
    ("zh-hans", _("Chinese (Simplified)")),
    ("zh-hant", _("Chinese (Traditional)")),
]
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id

# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS = [str(BASE_DIR / "locale")]

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases


def _postgres_url() -> str:
    """Assemble the DSN from the POSTGRES_* variables the postgres container uses.

    Only called when DATABASE_URL is absent, so a DATABASE_URL-only environment
    (CI's mypy job) never needs POSTGRES_*. User, password and database name are
    percent-encoded the same way the /entrypoint script does (#356);
    a missing variable raises ImproperlyConfigured naming it. POSTGRES_USER
    defaults to the postgres image's own default, as in the entrypoint.
    """
    try:
        user = quote(env("POSTGRES_USER", default="postgres"), safe="")
        password = quote(env("POSTGRES_PASSWORD"), safe="")
        name = quote(env("POSTGRES_DB"), safe="")
        host = env("POSTGRES_HOST")
        port = env("POSTGRES_PORT")
    except ImproperlyConfigured as exc:
        msg = f"{exc}, or set DATABASE_URL instead of POSTGRES_*"
        raise ImproperlyConfigured(msg) from exc
    return f"postgres://{user}:{password}@{host}:{port}/{name}"


# Presence, not truthiness: the production image compiles messages at build time
# with DATABASE_URL="" and no POSTGRES_* at all.
if "DATABASE_URL" in env.ENVIRON:
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    # Lets `docker compose exec django python manage.py ...` work without going
    # through /entrypoint, which is what exported DATABASE_URL before (#404, #453).
    DATABASES = {"default": env.db_url_config(_postgres_url())}
# 0 = close after each request. Django's docs: "When using ASGI, persistent
# connections should be disabled" — each request runs in its own thread, so a
# kept-alive connection outlives it and piles up until Postgres refuses (#430).
DATABASES["default"]["CONN_MAX_AGE"] = 0
# ATOMIC_REQUESTS is disabled: async views are incompatible with it.
# Views that need transactions use transaction.atomic() / transaction.aatomic() explicitly.
# DEFAULT_AUTO_FIELD is not set explicitly: Django 6.0's default is already
# "django.db.models.BigAutoField".

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"
# https://docs.djangoproject.com/en/dev/ref/settings/#asgi-application
ASGI_APPLICATION = "config.asgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.forms",
]
THIRD_PARTY_APPS = [
    "compressor",
]

LOCAL_APPS = [
    "suchar_overflow.users",
    "suchar_overflow.suchary",
    "suchar_overflow.stats",
    "suchar_overflow.achievements",
    "suchar_overflow.utils",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
# modeltranslation must precede django.contrib.admin
INSTALLED_APPS = ["modeltranslation", *DJANGO_APPS, *THIRD_PARTY_APPS, *LOCAL_APPS]

# MODELTRANSLATION
# ------------------------------------------------------------------------------
MODELTRANSLATION_DEFAULT_LANGUAGE = "pl"
MODELTRANSLATION_LANGUAGES = ("pl", "en")
MODELTRANSLATION_FALLBACK_LANGUAGES = ("pl",)

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules


# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "users.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = "suchary:list"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = "login"
# https://docs.djangoproject.com/en/dev/ref/settings/#logout-redirect-url
LOGOUT_REDIRECT_URL = "home"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    # Visitor's browser zone for input/display only (#410).
    "suchar_overflow.utils.middleware.user_timezone_middleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = env("DJANGO_STATIC_ROOT", default=str(BASE_DIR / "staticfiles"))
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(APPS_DIR / "static")]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "compressor.finders.CompressorFinder",
]

# COMPRESSOR
# ------------------------------------------------------------------------------
COMPRESS_ENABLED = False  # Enabled per-environment (production.py)
COMPRESS_CSS_FILTERS = [
    "compressor.filters.css_default.CssAbsoluteFilter",
    "compressor.filters.rcssmin.RCSSMinFilter",
]
COMPRESS_JS_FILTERS = [
    "compressor.filters.jsmin.RJSMinFilter",
]
COMPRESS_STORAGE = "compressor.storage.GzipCompressorFileStorage"
COMPRESS_OFFLINE = False  # Enabled per-environment in production.py

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(APPS_DIR / "media")
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [str(APPS_DIR / "templates")],
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "APP_DIRS": True,
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csp",
                "suchar_overflow.utils.context_processors.site_settings",
                "suchar_overflow.achievements.context_processors.achievements_bell",
            ],
        },
    },
]


# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),)

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/topics/email/#mailers
# Django 6.x replaces the flat EMAIL_* settings (deprecated, removed in 7.0)
# with a DATABASES/CACHES-style MAILERS mapping. Every option comes from a
# DJANGO_EMAIL_<X> variable; the defaults are the conservative SMTP-to-
# localhost:25, no-auth behaviour. Local points it at mailpit through
# .envs/.local/.django, production through .envs/.production/.django.
# The pre-#453 names (EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, ...) are still read
# as a fallback for one release — see CHANGELOG.md. The helper is lowercase on
# purpose: an uppercase EMAIL_* module attribute next to MAILERS makes Django
# raise ImproperlyConfigured.


def _email_env(option: str, default: str) -> str:
    """Value of DJANGO_EMAIL_<option>, else legacy EMAIL_<option>, else default.

    An empty value counts as unset, unlike DATABASE_URL's "presence, not
    truthiness" rule above (which the production build relies on — don't unify
    them). A blank `DJANGO_EMAIL_PORT=` left behind while migrating off EMAIL_*
    would otherwise crash int() at import, and a blank `DJANGO_EMAIL_HOST=` would
    shadow a still-set legacy EMAIL_HOST with host "". Every option's default is
    what an empty value would mean anyway ("" user/password, False TLS/SSL).
    """
    for name in (f"DJANGO_EMAIL_{option}", f"EMAIL_{option}"):
        if value := env.ENVIRON.get(name, ""):
            return value
    return default


MAILERS = {
    "default": {
        # Same "empty = unset" rule as _email_env (no legacy EMAIL_BACKEND name to
        # fall back to): a blank BACKEND imports fine but makes every send raise
        # InvalidMailer, which logging swallows for mail_admins.
        "BACKEND": env("DJANGO_EMAIL_BACKEND", default="") or "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": _email_env("HOST", "localhost"),
            "port": int(_email_env("PORT", "25")),
            "username": _email_env("HOST_USER", ""),
            "password": _email_env("HOST_PASSWORD", ""),
            # STARTTLS (port 587) vs. implicit TLS / SMTPS (port 465) — set at
            # most one. Django's SMTP backend rejects both being True.
            "use_tls": env.parse_value(_email_env("USE_TLS", "False"), bool),
            "use_ssl": env.parse_value(_email_env("USE_SSL", "False"), bool),
            "timeout": int(_email_env("TIMEOUT", "5")),
        },
    },
}

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
# Comma-separated addresses, each either "mail@example.com" or
# "Name <mail@example.com>" (no comma inside a name — it is the separator).
# Django 6.x takes a plain list of address strings here; (name, address) pairs
# are deprecated. env.list() neither strips entries nor drops blank ones, and a
# single " " entry (e.g. a trailing ", ") makes every mail_admins send raise, which
# logging swallows — so 500 reports would vanish silently.
ADMINS = [address.strip() for address in env.list("DJANGO_ADMINS", default=[]) if address.strip()]
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        # award-publication-achievements runs every minute (#402); apscheduler's
        # INFO "Running job" / "executed successfully" pair would add ~2880
        # lines a day. Job errors and missed-run warnings still get through.
        "apscheduler.executors": {"level": "WARNING"},
        # Replaces the handlers Django's DEFAULT_LOGGING puts on "django"
        # (disable_existing_loggers=False keeps them otherwise, #447): a stock
        # AdminEmailHandler, which production's mail_admins duplicated, and a
        # console handler repeating what reaches root's. Side effect: dictConfig
        # resets django.* children, so DEFAULT_LOGGING's django.server (runserver's
        # request log) loses its own handler and propagates to root instead; this
        # project serves through uvicorn, which never logs there.
        "django": {"handlers": [], "level": "INFO"},
    },
}

# No default: set in .envs/.local/.django and .envs/.production/.django (#453).
REDIS_URL = env("REDIS_URL")
REDIS_SSL = REDIS_URL.startswith("rediss://")

# CACHES
# ------------------------------------------------------------------------------
# Defined only here (#454): local and production both use this Redis cache, so the
# shared-cache behaviour (the SSE `achievements_pending` flag, the toast latch) is
# the same in dev as in production and survives a dev-server restart. Only test.py
# swaps in LocMem. tests/test_cache_settings.py guards the layering.
# https://docs.djangoproject.com/en/dev/ref/settings/#caches
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {"ssl_cert_reqs": None} if REDIS_SSL else {},
            # Mimicking memcache behavior: a Redis outage degrades to cache misses
            # instead of 500s.
            # https://github.com/jazzband/django-redis#memcached-exceptions-behavior
            "IGNORE_EXCEPTIONS": True,
        },
    },
}

# CSP
# ------------------------------------------------------------------------------
from django.utils.csp import CSP  # noqa: E402

SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],  # CSS custom properties
    "img-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],  # covers the SSE endpoint
    "font-src": [CSP.SELF],
}

# FEEDBACK
# ------------------------------------------------------------------------------
# URL for the feedback/bug report link shown in the footer.
# Override via the FEEDBACK_URL environment variable.
FEEDBACK_URL = env(
    "FEEDBACK_URL",
    default="https://github.com/MilBia/Suchar-Overflow/issues/new",
)
