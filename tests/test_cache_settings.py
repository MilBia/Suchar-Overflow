"""Regression guard for issue #454 — one CACHES definition, Redis outside tests.

``CACHES`` lives only in ``base.py`` (django-redis, ``IGNORE_EXCEPTIONS``,
``rediss://`` support). ``production.py`` and ``local.py`` must not redefine it —
local used to swap in LocMem, which hid shared-cache behaviour (SSE flags, the
toast latch) and lost it on every dev-server restart. Only ``test.py`` uses LocMem.

``local.py`` is checked statically: importing it here would run its
``MIDDLEWARE +=`` / ``TEMPLATES[0][...] =`` against the live ``base`` objects the
test settings share, and register a ``faulthandler`` signal.
"""

import ast
from pathlib import Path

import pytest
from django.conf import settings

from config.settings import base
from tests.settings_loader import MINIMAL_ENV
from tests.settings_loader import load_base_settings
from tests.settings_loader import load_production_settings

SETTINGS_DIR = Path(base.__file__).resolve().parent


def _assigned_names(path: Path) -> set[str]:
    """Top-level names a settings module assigns, including ``X[...] = ...`` targets."""
    names: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        else:
            continue
        for target in targets:
            base_target = target
            while isinstance(base_target, ast.Subscript):
                base_target = base_target.value
            if isinstance(base_target, ast.Name):
                names.add(base_target.id)
    return names


@pytest.mark.parametrize(
    ("redis_url", "pool_kwargs"),
    [
        ("redis://redis:6379/0", {}),
        ("rediss://:secret@redis.example.com:6380/0", {"ssl_cert_reqs": None}),
    ],
)
def test_base_caches_use_redis_and_ignore_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    redis_url: str,
    pool_kwargs: dict[str, None],
) -> None:
    loaded = load_base_settings(monkeypatch, tmp_path, {**MINIMAL_ENV, "REDIS_URL": redis_url})
    default = loaded.CACHES["default"]
    assert default["BACKEND"] == "django_redis.cache.RedisCache"
    assert default["LOCATION"] == redis_url
    assert default["OPTIONS"]["IGNORE_EXCEPTIONS"] is True
    assert default["OPTIONS"]["CONNECTION_POOL_KWARGS"] == pool_kwargs


@pytest.mark.parametrize("module", ["local.py", "production.py"])
def test_local_and_production_do_not_redefine_caches(module: str) -> None:
    assert "CACHES" not in _assigned_names(SETTINGS_DIR / module)


def test_production_inherits_base_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    production = load_production_settings(monkeypatch)
    assert production.CACHES is base.CACHES


def test_test_settings_use_locmem() -> None:
    assert settings.CACHES["default"]["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache"


def test_local_template_loaders_are_not_cached() -> None:
    """uvicorn --reload never resets the cached loader, so local must not use it."""
    source = (SETTINGS_DIR / "local.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments = {
        ast.unparse(node.targets[0]): node.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Subscript)
    }
    # ast.unparse normalises quoting, so look targets up in that same form.
    app_dirs = assignments[ast.unparse(ast.parse('TEMPLATES[0]["APP_DIRS"]', mode="eval").body)]
    assert isinstance(app_dirs, ast.Constant)
    assert app_dirs.value is False
    loaders_target = ast.unparse(ast.parse('TEMPLATES[0]["OPTIONS"]["loaders"]', mode="eval").body)
    loaders = ast.literal_eval(assignments[loaders_target])
    assert loaders == [
        "django.template.loaders.filesystem.Loader",
        "django.template.loaders.app_directories.Loader",
    ]
