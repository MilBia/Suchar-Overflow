"""Bearer-token API authentication (#459)."""

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.test import Client
from django.urls import reverse

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote
from suchar_overflow.users.models import AuthToken

if TYPE_CHECKING:
    from suchar_overflow.users.models import User

ME = "/api/users/me"


@pytest.mark.django_db
def test_me_with_a_token(api_client: Client, user: User) -> None:
    response = api_client.get(ME)
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.content) == {"username": user.username}


@pytest.mark.django_db
def test_me_with_a_session(user: User) -> None:
    client = Client()
    client.force_login(user)
    response = client.get(ME)
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.content) == {"username": user.username}


@pytest.mark.django_db
def test_me_anonymous_is_401() -> None:
    assert Client().get(ME).status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_me_with_a_wrong_token_is_401(api_token: str) -> None:  # noqa: ARG001
    client = Client(headers={"Authorization": "Bearer not-the-token"})
    assert client.get(ME).status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_a_token_of_an_inactive_user_is_rejected(api_client: Client, user: User) -> None:
    user.is_active = False
    user.save()
    assert api_client.get(ME).status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_only_the_hash_is_stored(user: User, api_token: str) -> None:
    stored = AuthToken.objects.get(user=user)
    assert stored.token_hash == AuthToken.hash_token(api_token)
    assert api_token not in stored.token_hash
    assert len(stored.token_hash) == 64


@pytest.mark.django_db
def test_issue_replaces_the_previous_token(user: User, api_token: str) -> None:
    _token, new = AuthToken.issue(user)
    assert new != api_token
    assert AuthToken.objects.filter(user=user).count() == 1
    assert Client(headers={"Authorization": f"Bearer {api_token}"}).get(ME).status_code == HTTPStatus.UNAUTHORIZED
    assert Client(headers={"Authorization": f"Bearer {new}"}).get(ME).status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_anonymous_tag_autocomplete_stays_public() -> None:
    assert Client().get(reverse("api:suchary_list_tags")).status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_vote_with_a_token_needs_no_csrf(api_client: Client, user: User) -> None:
    suchar = Suchar.objects.create(text="joke", author=user)
    response = api_client.post(
        reverse("api:suchary_vote_suchar", kwargs={"suchar_id": suchar.pk}),
        data={"vote_type": "funny"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK
    assert Vote.objects.filter(suchar=suchar, user=user, is_funny=True).exists()


@pytest.mark.django_db
def test_vote_with_a_session_still_requires_csrf(user: User) -> None:
    suchar = Suchar.objects.create(text="joke", author=user)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    response = client.post(
        reverse("api:suchary_vote_suchar", kwargs={"suchar_id": suchar.pk}),
        data={"vote_type": "funny"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert not Vote.objects.exists()


@pytest.mark.django_db
def test_achievement_endpoints_accept_a_token(api_client: Client) -> None:
    assert api_client.get("/api/achievements/frontend-owned").status_code == HTTPStatus.OK


# --- admin -------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_issues_a_token_and_shows_it_once(admin_client: Client, user: User) -> None:
    response = admin_client.post(reverse("admin:users_authtoken_add"), {"user": user.pk}, follow=True)
    assert response.status_code == HTTPStatus.OK
    stored = AuthToken.objects.get(user=user)
    message = next(str(m) for m in response.context["messages"] if "shown only once" in str(m) or "tylko raz" in str(m))
    raw = message.rsplit(" ", 1)[-1]
    assert AuthToken.hash_token(raw) == stored.token_hash
    assert Client(headers={"Authorization": f"Bearer {raw}"}).get(ME).status_code == HTTPStatus.OK
    # Not shown again on the list or change page.
    change = admin_client.get(reverse("admin:users_authtoken_change", args=[stored.pk]))
    assert raw.encode() not in change.content
    assert stored.token_hash.encode() not in change.content


@pytest.mark.django_db
def test_admin_regenerate_action_invalidates_the_old_token(admin_client: Client, user: User, api_token: str) -> None:
    stored = AuthToken.objects.get(user=user)
    admin_client.post(
        reverse("admin:users_authtoken_changelist"),
        {"action": "regenerate", "_selected_action": [stored.pk]},
        follow=True,
    )
    assert Client(headers={"Authorization": f"Bearer {api_token}"}).get(ME).status_code == HTTPStatus.UNAUTHORIZED
