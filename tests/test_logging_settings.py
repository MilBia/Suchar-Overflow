"""Regression guard for the RQ loggers (#402, #460, #462).

``award-publication-achievements`` runs every minute (#402), so ``rq.cron``'s per-job
INFO lines would flood the log; ``base.py`` raises that logger to ``WARNING`` and gives
``rq.worker`` the project's console format. ``production.py`` rebuilds
``LOGGING["loggers"]`` and must merge base's entries rather than drop them. Production is reloaded with stubbed env via
``tests.settings_loader.load_production_settings``.
"""

import logging
from typing import Any

import pytest
from django.utils import log

from config.settings import base
from tests.settings_loader import load_production_settings


def test_base_quiets_rq_cron_and_formats_rq_worker() -> None:
    # base.LOGGING is inferred as dict[str, object]; widen it to index into it.
    logging_config: dict[str, Any] = base.LOGGING
    assert logging_config["loggers"]["rq.cron"]["level"] == "WARNING"
    assert logging_config["loggers"]["rq.worker"]["handlers"] == ["rq_console"]
    assert "apscheduler.executors" not in logging_config["loggers"]


def test_production_keeps_rq_loggers_and_its_own_loggers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loggers = load_production_settings(monkeypatch).LOGGING["loggers"]
    assert loggers["rq.cron"]["level"] == "WARNING"
    assert loggers["rq.worker"]["handlers"] == ["rq_console"]
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
def test_production_emails_and_prints_each_django_error_once(
    monkeypatch: pytest.MonkeyPatch,
    logger_name: str,
) -> None:
    logging_config = load_production_settings(monkeypatch).LOGGING
    loggers = logging_config["loggers"]
    reached: list[str] = []
    # Walk the propagation chain the way logging does: this logger, its dotted
    # ancestors, then root, stopping at the first one with propagate=False.
    parts = logger_name.split(".")
    chain = [".".join(parts[:i]) for i in range(len(parts), 0, -1)]
    for name in chain:
        entry = loggers.get(name, {})
        reached += entry.get("handlers", [])
        if not entry.get("propagate", True):
            break
    else:
        reached += logging_config["root"]["handlers"]
    # One email and one console line per error, not two of either.
    assert sorted(reached) == ["console", "mail_admins"]
    # Through the subclass that releases its DB connection (#447).
    assert logging_config["handlers"]["mail_admins"]["class"] == "suchar_overflow.utils.log.AdminEmailHandler"
