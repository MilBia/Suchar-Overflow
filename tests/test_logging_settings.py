"""Regression guard for issue #402 — apscheduler's per-job INFO logging stays quiet.

``award-publication-achievements`` runs every minute (#402), so apscheduler's
INFO "Running job" / "executed successfully" pair would add ~2880 log lines a
day. ``base.py`` raises the ``apscheduler.executors`` logger to ``WARNING``;
``production.py`` rebuilds ``LOGGING["loggers"]`` and must merge base's entry
rather than drop it. Production is imported directly with stubbed env, the same
way as ``tests/test_hsts_settings.py``.
"""

import importlib

# Real import (not TYPE_CHECKING-guarded): kept plain to match every other test
# module; ModuleType and pytest are only referenced in annotations here.
from types import ModuleType  # noqa: TC003
from typing import Any

import pytest  # noqa: TC002

from config.settings import base

_REQUIRED_ENV = {
    "DJANGO_SECRET_KEY": "dummy-secret-key-for-tests",
    "DJANGO_ADMIN_URL": "admin/",
    "DJANGO_ALLOWED_HOSTS": "example.com",
    "DATABASE_URL": "postgres://user:pass@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
}


def _load_production_settings(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for key, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    # production.py mutates base.DATABASES["default"] in place (CONN_MAX_AGE);
    # restore it on teardown so the reload doesn't leak into live settings.
    monkeypatch.setitem(base.DATABASES["default"], "CONN_MAX_AGE", 0)
    module = importlib.import_module("config.settings.production")
    return importlib.reload(module)


def test_base_quiets_apscheduler_executors() -> None:
    # base.LOGGING is inferred as dict[str, object]; widen it to index into it.
    logging_config: dict[str, Any] = base.LOGGING
    assert logging_config["loggers"]["apscheduler.executors"]["level"] == "WARNING"


def test_production_keeps_apscheduler_quiet_and_its_own_loggers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loggers = _load_production_settings(monkeypatch).LOGGING["loggers"]
    assert loggers["apscheduler.executors"]["level"] == "WARNING"
    assert loggers["django.request"]["handlers"] == ["mail_admins"]
    assert "django.security.DisallowedHost" in loggers
