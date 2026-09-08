"""Regression guard for issue #353 — HSTS ``preload`` must not ship with a
sub-year ``max-age``.

``production.py`` keeps a cautious 6-day ramp value for
``SECURE_HSTS_SECONDS`` by default. The browser preload list rejects a
``preload`` directive whose ``max-age`` is under ``31536000`` (one year), so
``SECURE_HSTS_PRELOAD`` must default to ``False`` and only turn on via env
(alongside a raised ``DJANGO_SECURE_HSTS_SECONDS``).

The test settings don't define the ``SECURE_HSTS_*`` names at all — they live
only in ``config.settings.production`` — so each test imports that module
directly with the handful of env vars its import needs stubbed (the same set
``compose/production/django/start`` relies on for ``collectstatic``).
"""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

    import pytest

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


def test_default_header_is_preload_list_consistent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``preload`` directive is only ever sent with a >= 1-year max-age."""
    settings = _load_production_settings(monkeypatch)
    if settings.SECURE_HSTS_PRELOAD:
        assert settings.SECURE_HSTS_SECONDS >= _ONE_YEAR
