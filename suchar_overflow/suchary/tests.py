from http import HTTPStatus

import pytest
from django.urls import reverse

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote


@pytest.mark.django_db
def test_suchar_list_view(client):
    url = reverse("suchary:list")
    response = client.get(url)
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_create_suchar(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="testuser",
        password="password",  # noqa: S106
    )
    client.force_login(user)

    url = reverse("suchary:add")
    response = client.post(url, {"text": "A dry joke"})

    assert response.status_code == HTTPStatus.FOUND
    assert Suchar.objects.count() == 1
    assert Suchar.objects.first().text == "A dry joke"


@pytest.mark.django_db
def test_vote_suchar(client, django_user_model):
    password = "password"  # noqa: S105
    user = django_user_model.objects.create_user(username="voter", password=password)
    author = django_user_model.objects.create_user(
        username="author",
        password=password,
    )
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(user)
    url = reverse("suchary:vote", kwargs={"pk": suchar.pk})

    # Vote UP
    response = client.post(url, {"value": "1"})
    assert response.status_code == HTTPStatus.FOUND
    assert Vote.objects.filter(user=user, suchar=suchar, value=1).exists()

    # Vote DOWN (change vote)
    response = client.post(url, {"value": "-1"})
    assert Vote.objects.filter(user=user, suchar=suchar, value=-1).exists()

    # Vote DOWN again (toggle off)
    response = client.post(url, {"value": "-1"})
    assert not Vote.objects.filter(user=user, suchar=suchar).exists()
