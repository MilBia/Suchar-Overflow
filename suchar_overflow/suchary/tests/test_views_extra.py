"""Extra view tests: SucharListView filtering and SucharUpdateView permissions."""

from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.contrib.messages import get_messages
from django.db import connection
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Tag
from suchar_overflow.suchary.models import Vote

if TYPE_CHECKING:
    from django.test import Client

    from suchar_overflow.users.models import User as UserModel

LIST_URL = "suchary:list"
ADD_URL = "suchary:add"


# ===========================================================================
# SucharListView — unpublished posts hidden
# ===========================================================================


@pytest.mark.django_db
def test_list_hides_scheduled_suchar(client: Client) -> None:
    user = make_user("author")
    future = timezone.now() + timedelta(days=1)
    Suchar.objects.create(text="Future joke", author=user, published_at=future)

    response = client.get(reverse(LIST_URL))
    assert response.status_code == HTTPStatus.OK
    assert "Future joke" not in response.content.decode()


@pytest.mark.django_db
def test_list_hides_scheduled_suchar_from_its_own_author(client: Client) -> None:
    """Guard for issue #373 — the list stays clean for the author too.

    Deliberately *not* a regression test: `SucharListView` filters on
    `published_at__lte=timezone.now()` for every viewer, the author included,
    so this passed before the template's `{% if not suchar.is_published %}`
    branch (a "Scheduled" badge plus an author-only Edit button) was removed —
    which is exactly why that branch was dead code. It locks in that the list
    surfaces neither a scheduled suchar nor an edit affordance for one, so the
    branch does not come back. The author's own scheduled suchary are shown on
    their profile instead (`scheduled_suchary` in `UserDetailView`, owner-gated).
    """
    author = make_user("scheduled_author")
    future = timezone.now() + timedelta(days=1)
    scheduled = Suchar.objects.create(
        text="Future joke",
        author=author,
        published_at=future,
    )

    client.force_login(author)
    response = client.get(reverse(LIST_URL))

    assert response.status_code == HTTPStatus.OK
    content = response.content.decode()
    assert "Future joke" not in content
    # Language-independent stand-in for the removed Edit button (CI never
    # compiles the .mo files, so asserting on the label text proves nothing).
    assert reverse("suchary:update", kwargs={"pk": scheduled.pk}) not in content


@pytest.mark.django_db
def test_list_template_never_renders_edit_link_for_unpublished_suchar() -> None:
    """Guard directly on the template, not the view's filter.

    The two tests above only prove `SucharListView` never *hands* the
    template an unpublished suchar — they can't tell the difference between
    "the template has no branch for it" and "the branch is there but never
    reached", because `published_at__lte=timezone.now()` keeps an unpublished
    suchar out of the queryset either way (PR #386 review, NC-A). This
    renders `suchar_list.html` directly with an unpublished suchar forced
    into its context — the one situation in which a reintroduced
    `{% if not suchar.is_published %}` branch could draw anything — so a
    future revert of #373 fails here even if the view-level filter is
    untouched. Pattern follows `tests/test_a11y_static.py`'s direct
    `render_to_string` usage.
    """
    author = make_user("template_guard_author")
    unpublished = Suchar.objects.create(
        text="Should never render an edit link",
        author=author,
        published_at=timezone.now() + timedelta(days=1),
    )
    request = RequestFactory().get(reverse(LIST_URL))
    request.user = author

    html = render_to_string(
        "suchary/suchar_list.html",
        {"suchary": [unpublished], "is_paginated": False},
        request=request,
    )

    assert reverse("suchary:update", kwargs={"pk": unpublished.pk}) not in html


@pytest.mark.django_db
def test_list_shows_published_suchar(client: Client) -> None:
    user = make_user("author")
    Suchar.objects.create(text="Past joke", author=user)

    response = client.get(reverse(LIST_URL))
    assert "Past joke" in response.content.decode()


# ===========================================================================
# SucharListView — authenticated user vote annotations
# ===========================================================================


