"""API conventions of #458: operation URL names, docs switch, 403 handler."""

import importlib
import json
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import URLPattern
from django.urls import clear_url_caches
from django.urls import reverse
from django.utils import translation

from config import api as config_api
from config import urls as config_urls

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Iterator

    from django.test import Client
    from pytest_django.fixtures import Settings as SettingsWrapper


# Ninja's own routes; anything else (a new router, e.g. users) must be listed below.
_NINJA_INTERNAL_NAMES = {"openapi-json", "openapi-view", "api-root"}

_OPERATIONS = [
    ("suchary_list_tags", "/api/suchary/tags"),
    ("suchary_vote_suchar", "/api/suchary/1/vote"),
    ("achievements_list_unseen_achievements", "/api/achievements/unseen"),
    ("achievements_get_pending_toast", "/api/achievements/toast"),
    ("achievements_mark_achievements_seen", "/api/achievements/mark-seen"),
    ("achievements_list_frontend_owned", "/api/achievements/frontend-owned"),
    ("achievements_record_frontend_event", "/api/achievements/frontend-event"),
    ("users_me", "/api/users/me"),
]


@pytest.mark.parametrize(("name", "path"), _OPERATIONS)
def test_every_operation_reverses_under_its_router_tag(name: str, path: str) -> None:
    kwargs = {"suchar_id": 1} if name == "suchary_vote_suchar" else {}
    assert reverse(f"api:{name}", kwargs=kwargs) == path


def test_table_lists_every_operation() -> None:
    """A new endpoint must be added to ``_OPERATIONS`` (and so needs a tagged router)."""
    declared = {
        pattern.name
        for pattern in config_api.api.urls[0]
        if isinstance(pattern, URLPattern) and pattern.name and pattern.name not in _NINJA_INTERNAL_NAMES
    }
    assert declared == {name for name, _ in _OPERATIONS}


@pytest.mark.parametrize(
    ("language", "message"),
    [
        ("pl", "Brak uprawnień do wykonania tej operacji."),
        ("en", "You do not have permission to perform this operation."),
    ],
)
def test_permission_denied_becomes_a_403_with_a_message(language: str, message: str) -> None:
    request = RequestFactory().get("/api/anything")
    with translation.override(language):
        response = config_api.api.on_exception(request, PermissionDenied())
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert json.loads(response.content) == {"message": message}


def _rebuild_api_urls() -> None:
    """Rebuild ``config.api`` / ``config.urls`` for the current settings."""
    importlib.reload(config_api)
    importlib.reload(config_urls)
    clear_url_caches()


@pytest.fixture
def reload_api_urls() -> Iterator[Callable[[], None]]:
    yield _rebuild_api_urls
    _rebuild_api_urls()


@pytest.mark.django_db
@pytest.mark.parametrize(("enabled", "status"), [(True, HTTPStatus.OK), (False, HTTPStatus.NOT_FOUND)])
def test_docs_follow_api_enable_docs(
    client: Client,
    settings: SettingsWrapper,
    reload_api_urls: Callable[[], None],
    enabled: bool,  # noqa: FBT001
    status: HTTPStatus,
) -> None:
    settings.API_ENABLE_DOCS = enabled
    reload_api_urls()
    assert client.get("/api/docs").status_code == status
