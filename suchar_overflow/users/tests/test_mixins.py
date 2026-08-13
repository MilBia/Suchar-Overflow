"""Tests for async auth mixins."""

from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.storage.cookie import CookieStorage
from django.http import HttpResponse
from django.test import AsyncRequestFactory
from django.utils.translation import gettext

from suchar_overflow.users.mixins import AsyncLoginRequiredMixin
from suchar_overflow.users.mixins import AsyncUserPassesTestMixin

User = get_user_model()


class _SimpleAsyncView(AsyncLoginRequiredMixin):
    async def get(self, request, *args, **kwargs):
        return HttpResponse("ok")


class _PassesTestView(AsyncUserPassesTestMixin):
    async def test_func(self):  # type: ignore[override]
        return self.request.user.username == "allowed"

    async def get(self, request, *args, **kwargs):
        return HttpResponse("ok")


class _NoTestFuncView(AsyncUserPassesTestMixin):
    async def get(self, request, *args, **kwargs):
        return HttpResponse("ok")


@pytest.mark.anyio
@pytest.mark.django_db
async def test_async_login_required_redirects_anonymous():
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = type("Anon", (), {"is_authenticated": False})()
    view = _SimpleAsyncView.as_view()
    # View.as_view() is typed as a sync-returning Callable; at runtime it
    # returns a coroutine for async view handlers (same stub gap as
    # AsyncLoginRequiredMixin.dispatch — see users/mixins.py).
    response = await view(request)  # type: ignore[misc]
    assert response.status_code == HTTPStatus.FOUND


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_async_login_required_allows_authenticated(django_user_model):
    user = await django_user_model.objects.acreate_user(
        username="u",
        password="pw",  # noqa: S106
    )
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = user
    view = _SimpleAsyncView.as_view()
    response = await view(request)  # type: ignore[misc]
    assert response.status_code == HTTPStatus.OK


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_async_user_passes_test_blocks_failing_user(django_user_model):
    user = await django_user_model.objects.acreate_user(
        username="blocked",
        password="pw",  # noqa: S106
    )
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = user
    request._messages = CookieStorage(request)  # type: ignore[attr-defined]  # noqa: SLF001
    view = _PassesTestView.as_view()
    response = await view(request)  # type: ignore[misc]
    assert response.status_code == HTTPStatus.FOUND
    messages = list(get_messages(request))
    assert len(messages) == 1
    assert str(messages[0]) == gettext("You don't have permission to do that.")


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_async_user_passes_test_allows_passing_user(django_user_model):
    user = await django_user_model.objects.acreate_user(
        username="allowed",
        password="pw",  # noqa: S106
    )
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = user
    view = _PassesTestView.as_view()
    response = await view(request)  # type: ignore[misc]
    assert response.status_code == HTTPStatus.OK


@pytest.mark.anyio
async def test_async_user_passes_test_default_test_func_raises():
    view = _NoTestFuncView()
    with pytest.raises(NotImplementedError, match="_NoTestFuncView"):
        await view.test_func()
