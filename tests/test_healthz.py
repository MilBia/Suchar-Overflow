"""``/healthz/`` (#457, queue check #460): status codes, no caching, no HTTPS redirect, no leaked connections.

The test settings use LocMem, so the raw Redis ping (``get_redis_connection``)
is patched with a stand-in; what matters is that the view reports it.
"""

import asyncio
import json
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import yaml
from django.core.asgi import get_asgi_application
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.signals import connection_created

from suchar_overflow.utils import views
from tests.asgi_client import asgi_get
from tests.settings_loader import load_production_settings

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.test import AsyncClient

_ROOT = Path(__file__).resolve().parent.parent
_PATCH_REDIS = "suchar_overflow.utils.views.get_redis_connection"


@pytest.fixture
def redis_ok() -> Iterator[MagicMock]:
    with patch(_PATCH_REDIS) as get_connection:
        yield get_connection


@pytest.mark.anyio
@pytest.mark.django_db
async def test_healthy_reports_both_ok(async_client: AsyncClient, redis_ok: MagicMock) -> None:
    response = await async_client.get("/healthz/")
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.content) == {"database": "ok", "cache": "ok", "queue": "ok"}
    redis_ok.return_value.ping.assert_called_once_with()


@pytest.mark.anyio
@pytest.mark.django_db
async def test_response_is_never_cached(async_client: AsyncClient, redis_ok: MagicMock) -> None:  # noqa: ARG001
    response = await async_client.get("/healthz/")
    assert "no-cache" in response["Cache-Control"]


@pytest.mark.anyio
@pytest.mark.django_db
async def test_database_down_is_503_and_not_detailed(
    async_client: AsyncClient,
    redis_ok: MagicMock,  # noqa: ARG001
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch.object(BaseDatabaseWrapper, "ensure_connection", side_effect=RuntimeError("secret dsn")):
        response = await async_client.get("/healthz/")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert json.loads(response.content) == {"database": "error", "cache": "ok", "queue": "ok"}
    assert b"secret dsn" not in response.content
    assert "secret dsn" in caplog.text  # logged server-side instead


@pytest.mark.anyio
@pytest.mark.django_db
async def test_redis_down_is_503(async_client: AsyncClient, redis_ok: MagicMock) -> None:
    redis_ok.return_value.ping.side_effect = ConnectionError("redis is gone")
    response = await async_client.get("/healthz/")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert json.loads(response.content) == {"database": "ok", "cache": "error", "queue": "ok"}


@pytest.mark.anyio
@pytest.mark.django_db
async def test_cache_check_pings_redis_not_the_swallowing_cache_api(async_client: AsyncClient) -> None:
    # No patch: LocMem has no raw Redis connection, so the check must fail. A
    # `cache.get` based check would pass here (and, with IGNORE_EXCEPTIONS, in a real outage).
    response = await async_client.get("/healthz/")
    assert json.loads(response.content)["cache"] == "error"


@pytest.mark.anyio
@pytest.mark.django_db
async def test_queue_down_is_503(async_client: AsyncClient, redis_ok: MagicMock, rq_queue: MagicMock) -> None:  # noqa: ARG001
    rq_queue.connection.ping.side_effect = ConnectionError("queue redis is gone")
    response = await async_client.get("/healthz/")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert json.loads(response.content) == {"database": "ok", "cache": "ok", "queue": "error"}


def test_health_checks_registry_names_the_response_fields() -> None:
    assert set(views.HEALTH_CHECKS) == {"database", "cache", "queue"}


def test_production_does_not_redirect_healthz_to_https(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_production_settings(monkeypatch)
    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.SECURE_REDIRECT_EXEMPT == [r"^healthz/$"]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_repeated_probes_leave_no_open_connections(redis_ok: MagicMock) -> None:  # noqa: ARG001
    opened: list[BaseDatabaseWrapper] = []

    def record(sender: object, connection: BaseDatabaseWrapper, **kwargs: object) -> None:  # noqa: ARG001
        opened.append(connection)

    app = get_asgi_application()
    connection_created.connect(record, weak=False)
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(asgi_get(app, "/healthz/", "") for _ in range(5))),
            timeout=10,
        )
    finally:
        connection_created.disconnect(record)

    assert [status for status, _ in results] == [HTTPStatus.OK] * 5
    assert opened, "the probe never touched the database"
    assert [conn for conn in opened if conn.connection is not None] == []


@pytest.mark.parametrize("compose", ["docker-compose.local.yml", "docker-compose.production.yml"])
def test_django_service_has_a_healthcheck_script(compose: str) -> None:
    django = yaml.safe_load((_ROOT / compose).read_text(encoding="utf-8"))["services"]["django"]
    assert django["healthcheck"]["test"][:2] == ["CMD", "/healthcheck"]


def test_traefik_waits_for_a_healthy_django() -> None:
    services = yaml.safe_load((_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))["services"]
    assert services["traefik"]["depends_on"]["django"]["condition"] == "service_healthy"
