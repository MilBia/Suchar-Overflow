"""Regression guard for issue #402 — apscheduler's per-job INFO logging stays quiet.

``award-publication-achievements`` runs every minute (#402), so apscheduler's
INFO "Running job" / "executed successfully" pair would add ~2880 log lines a
day. ``base.py`` raises the ``apscheduler.executors`` logger to ``WARNING``;
``production.py`` rebuilds ``LOGGING["loggers"]`` and must merge base's entry
rather than drop it. Production is imported directly with stubbed env, the same
way as ``tests/test_hsts_settings.py``.
"""

import importlib
import logging

# Real import (not TYPE_CHECKING-guarded): kept plain to match every other test
# module; ModuleType and pytest are only referenced in annotations here.
from types import ModuleType  # noqa: TC003
from typing import Any

import pytest
from django.utils import log

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
    assert loggers["django.request"]["level"] == "ERROR"
    assert "django.security.DisallowedHost" in loggers


def test_base_drops_djangos_default_django_handlers() -> None:
    # Django's DEFAULT_LOGGING attaches a stock AdminEmailHandler to "django"
    # and disable_existing_loggers=False would keep it: a second email for every
    # error, sent from a handler that strands executor-thread connections (#447).
    logging_config: dict[str, Any] = base.LOGGING
    assert logging_config["loggers"]["django"]["handlers"] == []
    live = logging.getLogger("django").handlers
    assert not [h for h in live if isinstance(h, log.AdminEmailHandler)]


@pytest.mark.parametrize(
    "logger_name",
    ["django.request", "django.security.DisallowedHost", "django.security.csrf"],
)
def test_production_emails_each_django_error_once(
    monkeypatch: pytest.MonkeyPatch,
    logger_name: str,
) -> None:
    logging_config = _load_production_settings(monkeypatch).LOGGING
    loggers = logging_config["loggers"]
    mail_handlers: list[str] = []
    # Walk the propagation chain the way logging does: this logger, its dotted
    # ancestors, then root, stopping at the first one with propagate=False.
    parts = logger_name.split(".")
    chain = [".".join(parts[:i]) for i in range(len(parts), 0, -1)]
    for name in chain:
        entry = loggers.get(name, {})
        mail_handlers += [h for h in entry.get("handlers", []) if h == "mail_admins"]
        if not entry.get("propagate", True):
            break
    else:
        mail_handlers += [
            h for h in logging_config["root"]["handlers"] if h == "mail_admins"
        ]
    assert mail_handlers == ["mail_admins"]
    # Through the subclass that releases its DB connection (#447).
    assert (
        logging_config["handlers"]["mail_admins"]["class"]
        == "suchar_overflow.log.AdminEmailHandler"
    )
