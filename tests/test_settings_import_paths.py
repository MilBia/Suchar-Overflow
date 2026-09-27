"""Every dotted path in the settings must import (#455).

``MIDDLEWARE``, the template context processors and the ``LOGGING`` handlers,
filters and formatters name their callables as strings. Neither ruff nor mypy
reads them, and some only resolve lazily in production: ``mail_admins`` sits
behind ``DEBUG = False`` and a production-only ``LOGGING``, so a stale path left
by moving a module would first fail on the server. This imports each one for the
test settings and for ``config.settings.production`` (loaded with stubbed env,
the same way as ``tests/test_hsts_settings.py``).
"""

import importlib

# Real import (not TYPE_CHECKING-guarded): kept plain to match every other test
# module; ModuleType is only referenced in an annotation here.
from types import ModuleType  # noqa: TC003
from typing import Any

import pytest
from django.conf import settings
from django.utils.module_loading import import_string

from config.settings import base

_REQUIRED_ENV = {
    "DJANGO_SECRET_KEY": "dummy-secret-key-for-tests",
    "DJANGO_ADMIN_URL": "admin/",
    "DJANGO_ALLOWED_HOSTS": "example.com",
    "DATABASE_URL": "postgres://user:pass@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
}

#: dictConfig keys that name a class or factory: ``class`` for handlers,
#: ``()`` for a custom factory (handlers, filters, formatters).
_LOGGING_PATH_KEYS = ("class", "()")


def _load_production_settings(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for key, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    # production.py mutates base.DATABASES["default"] in place (CONN_MAX_AGE);
    # restore it on teardown so the reload doesn't leak into live settings.
    monkeypatch.setitem(base.DATABASES["default"], "CONN_MAX_AGE", 0)
    module = importlib.import_module("config.settings.production")
    return importlib.reload(module)


def _dotted_paths(config: Any) -> list[str]:  # noqa: ANN401
    """The dotted paths ``config`` (a settings module or ``django.conf.settings``) names."""
    paths = list(config.MIDDLEWARE)
    for engine in config.TEMPLATES:
        paths += engine.get("OPTIONS", {}).get("context_processors", [])
    logging_config = config.LOGGING
    for section in ("handlers", "filters", "formatters"):
        for entry in logging_config.get(section, {}).values():
            paths += [entry[key] for key in _LOGGING_PATH_KEYS if key in entry]
    return paths


def _assert_all_import(paths: list[str]) -> None:
    failures = []
    for path in paths:
        try:
            import_string(path)
        except ImportError as exc:
            failures.append(f"{path}: {exc}")
    assert failures == []


def test_test_settings_paths_import() -> None:
    paths = _dotted_paths(settings)
    # Not vacuous: middleware, context processors and LOGGING are all collected.
    assert set(settings.MIDDLEWARE) <= set(paths)
    # django-stubs types TEMPLATES/LOGGING loosely; widen them to index into them.
    templates: list[dict[str, Any]] = settings.TEMPLATES
    logging_config: dict[str, Any] = settings.LOGGING
    assert templates[0]["OPTIONS"]["context_processors"][0] in paths
    assert logging_config["handlers"]["console"]["class"] in paths
    _assert_all_import(paths)


def test_production_settings_paths_import(monkeypatch: pytest.MonkeyPatch) -> None:
    production = _load_production_settings(monkeypatch)
    paths = _dotted_paths(production)
    # Not vacuous: the production-only handler and filter are collected. Read
    # from the settings, not spelled out, so a typo there still reaches
    # import_string below (test_logging_settings pins the class name itself).
    assert production.LOGGING["handlers"]["mail_admins"]["class"] in paths
    assert production.LOGGING["filters"]["require_debug_false"]["()"] in paths
    _assert_all_import(paths)


def test_a_stale_path_is_reported() -> None:
    # The check itself must fail on the kind of path a module move leaves behind.
    with pytest.raises(AssertionError):
        _assert_all_import(["suchar_overflow.utils.no_such_module.user_timezone_middleware"])
