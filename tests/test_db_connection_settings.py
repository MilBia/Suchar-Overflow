"""Regression guard for issue #430 — no persistent DB connections under ASGI.

The app is served by ASGI (``uvicorn`` locally, gunicorn + ``UvicornWorker`` in
production). Each request runs sync code in its own ``ThreadSensitiveContext``
thread with its own connection, so ``CONN_MAX_AGE > 0`` leaves one idle
connection behind per request until Postgres hits ``max_connections``. Django's
docs: "When using ASGI, persistent connections should be disabled" — reuse must
come from a connection pool (``OPTIONS["pool"]``) instead, if ever. The guard is
``CONN_MAX_AGE == 0`` alone, with no pool exemption: a pool requires 0 anyway
(Django raises only lazily, on first use), and a falsy ``OPTIONS["pool"]``
(``False`` / ``{}``) means no pool, so exempting on the key would hide the leak.

``production.py`` is reloaded with the env vars its import needs stubbed, via
``tests.settings_loader.load_production_settings``.
"""

from typing import Any

# Real import (not TYPE_CHECKING-guarded): kept plain to match every other test
# module; only referenced in annotations.
import pytest  # noqa: TC002
from django.conf import settings as live_settings

from config.settings import base
from tests.settings_loader import load_production_settings


def _no_persistent_connections(db: dict[str, Any]) -> bool:
    return db["CONN_MAX_AGE"] == 0


def test_base_disables_persistent_connections() -> None:
    assert _no_persistent_connections(base.DATABASES["default"])


def test_active_settings_disable_persistent_connections() -> None:
    # config.settings.test (and local/e2e) inherit base.py's value.
    assert _no_persistent_connections(live_settings.DATABASES["default"])


def test_production_disables_persistent_connections_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_production_settings(monkeypatch)
    assert _no_persistent_connections(settings.DATABASES["default"])


def test_production_conn_max_age_stays_overridable_via_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_production_settings(monkeypatch, CONN_MAX_AGE="30")
    assert settings.DATABASES["default"]["CONN_MAX_AGE"] == 30
