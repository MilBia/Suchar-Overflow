"""Regression guard for issue #353 — HSTS ``preload`` must not ship with a
sub-year ``max-age``.

``production.py`` keeps a cautious 6-day ramp value for
``SECURE_HSTS_SECONDS`` by default. The browser preload list rejects a
``preload`` directive whose ``max-age`` is under ``31536000`` (one year), so
``SECURE_HSTS_PRELOAD`` defaults to ``False`` and only turns on via env
(alongside a raised ``DJANGO_SECURE_HSTS_SECONDS``); a mismatched pair raises
``ImproperlyConfigured`` at settings load.

The test settings don't define the ``SECURE_HSTS_*`` names at all — they live
only in ``config.settings.production`` — so each test imports that module
directly with the handful of env vars its import needs stubbed (the same set
``compose/production/django/start`` relies on for ``collectstatic``).
"""

import importlib

# Real import (not TYPE_CHECKING-guarded): kept plain to match every other test
# module; only referenced in _load_production_settings' return annotation.
from types import ModuleType  # noqa: TC003

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings import base

_ONE_YEAR = 31536000
_RAMP_DEFAULT = 518400

_REQUIRED_ENV = {
    "DJANGO_SECRET_KEY": "dummy-secret-key-for-tests",
    "DJANGO_ADMIN_URL": "admin/",
    "DJANGO_ALLOWED_HOSTS": "example.com",
    "DATABASE_URL": "postgres://user:pass@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
}


def _load_production_settings(
    monkeypatch: pytest.MonkeyPatch,
    **overrides: str,
) -> ModuleType:
    for key, value in {**_REQUIRED_ENV, **overrides}.items():
        monkeypatch.setenv(key, value)
    # production.py mutates the shared base.DATABASES["default"] dict in place
    # (CONN_MAX_AGE); reloading it below would otherwise leak that into the
    # live test settings for the rest of the session. monkeypatch.setitem
    # records the pre-reload state and restores it on teardown.
    monkeypatch.setitem(base.DATABASES["default"], "CONN_MAX_AGE", 0)
    module = importlib.import_module("config.settings.production")
    return importlib.reload(module)


def test_hsts_preload_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _load_production_settings(monkeypatch)
    assert settings.SECURE_HSTS_PRELOAD is False


def test_hsts_seconds_keeps_the_ramp_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_production_settings(monkeypatch)
    assert settings.SECURE_HSTS_SECONDS == _RAMP_DEFAULT


def test_hsts_preload_and_max_age_are_opt_in_via_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_production_settings(
        monkeypatch,
        DJANGO_SECURE_HSTS_PRELOAD="True",
        DJANGO_SECURE_HSTS_SECONDS=str(_ONE_YEAR),
    )
    assert settings.SECURE_HSTS_PRELOAD is True
    assert settings.SECURE_HSTS_SECONDS == _ONE_YEAR


def test_preload_without_a_one_year_max_age_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabling preload without also raising max-age — the exact inconsistent
    header issue #353 is about — fails fast at settings load instead of being
    served."""
    with pytest.raises(ImproperlyConfigured, match="SECURE_HSTS_PRELOAD"):
        _load_production_settings(
            monkeypatch,
            DJANGO_SECURE_HSTS_PRELOAD="True",
            # DJANGO_SECURE_HSTS_SECONDS left at the 6-day ramp default.
        )
    # The failed reload leaves config.settings.production half-initialised in
    # sys.modules, which is harmless: nothing else in the suite imports it, and
    # the next _load_production_settings() call re-executes the whole module.
