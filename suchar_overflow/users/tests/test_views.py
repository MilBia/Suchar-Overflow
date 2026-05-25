from http import HTTPStatus

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.urls import reverse

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote
from suchar_overflow.users.tests.factories import UserFactory


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_update_get(async_client):
    user = await sync_to_async(UserFactory)()
    await async_client.aforce_login(user)
    response = await async_client.get(reverse("users:update"))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_update_post_redirects_to_profile(async_client):
    user = await sync_to_async(UserFactory)()
    await async_client.aforce_login(user)
    response = await async_client.post(reverse("users:update"), {"name": "New Name"})
    assert response.status_code == HTTPStatus.FOUND
    assert response.url == f"/users/{user.username}/"


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_detail_authenticated(async_client):
    target = await sync_to_async(UserFactory)()
    viewer = await sync_to_async(UserFactory)()
    await async_client.aforce_login(viewer)
    response = await async_client.get(
        reverse("users:detail", kwargs={"username": target.username}),
    )
    assert response.status_code == HTTPStatus.OK


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_detail_not_authenticated(async_client):
    target = await sync_to_async(UserFactory)()
    response = await async_client.get(
        reverse("users:detail", kwargs={"username": target.username}),
    )
    login_url = reverse(settings.LOGIN_URL)
    assert response.status_code == HTTPStatus.FOUND
    assert response.url.startswith(login_url)


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_detail_stats_calculation(async_client):
    user = await sync_to_async(UserFactory)()
    s1 = await Suchar.objects.acreate(text="Joke 1", author=user)
    await Vote.objects.acreate(suchar=s1, user=user, is_funny=True)

    other_user = await sync_to_async(UserFactory)()
    s2 = await Suchar.objects.acreate(text="Joke 2", author=user)
    await Vote.objects.acreate(suchar=s2, user=other_user, is_dry=True)

    await async_client.aforce_login(user)
    response = await async_client.get(f"/users/{user.username}/")

    assert response.status_code == HTTPStatus.OK
    expected_score = 2
    assert response.context["object"].total_score == expected_score
    expected_count = 2
    assert response.context["suchar_count"] == expected_count
