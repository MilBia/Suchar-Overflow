from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Tag
from suchar_overflow.suchary.models import Vote

if TYPE_CHECKING:
    from django.test import Client

    from suchar_overflow.users.models import User as UserModel


@pytest.mark.django_db
def test_suchar_list_view(client: Client) -> None:
    url = reverse("suchary:list")
    response = client.get(url)
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_create_suchar(client: Client, django_user_model: type[UserModel]) -> None:
    user = django_user_model.objects.create_user(
        username="testuser",
        password="password",  # noqa: S106
    )
    client.force_login(user)

    url = reverse("suchary:add")
    response = client.post(url, {"text": "A dry joke"})

    assert response.status_code == HTTPStatus.FOUND
    assert Suchar.objects.count() == 1
    first_suchar = Suchar.objects.first()
    assert first_suchar is not None
    assert first_suchar.text == "A dry joke"
    messages = list(get_messages(response.wsgi_request))
    assert [str(m) for m in messages] == [gettext("Your suchar has been posted.")]


@pytest.mark.django_db
def test_suchar_list_sorting(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
    user = django_user_model.objects.create_user(
        username="author",
        email="author@example.com",
        password="password",  # noqa: S106
    )
    s1 = Suchar.objects.create(text="Older joke", author=user)
    s2 = Suchar.objects.create(text="Newer joke", author=user)
    # Force deterministic ordering by pinning created_at directly
    Suchar.objects.filter(pk=s1.pk).update(
        created_at=timezone.now() - timedelta(seconds=10),
    )
    Suchar.objects.filter(pk=s2.pk).update(created_at=timezone.now())

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
def test_suchar_list_search(client: Client, django_user_model: type[UserModel]) -> None:
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
def test_create_suchar_with_tags(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
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
    assert suchar is not None
    assert suchar.tags.count() == 3  # noqa: PLR2004
    assert suchar.tags.filter(slug="it").exists()
    assert suchar.tags.filter(slug="programming").exists()
    assert suchar.tags.filter(slug="suchar").exists()


@pytest.mark.django_db
def test_pagination_preserves_params(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
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


@pytest.mark.django_db
def test_search_query_with_special_chars_is_urlencoded_in_links(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
    user = django_user_model.objects.create_user(
        username="author2",
        email="author2@example.com",
        password="password",  # noqa: S106
    )
    tag_it = Tag.objects.create(name="IT2", slug="it2")
    for i in range(15):
        s = Suchar.objects.create(text=f"Fish & Chips {i}", author=user)
        s.tags.add(tag_it)

    url = reverse("suchary:list")
    response = client.get(url, {"q": "Fish & Chips", "tag": "it2"})

    assert response.status_code == HTTPStatus.OK
    content = response.content.decode()

    # An unescaped "&" inside a query-string value would be parsed as the
    # start of a new parameter, breaking the pagination/filter-removal links.
    assert "q=Fish & Chips" not in content
    assert "%26" in content


def _cast_votes(
    suchar: Suchar,
    django_user_model: type[UserModel],
    *,
    funny: int,
    dry: int,
) -> None:
    """Cast `funny` funny votes and `dry` dry votes, one per distinct voter.

    Vote has unique_together ("suchar", "user"), so every vote needs its own
    voter — hence the generated usernames.
    """
    for i in range(funny + dry):
        voter = django_user_model.objects.create_user(
            username=f"voter-{suchar.pk}-{i}",
            email=f"voter-{suchar.pk}-{i}@example.com",
            password="password",  # noqa: S106
        )
        Vote.objects.create(
            suchar=suchar,
            user=voter,
            is_funny=i < funny,
            is_dry=i >= funny,
        )


@pytest.mark.django_db
def test_search_counts_not_inflated_by_multiple_matching_tags(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
    """Regression for #196: parallel tags/votes JOINs must not multiply counts.

    The vote counts are annotated before the `?q=` filter adds its own JOIN to
    the tags table, so without `distinct=True` a suchar matching the phrase on
    two tags reports every vote twice.
    """
    author = django_user_model.objects.create_user(
        username="tag-author",
        email="tag-author@example.com",
        password="password",  # noqa: S106
    )
    suchar = Suchar.objects.create(text="A joke about nothing", author=author)
    suchar.tags.add(
        Tag.objects.create(name="śmiech-fajny", slug="smiech-fajny"),
        Tag.objects.create(name="fajny-info", slug="fajny-info"),
    )
    _cast_votes(suchar, django_user_model, funny=3, dry=2)

    response = client.get(reverse("suchary:list"), {"q": "fajny"})

    assert response.status_code == HTTPStatus.OK
    results = list(response.context["suchary"])
    assert len(results) == 1
    # Two matching tags x five votes would yield 6/4 without distinct=True.
    assert results[0].funny_count == 3  # noqa: PLR2004
    assert results[0].dry_count == 2  # noqa: PLR2004


@pytest.mark.django_db
def test_search_counts_correct_with_single_matching_tag(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
    """The single-matching-tag case (never inflated) must stay correct."""
    author = django_user_model.objects.create_user(
        username="single-tag-author",
        email="single-tag-author@example.com",
        password="password",  # noqa: S106
    )
    suchar = Suchar.objects.create(text="Another joke", author=author)
    suchar.tags.add(Tag.objects.create(name="fajny-only", slug="fajny-only"))
    _cast_votes(suchar, django_user_model, funny=3, dry=2)

    response = client.get(reverse("suchary:list"), {"q": "fajny"})

    assert response.status_code == HTTPStatus.OK
    results = list(response.context["suchary"])
    assert len(results) == 1
    assert results[0].funny_count == 3  # noqa: PLR2004
    assert results[0].dry_count == 2  # noqa: PLR2004


@pytest.mark.django_db
def test_search_counts_not_inflated_by_text_match_with_nonmatching_tags(
    client: Client,
    django_user_model: type[UserModel],
) -> None:
    """#196: the fan-out also fires when only the *text* matches `?q=`.

    The tag predicate is OR'd with the text predicate in WHERE, so a text
    match lets every one of the suchar's tag rows through -- two tags that
    don't match the phrase still multiply the vote counts without
    distinct=True. This is the more common production case than two
    genuinely matching tags.
    """
    author = django_user_model.objects.create_user(
        username="text-match-author",
        email="text-match-author@example.com",
        password="password",  # noqa: S106
    )
    suchar = Suchar.objects.create(text="A joke about fajny things", author=author)
    suchar.tags.add(
        Tag.objects.create(name="koty", slug="koty"),
        Tag.objects.create(name="psy", slug="psy"),
    )
    _cast_votes(suchar, django_user_model, funny=3, dry=2)

    response = client.get(reverse("suchary:list"), {"q": "fajny"})

    assert response.status_code == HTTPStatus.OK
    results = list(response.context["suchary"])
    assert len(results) == 1
    # Two non-matching tags x five votes would still yield 6/4 without distinct.
    assert results[0].funny_count == 3  # noqa: PLR2004
    assert results[0].dry_count == 2  # noqa: PLR2004
