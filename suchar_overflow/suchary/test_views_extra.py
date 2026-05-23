"""Extra view tests: SucharListView filtering and SucharUpdateView permissions."""

from datetime import timedelta
from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Tag
from suchar_overflow.suchary.models import Vote


def make_user(username):
    user_model = get_user_model()
    return user_model.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


LIST_URL = "suchary:list"
ADD_URL = "suchary:add"


# ===========================================================================
# SucharListView — unpublished posts hidden
# ===========================================================================


@pytest.mark.django_db
def test_list_hides_scheduled_suchar(client):
    user = make_user("author")
    future = timezone.now() + timedelta(days=1)
    Suchar.objects.create(text="Future joke", author=user, published_at=future)

    response = client.get(reverse(LIST_URL))
    assert response.status_code == HTTPStatus.OK
    assert "Future joke" not in response.content.decode()


@pytest.mark.django_db
def test_list_shows_published_suchar(client):
    user = make_user("author")
    Suchar.objects.create(text="Past joke", author=user)

    response = client.get(reverse(LIST_URL))
    assert "Past joke" in response.content.decode()


# ===========================================================================
# SucharListView — authenticated user vote annotations
# ===========================================================================


@pytest.mark.django_db
def test_list_annotates_user_is_funny_for_authenticated(client, django_user_model):
    author = django_user_model.objects.create_user(
        username="auth_author",
        email="aa@example.com",
        password="pw",  # noqa: S106
    )
    voter = django_user_model.objects.create_user(
        username="auth_voter",
        email="av@example.com",
        password="pw",  # noqa: S106
    )
    suchar = Suchar.objects.create(text="annotated joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    client.force_login(voter)
    response = client.get(reverse(LIST_URL))
    suchary = list(response.context["suchary"])
    assert len(suchary) == 1
    assert suchary[0].user_is_funny is True
    assert suchary[0].user_is_dry is False


@pytest.mark.django_db
def test_list_annotates_user_is_dry_for_authenticated(client, django_user_model):
    author = django_user_model.objects.create_user(
        username="dry_author",
        email="da@example.com",
        password="pw",  # noqa: S106
    )
    voter = django_user_model.objects.create_user(
        username="dry_voter",
        email="dv@example.com",
        password="pw",  # noqa: S106
    )
    suchar = Suchar.objects.create(text="dry annotated joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_dry=True)

    client.force_login(voter)
    response = client.get(reverse(LIST_URL))
    suchary = list(response.context["suchary"])
    assert suchary[0].user_is_dry is True
    assert suchary[0].user_is_funny is False


@pytest.mark.django_db
def test_list_no_user_vote_annotations_for_anonymous(client, django_user_model):
    author = django_user_model.objects.create_user(
        username="anon_author",
        email="ano@example.com",
        password="pw",  # noqa: S106
    )
    Suchar.objects.create(text="anon joke", author=author)

    response = client.get(reverse(LIST_URL))
    suchary = list(response.context["suchary"])
    assert len(suchary) == 1
    # Anonymous users must NOT have user_is_funny / user_is_dry annotations
    assert not hasattr(suchary[0], "user_is_funny") or suchary[0].user_is_funny is None


# ===========================================================================
# SucharListView — combined text + tag filter
# ===========================================================================


@pytest.mark.django_db
def test_list_combined_text_and_tag_filter(client, django_user_model):
    author = django_user_model.objects.create_user(
        username="combo_auth",
        email="combo@example.com",
        password="pw",  # noqa: S106
    )
    tag_py = Tag.objects.create(name="Python", slug="python")
    s_match = Suchar.objects.create(text="Python joke", author=author)
    s_match.tags.add(tag_py)
    s_no_tag = Suchar.objects.create(text="Python but no tag", author=author)
    s_other_tag = Suchar.objects.create(text="Other joke", author=author)
    s_other_tag.tags.add(tag_py)

    response = client.get(reverse(LIST_URL), {"q": "Python", "tag": "python"})
    suchary = list(response.context["suchary"])
    # s_match: text and tag both match
    assert s_match in suchary
    # s_no_tag: text matches but has no tag — excluded by tag filter
    assert s_no_tag not in suchary
    # s_other_tag: text="Other joke" doesn't match text, but its tag name="Python"
    # matches the text filter (Q(tags__name__icontains=q)) AND its tag slug="python"
    # matches the tag slug filter — so it IS correctly included
    assert s_other_tag in suchary


# ===========================================================================
# SucharListView — author filter
# ===========================================================================


@pytest.mark.django_db
def test_list_author_filter_exact_match(client, django_user_model):
    u1 = django_user_model.objects.create_user(
        username="alice",
        email="alice@example.com",
        password="pw",  # noqa: S106
    )
    u2 = django_user_model.objects.create_user(
        username="bob",
        email="bob@example.com",
        password="pw",  # noqa: S106
    )
    s_alice = Suchar.objects.create(text="Alice joke", author=u1)
    Suchar.objects.create(text="Bob joke", author=u2)

    response = client.get(reverse(LIST_URL), {"author": "alice"})
    suchary = list(response.context["suchary"])
    assert s_alice in suchary
    assert all(s.author.username == "alice" for s in suchary)


# ===========================================================================
# SucharCreateView — anonymous redirect
# ===========================================================================


@pytest.mark.django_db
def test_create_requires_login(client):
    response = client.get(reverse(ADD_URL))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_create_post_requires_login(client):
    response = client.post(reverse(ADD_URL), {"text": "joke"})
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


# ===========================================================================
# SucharUpdateView — permissions
# ===========================================================================


@pytest.mark.django_db
def test_update_non_author_forbidden(client, django_user_model):
    author = django_user_model.objects.create_user(
        username="upd_author",
        email="ua@example.com",
        password="pw",  # noqa: S106
    )
    other = django_user_model.objects.create_user(
        username="upd_other",
        email="uo@example.com",
        password="pw",  # noqa: S106
    )
    future = timezone.now() + timedelta(days=1)
    suchar = Suchar.objects.create(
        text="Protected joke",
        author=author,
        published_at=future,
    )

    client.force_login(other)
    response = client.get(reverse("suchary:update", kwargs={"pk": suchar.pk}))
    # Non-author gets redirected to login (Django's default handle_no_permission)
    assert response.status_code in (HTTPStatus.FOUND, HTTPStatus.FORBIDDEN)


@pytest.mark.django_db
def test_update_author_can_edit_unpublished(client, django_user_model):
    author = django_user_model.objects.create_user(
        username="upd_auth2",
        email="ua2@example.com",
        password="pw",  # noqa: S106
    )
    future = timezone.now() + timedelta(days=1)
    suchar = Suchar.objects.create(
        text="Future joke",
        author=author,
        published_at=future,
    )

    client.force_login(author)
    response = client.get(reverse("suchary:update", kwargs={"pk": suchar.pk}))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_update_author_gets_too_late_page_for_published(client, django_user_model):
    author = django_user_model.objects.create_user(
        username="upd_auth3",
        email="ua3@example.com",
        password="pw",  # noqa: S106
    )
    past = timezone.now() - timedelta(seconds=1)
    suchar = Suchar.objects.create(text="Old joke", author=author, published_at=past)

    client.force_login(author)
    response = client.get(reverse("suchary:update", kwargs={"pk": suchar.pk}))
    assert response.status_code == HTTPStatus.FORBIDDEN
    # Template is in Polish; hourglass emoji is unique to edit_too_late.html
    assert "\u231b".encode() in response.content  # ⌛


# ===========================================================================
# vote_suchar — GET method rejected
# ===========================================================================


@pytest.mark.django_db
def test_vote_get_method_not_allowed(client, django_user_model):
    author = django_user_model.objects.create_user(
        username="vget_auth",
        email="vga@example.com",
        password="pw",  # noqa: S106
    )
    suchar = Suchar.objects.create(text="joke", author=author)
    client.force_login(author)
    response = client.get(reverse("suchary:vote", kwargs={"pk": suchar.pk}))
    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED


# ===========================================================================
# vote_suchar — anonymous redirect
# ===========================================================================


@pytest.mark.django_db
def test_vote_anonymous_redirects_to_login(client, django_user_model):
    author = django_user_model.objects.create_user(
        username="vanon_auth",
        email="vaa@example.com",
        password="pw",  # noqa: S106
    )
    suchar = Suchar.objects.create(text="joke", author=author)
    response = client.post(
        reverse("suchary:vote", kwargs={"pk": suchar.pk}),
        {"vote_type": "funny"},
    )
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]
