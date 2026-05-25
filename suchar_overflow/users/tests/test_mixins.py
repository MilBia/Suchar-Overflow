"""Tests for async auth mixins."""

from http import HTTPStatus

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import AsyncRequestFactory
from django.views import View

from suchar_overflow.users.mixins import AsyncLoginRequiredMixin
from suchar_overflow.users.mixins import AsyncUserPassesTestMixin

User = get_user_model()


class _SimpleAsyncView(AsyncLoginRequiredMixin, View):
    login_url = "/accounts/login/"

    async def get(self, request, *args, **kwargs):
        return HttpResponse("ok")


class _PassesTestView(AsyncUserPassesTestMixin, View):
    login_url = "/accounts/login/"

    async def test_func(self):
        return self.request.user.username == "allowed"

    async def get(self, request, *args, **kwargs):
        return HttpResponse("ok")


@pytest.mark.django_db
def test_async_login_required_redirects_anonymous():
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = type("Anon", (), {"is_authenticated": False})()
    view = _SimpleAsyncView.as_view()
    response = async_to_sync(view)(request)
    assert response.status_code == HTTPStatus.FOUND


@pytest.mark.django_db
def test_async_login_required_allows_authenticated(django_user_model):
    user = User.objects.create_user(
        username="u",
        password="pw",  # noqa: S106
    )
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = user
    view = _SimpleAsyncView.as_view()
    response = async_to_sync(view)(request)
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_async_user_passes_test_blocks_failing_user(django_user_model):
    user = User.objects.create_user(
        username="blocked",
        password="pw",  # noqa: S106
    )
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = user
    view = _PassesTestView.as_view()
    response = async_to_sync(view)(request)
    assert response.status_code == HTTPStatus.FOUND  # redirect to login


@pytest.mark.django_db
def test_async_user_passes_test_allows_passing_user(django_user_model):
    user = User.objects.create_user(
        username="allowed",
        password="pw",  # noqa: S106
    )
    arf = AsyncRequestFactory()
    request = arf.get("/fake-path/")
    request.user = user
    view = _PassesTestView.as_view()
    response = async_to_sync(view)(request)
    assert response.status_code == HTTPStatus.OK
