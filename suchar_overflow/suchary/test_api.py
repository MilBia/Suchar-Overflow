import json
from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Tag
from suchar_overflow.suchary.models import Vote

User = get_user_model()

TAGS_URL = "/api/suchary/tags"
VOTE_URL = "/api/suchary/{pk}/vote"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def vote_url(pk):
    return VOTE_URL.format(pk=pk)


def make_user(username, **kwargs):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
        **kwargs,
    )


# ---------------------------------------------------------------------------
# list_tags
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_tags_empty(client):
    response = client.get(TAGS_URL)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.django_db
def test_list_tags_returns_all(client):
    Tag.objects.create(name="IT", slug="it")
    Tag.objects.create(name="Programowanie", slug="programowanie")

    response = client.get(TAGS_URL)
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 2  # noqa: PLR2004
    slugs = {item["slug"] for item in data}
    assert slugs == {"it", "programowanie"}


@pytest.mark.django_db
def test_list_tags_filtered_by_q(client):
    Tag.objects.create(name="IT", slug="it")
    Tag.objects.create(name="Python", slug="python")
    Tag.objects.create(name="Programowanie", slug="programowanie")

    response = client.get(TAGS_URL, {"q": "it"})
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    # "IT" matches "it" case-insensitively; "Programowanie" does NOT contain "it"
    names = [item["name"] for item in data]
    assert "IT" in names
    assert "Python" not in names


@pytest.mark.django_db
def test_list_tags_q_empty_string_returns_all(client):
    Tag.objects.create(name="IT", slug="it")
    Tag.objects.create(name="Python", slug="python")

    response = client.get(TAGS_URL, {"q": ""})
    assert response.status_code == HTTPStatus.OK
    assert len(response.json()) == 2  # noqa: PLR2004


@pytest.mark.django_db
def test_list_tags_capped_at_ten(client):
    for i in range(15):
        Tag.objects.create(name=f"Tag{i}", slug=f"tag{i}")

    response = client.get(TAGS_URL)
    assert response.status_code == HTTPStatus.OK
    assert len(response.json()) == 10  # noqa: PLR2004


@pytest.mark.django_db
def test_list_tags_schema_fields(client):
    Tag.objects.create(name="IT", slug="it")

    response = client.get(TAGS_URL)
    item = response.json()[0]
    assert "name" in item
    assert "slug" in item


# ---------------------------------------------------------------------------
# vote_suchar — auth requirement
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_requires_authentication(client):
    author = make_user("author")
    suchar = Suchar.objects.create(text="Joke", author=author)

    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ---------------------------------------------------------------------------
# vote_suchar — basic toggling
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_funny_toggle_on(client):
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["funny_count"] == 1
    assert data["dry_count"] == 0
    assert data["user_is_funny"] is True
    assert data["user_is_dry"] is False


@pytest.mark.django_db
def test_vote_funny_toggle_off(client):
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["funny_count"] == 0
    assert data["user_is_funny"] is False
    assert not Vote.objects.filter(user=voter, suchar=suchar).exists()


@pytest.mark.django_db
def test_vote_dry_toggle_on(client):
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["dry_count"] == 1
    assert data["funny_count"] == 0
    assert data["user_is_dry"] is True
    assert data["user_is_funny"] is False


@pytest.mark.django_db
def test_vote_both_flags_then_toggle_off_one_keeps_vote(client):
    """Toggling off one flag while the other stays True must preserve the Vote row."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True, is_dry=True)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["user_is_funny"] is False
    assert data["user_is_dry"] is True
    assert Vote.objects.filter(user=voter, suchar=suchar).exists()


@pytest.mark.django_db
def test_vote_both_flags_off_deletes_vote_row(client):
    """Toggling the last active flag must delete the Vote row entirely."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_funny=False, is_dry=True)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["user_is_funny"] is False
    assert data["user_is_dry"] is False
    assert not Vote.objects.filter(user=voter, suchar=suchar).exists()


# ---------------------------------------------------------------------------
# vote_suchar — counts accuracy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_response_counts_multiple_voters(client):
    author = make_user("author")
    voter1 = make_user("voter1")
    voter2 = make_user("voter2")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter1, is_funny=True)
    Vote.objects.create(suchar=suchar, user=voter2, is_dry=True)

    voter3 = make_user("voter3")
    client.force_login(voter3)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["funny_count"] == 2  # noqa: PLR2004
    assert data["dry_count"] == 1


# ---------------------------------------------------------------------------
# vote_suchar — error cases
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_nonexistent_suchar_returns_404(client):
    voter = make_user("voter")
    client.force_login(voter)

    response = client.post(
        vote_url(99999),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.django_db
def test_vote_invalid_vote_type_returns_422(client):
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "invalid"}),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.django_db
def test_vote_missing_payload_returns_422(client):
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
