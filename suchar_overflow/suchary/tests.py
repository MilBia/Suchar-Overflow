import time
from http import HTTPStatus

import pytest
from django.urls import reverse

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Tag
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
    user = django_user_model.objects.create_user(
        username="voter",
        email="voter@example.com",
        password=password,
    )
    author = django_user_model.objects.create_user(
        username="author",
        email="author@example.com",
        password=password,
    )
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(user)
    url = reverse("suchary:vote", kwargs={"pk": suchar.pk})

    # Vote Funny (toggle on)
    response = client.post(url, {"vote_type": "funny"})
    assert response.status_code == HTTPStatus.FOUND
    assert Vote.objects.filter(user=user, suchar=suchar, is_funny=True).exists()
    assert Vote.objects.filter(user=user, suchar=suchar, is_dry=False).exists()

    # Vote Dry (toggle on independent)
    response = client.post(url, {"vote_type": "dry"})
    assert Vote.objects.filter(
        user=user,
        suchar=suchar,
        is_funny=True,
        is_dry=True,
    ).exists()

    # Vote Funny again (toggle off)
    response = client.post(url, {"vote_type": "funny"})
    # Now funny=False, dry=True
    assert Vote.objects.filter(
        user=user,
        suchar=suchar,
        is_funny=False,
        is_dry=True,
    ).exists()

    # Vote Dry again (toggle off) -> Should delete vote
    response = client.post(url, {"vote_type": "dry"})
    assert not Vote.objects.filter(user=user, suchar=suchar).exists()


@pytest.mark.django_db
def test_suchar_list_sorting(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="author",
        email="author@example.com",
        password="password",  # noqa: S106
    )
    s1 = Suchar.objects.create(text="Older joke", author=user)
    time.sleep(0.01)  # Ensure different created_at
    s2 = Suchar.objects.create(text="Newer joke", author=user)

    url = reverse("suchary:list")

    # Default sort (newest)
    response = client.get(url)
    assert list(response.context["suchary"]) == [s2, s1]

    # Explicit newest
    response = client.get(url, {"sort": "newest"})
    assert list(response.context["suchary"]) == [s2, s1]

    # Top sort (Prioritize funny)
    Vote.objects.create(user=user, suchar=s1, is_funny=True)
    response = client.get(url, {"sort": "top"})
    assert list(response.context["suchary"]) == [s1, s2]


@pytest.mark.django_db
def test_suchar_list_search(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="author",
        email="author@example.com",
        password="password",  # noqa: S106
    )
    tag_it = Tag.objects.create(name="IT", slug="it")
    s1 = Suchar.objects.create(text="Python joke", author=user)
    s1.tags.add(tag_it)
    s2 = Suchar.objects.create(text="General joke", author=user)

    url = reverse("suchary:list")

    # Search by text
    response = client.get(url, {"q": "Python"})
    assert s1 in response.context["suchary"]
    assert s2 not in response.context["suchary"]

    # Search by tag
    response = client.get(url, {"q": "IT"})
    assert s1 in response.context["suchary"]
    assert s2 not in response.context["suchary"]

    # Filter by tag slug
    response = client.get(url, {"tag": "it"})
    assert s1 in response.context["suchary"]
    assert s2 not in response.context["suchary"]


@pytest.mark.django_db
def test_create_suchar_with_tags(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="testuser",
        email="testuser@example.com",
        password="password",  # noqa: S106
    )
    client.force_login(user)

    url = reverse("suchary:add")
    response = client.post(
        url,
        {"text": "A joke", "tags_input": "it, programming suchar"},
    )

    assert response.status_code == HTTPStatus.FOUND
    suchar = Suchar.objects.first()
    assert suchar.tags.count() == 3  # noqa: PLR2004
    assert suchar.tags.filter(slug="it").exists()
    assert suchar.tags.filter(slug="programming").exists()
    assert suchar.tags.filter(slug="suchar").exists()


@pytest.mark.django_db
def test_vote_suchar_edge_cases(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="voter",
        email="voter@example.com",
        password="password",  # noqa: S106
    )
    author = django_user_model.objects.create_user(
        username="author",
        email="author@example.com",
        password="password",  # noqa: S106
    )
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(user)
    url = reverse("suchary:vote", kwargs={"pk": suchar.pk})

    # Invalid vote type
    response = client.post(url, {"vote_type": "invalid"})
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # Missing vote type
    response = client.post(url, {})
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # Non-existent suchar
    url_invalid = reverse("suchary:vote", kwargs={"pk": 9999})
    response = client.post(url_invalid, {"vote_type": "funny"})
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.django_db
def test_pagination_preserves_params(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="author",
        email="author@example.com",
        password="password",  # noqa: S106
    )
    tag_it = Tag.objects.create(name="IT", slug="it")
    # Create 15 suchary to trigger pagination (paginate_by = 10)
    for i in range(15):
        s = Suchar.objects.create(text=f"Joke {i}", author=user)
        s.tags.add(tag_it)

    url = reverse("suchary:list")
    params = {"q": "Joke", "sort": "top", "tag": "it", "author": "author"}
    response = client.get(url, params)

    assert response.status_code == HTTPStatus.OK
    content = response.content.decode()

    # Check if next page link contains all params
    assert "page=2" in content
    assert "q=Joke" in content
    assert "sort=top" in content
    assert "tag=it" in content
    assert "author=author" in content
