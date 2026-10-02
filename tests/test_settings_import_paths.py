"""Every dotted path in the settings must import (#455).

``MIDDLEWARE``, the template context processors and the ``LOGGING`` handlers,
filters and formatters name their callables as strings. Neither ruff nor mypy
reads them, and some only resolve lazily in production: ``mail_admins`` sits
behind ``DEBUG = False`` and a production-only ``LOGGING``, so a stale path left
by moving a module would first fail on the server. This imports each one for the
test settings and for ``config.settings.production`` (loaded with stubbed env
through ``tests.settings_loader.load_production_settings``).
"""

from typing import Any

import pytest
from django.conf import settings
from django.utils.module_loading import import_string

from tests.settings_loader import load_production_settings

#: dictConfig keys that name a class or factory: ``class`` for handlers,
#: ``()`` for a custom factory (handlers, filters, formatters).
_LOGGING_PATH_KEYS = ("class", "()")


def _dotted_paths(config: Any) -> list[str]:  # noqa: ANN401
    """The dotted paths ``config`` (a settings module or ``django.conf.settings``) names."""
    paths = [*config.MIDDLEWARE, *config.RQ_EXCEPTION_HANDLERS]
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
    production = load_production_settings(monkeypatch)
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
