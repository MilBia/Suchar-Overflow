import faulthandler
import signal
import socket

from suchar_overflow.utils.debug import InternalIPs

from .base import *  # noqa: F403
from .base import INSTALLED_APPS
from .base import MIDDLEWARE
from .base import TEMPLATES
from .base import WEBPACK_LOADER
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = True
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
# No default in code: the dev key lives in .envs/.local/.django (#453).
SECRET_KEY = env("DJANGO_SECRET_KEY")
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
# Wildcard is fine for local dev only; the other entries were redundant.
ALLOWED_HOSTS = ["*"]

# TEMPLATES
# ------------------------------------------------------------------------------
# Non-cached loaders (#454). With DEBUG on, Django still wraps the loaders in the
# cached loader and relies on runserver's autoreloader to reset it when a template
# changes. The dev server is uvicorn, which never sends that signal, and its
# --reload only restarts on *.py/*.mo, so an edited *.html kept rendering the old
# version until a restart. Listing the loaders explicitly (APP_DIRS must then be
# False) re-reads every template on each render.
TEMPLATES[0]["APP_DIRS"] = False
TEMPLATES[0]["OPTIONS"]["loaders"] = [  # type: ignore[index]
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]

# EMAIL
# ------------------------------------------------------------------------------
# base.py's MAILERS reads DJANGO_EMAIL_HOST/PORT; .envs/.local/.django points them
# at the mailpit container (web UI on localhost:8025).

# STATIC
# ------------------------------------------------------------------------------
# uvicorn serves no static files and there is no runserver; config/asgi.py wraps the
# app in ASGIStaticFilesHandler while DEBUG is on (#463).


# WEBPACK (#466)
# ------------------------------------------------------------------------------
# Re-read webpack-stats.json on every render: the `node` service rewrites it on each
# rebuild and the loader (DEBUG on) waits while its status is "compile".
WEBPACK_LOADER = {"DEFAULT": {**WEBPACK_LOADER["DEFAULT"], "CACHE": False}}


# django-debug-toolbar
# ------------------------------------------------------------------------------
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#prerequisites
INSTALLED_APPS += ["debug_toolbar"]
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#middleware
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
# https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config
DEBUG_TOOLBAR_CONFIG = {
    "DISABLE_PANELS": [
        "debug_toolbar.panels.redirects.RedirectsPanel",
        # Disable profiling panel due to an issue with Python 3.12+ (still open
        # as of 2026-08-11, now tracked under django-commons):
        # https://github.com/django-commons/django-debug-toolbar/issues/1875
        "debug_toolbar.panels.profiling.ProfilingPanel",
    ],
    "SHOW_TEMPLATE_CONTEXT": True,
}
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#internal-ips


# The per-request lookup of `node` only makes sense inside compose; elsewhere it would be a failing DNS query.
INTERNAL_IPS = InternalIPs(["127.0.0.1", "10.0.2.2"]) if env("USE_DOCKER", default="no") == "yes" else ["127.0.0.1", "10.0.2.2"]
if env("USE_DOCKER", default="no") == "yes":
    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS += [".".join([*ip.split(".")[:-1], "1"]) for ip in ips]
    # The `node` service proxies :3000 to django, so the toolbar sees its address, not the host's
    # (resolved lazily — see InternalIPs).

# django-extensions
# ------------------------------------------------------------------------------
# https://django-extensions.readthedocs.io/en/latest/installation_instructions.html#configuration
INSTALLED_APPS += ["django_extensions"]

# Hang diagnostics (#403)
# ------------------------------------------------------------------------------
# `just dump-stacks` sends SIGUSR1 to the uvicorn worker; this prints the Python
# stack of every thread to stderr (`just logs`) without stopping the process.
faulthandler.register(signal.SIGUSR1, all_threads=True)