@pytest.mark.django_db
def test_list_annotates_user_is_funny_for_authenticated(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
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
def test_list_annotates_user_is_dry_for_authenticated(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
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
def test_list_no_user_vote_annotations_for_anonymous(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
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
def test_list_combined_text_and_tag_filter(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
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
def test_list_author_filter_exact_match(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
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
def test_create_requires_login(client: Client) -> None:
    response = client.get(reverse(ADD_URL))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_create_post_requires_login(client: Client) -> None:
    response = client.post(reverse(ADD_URL), {"text": "joke"})
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


# ===========================================================================
# SucharUpdateView — permissions
# ===========================================================================


def _make_editable_suchar(django_user_model: type[UserModel], slug: str) -> Suchar:
    author = django_user_model.objects.create_user(
        username=f"upd_{slug}",
        email=f"{slug}@example.com",
        password="pw",  # noqa: S106
    )
    future = timezone.now() + timedelta(days=1)
    return Suchar.objects.create(
        text="Future joke",
        author=author,
        published_at=future,
    )


@pytest.mark.django_db
def test_update_non_author_forbidden(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
    suchar = _make_editable_suchar(django_user_model, "non_author")
    other = django_user_model.objects.create_user(
        username="upd_other",
        email="uo@example.com",
        password="pw",  # noqa: S106
    )

    client.force_login(other)
    response = client.get(reverse("suchary:update", kwargs={"pk": suchar.pk}))
    # Non-author gets redirected to login (Django's default handle_no_permission)
    assert response.status_code in (HTTPStatus.FOUND, HTTPStatus.FORBIDDEN)
    messages = list(get_messages(response.wsgi_request))
    assert [str(m) for m in messages] == [
        gettext("You don't have permission to do that."),
    ]


@pytest.mark.django_db
def test_update_author_can_edit_unpublished(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
    suchar = _make_editable_suchar(django_user_model, "auth2")

    client.force_login(suchar.author)
    response = client.get(reverse("suchary:update", kwargs={"pk": suchar.pk}))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_update_author_post_success_shows_message(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
    suchar = _make_editable_suchar(django_user_model, "auth4")

    client.force_login(suchar.author)
    response = client.post(
        reverse("suchary:update", kwargs={"pk": suchar.pk}),
        {"text": "Updated future joke"},
    )
    assert response.status_code == HTTPStatus.FOUND
    messages = list(get_messages(response.wsgi_request))
    assert [str(m) for m in messages] == [
        gettext("Suchar odświeżony. Dalej suchy, tylko młodszy."),
    ]


def _suchar_select_count(ctx: CaptureQueriesContext) -> int:
    """Count the authorship-row fetches — SELECTs of a single suchar by pk.

    The #201 guard is specifically about `_get_suchar` loading the edited row
    once, not twice. Requiring both `FROM "suchary_suchar"` and a
    `"suchary_suchar"."id" =` filter pins it to that `.aget(pk=...)`:

    * `UPDATE "suchary_suchar" SET ... WHERE "id" =` from `form.save()` / the
      `edit_count` bump has the id filter but no `FROM`, so it is excluded;
    * the `EditCountRule` aggregate the `suchar_edited` signal runs for the
      "Recydywa" achievement (#297) has `FROM "suchary_suchar"` but filters on
      `author_id`, not `id`, so it is excluded too.
    """
    return len(
        [
            q
            for q in ctx.captured_queries
            if 'FROM "suchary_suchar"' in q["sql"]
            and '"suchary_suchar"."id" =' in q["sql"]
        ],
    )


@pytest.mark.django_db
def test_update_get_fetches_suchar_once(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
    """Regression test for issue #201.

    `AsyncUserPassesTestMixin.dispatch` calls `test_func()`, which loads the
    suchar to check authorship; `get()` then loaded the very same row a second
    time. The object must be fetched exactly once per request.
    """
    suchar = _make_editable_suchar(django_user_model, "qcount_get")
    client.force_login(suchar.author)

    with CaptureQueriesContext(connection) as ctx:
        response = client.get(reverse("suchary:update", kwargs={"pk": suchar.pk}))

    assert response.status_code == HTTPStatus.OK
    assert _suchar_select_count(ctx) == 1


@pytest.mark.django_db
def test_update_post_fetches_suchar_once(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
    """Regression test for issue #201 — same double fetch on the POST path."""
    suchar = _make_editable_suchar(django_user_model, "qcount_post")
    client.force_login(suchar.author)

    with CaptureQueriesContext(connection) as ctx:
        response = client.post(
            reverse("suchary:update", kwargs={"pk": suchar.pk}),
            {"text": "Updated future joke"},
        )

    assert response.status_code == HTTPStatus.FOUND
    assert _suchar_select_count(ctx) == 1


@pytest.mark.django_db
def test_update_missing_pk_returns_404(client: Client) -> None:
    """The memo must not swallow `Http404` for a non-existent `pk` (issue #201).

    `self._suchar` is only assigned after a successful `aget`, so `test_func()`
    still raises `Http404` before any handler runs — this guards the PR's
    explicit "Http404 unchanged" claim.
    """
    client.force_login(make_user("u404"))

    response = client.get(reverse("suchary:update", kwargs={"pk": 999999}))

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.django_db
def test_update_author_gets_too_late_page_for_published(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
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
