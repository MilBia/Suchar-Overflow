"""Static files are served by nginx, not by Django (#463).

- No sync-only class in production's ``MIDDLEWARE``: one would run in the request's
  ``ThreadSensitiveContext`` thread and bring back the #426 disconnect deadlock
  risk (``test_asgiref_disconnect_deadlock.py`` pins the asgiref floor).
- Production's storage is the plain manifest storage and WhiteNoise is gone.
- The nginx config and the compose/Traefik wiring (checked as files — that the
  stack serves them is verified by hand with ``just prod-up``).
- Locally ``config/asgi.py`` serves ``/static/`` only while ``DEBUG`` is on.
"""

import importlib
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.utils.module_loading import import_string

from tests.settings_loader import load_production_settings

if TYPE_CHECKING:
    from pytest_django.fixtures import Settings as SettingsWrapper

_ROOT = Path(__file__).resolve().parent.parent
_NGINX_CONF = (_ROOT / "compose/production/nginx/default.conf").read_text(encoding="utf-8")


class _OldStyleMiddleware:
    """Declares neither flag, like WhiteNoiseMiddleware did."""


def _is_sync_only_class(cls: type) -> bool:
    # Django's own defaults when a class declares neither flag (load_middleware).
    return getattr(cls, "sync_capable", True) and not getattr(cls, "async_capable", False)


def _is_sync_only(path: str) -> bool:
    return _is_sync_only_class(import_string(path))


def test_sync_only_detector_flags_an_old_style_middleware() -> None:
    assert _is_sync_only_class(_OldStyleMiddleware) is True
    assert _is_sync_only("django.middleware.security.SecurityMiddleware") is False


def test_production_middleware_chain_has_no_sync_only_class(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = load_production_settings(monkeypatch).MIDDLEWARE
    assert middleware
    assert [path for path in middleware if _is_sync_only(path)] == []


def test_production_serves_static_through_the_manifest_storage_only(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_production_settings(monkeypatch)
    assert (
        settings.STORAGES["staticfiles"]["BACKEND"] == "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
    )
    assert not any("whitenoise" in path.lower() for path in settings.MIDDLEWARE)
    assert not any("whitenoise" in app.lower() for app in settings.INSTALLED_APPS)


def test_whitenoise_is_not_a_dependency() -> None:
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "whitenoise" not in pyproject.lower()


def test_nginx_caches_hashed_static_forever_and_gzips() -> None:
    assert "location /static/" in _NGINX_CONF
    assert "gzip on;" in _NGINX_CONF
    assert "gzip_static on;" in _NGINX_CONF
    assert "immutable" in _NGINX_CONF
    # The hashed-name regex is quoted (a bare `{12}` opens a block) and matches the manifest's names.
    match = re.search(r'location ~ "(\^/static/[^"]+)"', _NGINX_CONF)
    assert match, "hashed-name location must use a quoted regex"
    pattern = re.sub(r"\(\?<\w+>", "(", match.group(1))
    # webpack's `[name].[contenthash]` names (hashDigestLength 12) and the manifest storage's.
    assert re.match(pattern, "/static/webpack_bundles/css/project.0123456789ab.css")
    assert re.match(pattern, "/static/js/project.0123456789ab.js")
    assert not re.match(pattern, "/static/js/project.js")


def test_static_volume_is_rw_for_django_and_ro_for_nginx() -> None:
    compose = yaml.safe_load((_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    assert "production_django_static" in compose["volumes"]
    django_volumes = compose["services"]["django"]["volumes"]
    nginx_volumes = compose["services"]["nginx"]["volumes"]
    assert "production_django_static:/app/staticfiles" in django_volumes
    assert "production_django_static:/usr/share/nginx/static:ro" in nginx_volumes


def test_traefik_routes_static_and_media_to_nginx() -> None:
    traefik = yaml.safe_load((_ROOT / "compose/production/traefik/traefik.yml").read_text(encoding="utf-8"))
    routers = traefik["http"]["routers"]
    assert "PathPrefix(`/static/`)" in routers["web-static-router"]["rule"]
    assert "PathPrefix(`/media/`)" in routers["web-media-router"]["rule"]
    assert routers["web-static-router"]["service"] == routers["web-media-router"]["service"] == "nginx"
    assert traefik["http"]["services"]["nginx"]["loadBalancer"]["servers"] == [{"url": "http://nginx:80"}]


@pytest.mark.parametrize(("debug", "wrapped"), [(True, True), (False, False)])
def test_asgi_serves_static_only_in_debug(
    settings: SettingsWrapper,
    monkeypatch: pytest.MonkeyPatch,
    debug: bool,  # noqa: FBT001
    wrapped: bool,  # noqa: FBT001
) -> None:
    settings.DEBUG = debug
    monkeypatch.delitem(sys.modules, "config.asgi", raising=False)
    module = importlib.import_module("config.asgi")
    try:
        assert isinstance(module.application, ASGIStaticFilesHandler) is wrapped
    finally:
        sys.modules.pop("config.asgi", None)


def test_production_start_clears_the_static_volume_and_has_no_compress_step() -> None:
    start = (_ROOT / "compose/production/django/start").read_text(encoding="utf-8")
    assert "manage.py collectstatic --noinput --clear" in start
    # django-compressor is gone (#469): the bundles are built into the image, not at start-up.
    assert "manage.py compress" not in start
