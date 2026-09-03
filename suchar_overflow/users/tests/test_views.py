from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.urls import reverse
from django.utils.translation import gettext

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote
from suchar_overflow.users.tests.factories import UserFactory

if TYPE_CHECKING:
    from django.test import AsyncClient

    from suchar_overflow.users.models import User


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_update_get(async_client: AsyncClient) -> None:
    user = await sync_to_async(UserFactory.create)()
    await async_client.aforce_login(user)
    response = await async_client.get(reverse("users:update"))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_update_post_redirects_to_profile(async_client: AsyncClient) -> None:
    user = await sync_to_async(UserFactory.create)()
    await async_client.aforce_login(user)
    response = await async_client.post(reverse("users:update"), {"name": "New Name"})
    assert response.status_code == HTTPStatus.FOUND
    # django-stubs' ASGI test-client response stub doesn't declare `.url`,
    # even though Django's HttpResponseRedirectBase sets it at runtime.
    assert response.url == f"/users/{user.username}/"  # type: ignore[attr-defined]
    messages = list(get_messages(response.asgi_request))
    assert [str(m) for m in messages] == [gettext("Profile updated.")]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_detail_authenticated(async_client: AsyncClient) -> None:
    target = await sync_to_async(UserFactory.create)()
    viewer = await sync_to_async(UserFactory.create)()
    await async_client.aforce_login(viewer)
    response = await async_client.get(
        reverse("users:detail", kwargs={"username": target.username}),
    )
    assert response.status_code == HTTPStatus.OK


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_detail_not_authenticated(async_client: AsyncClient) -> None:
    target = await sync_to_async(UserFactory.create)()
    response = await async_client.get(
        reverse("users:detail", kwargs={"username": target.username}),
    )
    login_url = reverse(settings.LOGIN_URL)
    assert response.status_code == HTTPStatus.FOUND
    # See the `.url` type:ignore comment in test_user_update_post_redirects_to_profile.
    assert response.url.startswith(login_url)  # type: ignore[attr-defined]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_detail_stats_calculation(async_client: AsyncClient) -> None:
    user = await sync_to_async(UserFactory.create)()
    s1 = await Suchar.objects.acreate(text="Joke 1", author=user)
    await Vote.objects.acreate(suchar=s1, user=user, is_funny=True)

    other_user = await sync_to_async(UserFactory.create)()
    s2 = await Suchar.objects.acreate(text="Joke 2", author=user)
    await Vote.objects.acreate(suchar=s2, user=other_user, is_dry=True)

    await async_client.aforce_login(user)
    response = await async_client.get(f"/users/{user.username}/")

    assert response.status_code == HTTPStatus.OK
    expected_score = 2
    assert response.context["object"].total_score == expected_score
    expected_count = 2
    assert response.context["suchar_count"] == expected_count


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_detail_rank_label_qualifies_funny_ranking(
    async_client: AsyncClient,
) -> None:
    """The stat next to ``global_rank`` must say it ranks by funny votes (#240)."""
    target = await sync_to_async(UserFactory.create)()
    viewer = await sync_to_async(UserFactory.create)()
    await async_client.aforce_login(viewer)
    response = await async_client.get(
        reverse("users:detail", kwargs={"username": target.username}),
    )

    assert response.status_code == HTTPStatus.OK
    content = response.content.decode()
    # Assert on the (possibly untranslated) catalog string, not a hardcoded
    # Polish rendering — CI never compiles locale/*.mo (see CLAUDE.md).
    assert gettext("Comedy Rank") in content
    assert ">Rank<" not in content


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_detail_shows_comedy_rank_name_for_top_user(
    async_client: AsyncClient,
) -> None:
    """A user leading the funny-vote ranking gets the top rank name (#291)."""
    await sync_to_async(cache.clear)()
    target = await sync_to_async(UserFactory.create)()
    rival = await sync_to_async(UserFactory.create)()
    voter = await sync_to_async(UserFactory.create)()

    target_joke = await Suchar.objects.acreate(text="top joke", author=target)
    rival_joke = await Suchar.objects.acreate(text="rival joke", author=rival)
    for _i in range(3):
        u = await sync_to_async(UserFactory.create)()
        await Vote.objects.acreate(suchar=target_joke, user=u, is_funny=True)
    await Vote.objects.acreate(suchar=rival_joke, user=voter, is_funny=True)

    await async_client.aforce_login(voter)
    response = await async_client.get(
        reverse("users:detail", kwargs={"username": target.username}),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.context["global_rank"] == 1
    assert str(response.context["global_rank_name"]) == gettext("Godfather of Puns")
    content = response.content.decode()
    assert gettext("Godfather of Puns") in content
    # Raw rank number stays available: as small secondary text (announced by
    # screen readers, unlike a bare title) and in the title for mouse hover.
    normalized = " ".join(content.split())
    assert 'text-muted small">#1</span>' in normalized
    assert 'title="#1"' in content


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_detail_comedy_rank_name_uses_ranked_population_not_all_users(
    async_client: AsyncClient,
) -> None:
    """The percentile bands divide by users with >=1 funny vote received (#291).

    Three authors on 3 / 2 / 1 funny votes; the six voters have none received.
    With the right denominator (3 ranked authors) the 1-vote author lands in the
    bottom band; counting all nine users would push them a band higher.
    """
    await sync_to_async(cache.clear)()
    authors = [await sync_to_async(UserFactory.create)() for _i in range(3)]
    for funny_votes, author in zip((3, 2, 1), authors, strict=True):
        joke = await Suchar.objects.acreate(text="j", author=author)
        for _v in range(funny_votes):
            voter = await sync_to_async(UserFactory.create)()
            await Vote.objects.acreate(suchar=joke, user=voter, is_funny=True)

    await async_client.aforce_login(authors[0])

    async def rank_of(author: User) -> tuple[int, str]:
        resp = await async_client.get(
            reverse("users:detail", kwargs={"username": author.username}),
        )
        return resp.context["global_rank"], str(resp.context["global_rank_name"])

    assert await rank_of(authors[2]) == (3, gettext("Wedding Uncle"))
    assert await rank_of(authors[1]) == (2, gettext("Laughter Carousel Chairman"))


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_detail_comedy_rank_name_floor_without_funny_votes(
    async_client: AsyncClient,
) -> None:
    """No funny votes received -> the floor rank name, regardless of position."""
    await sync_to_async(cache.clear)()
    target = await sync_to_async(UserFactory.create)()
    rival = await sync_to_async(UserFactory.create)()

    target_joke = await Suchar.objects.acreate(text="dry one", author=target)
    rival_joke = await Suchar.objects.acreate(text="funny one", author=rival)
    await Vote.objects.acreate(suchar=target_joke, user=rival, is_dry=True)
    await Vote.objects.acreate(suchar=rival_joke, user=target, is_funny=True)

    await async_client.aforce_login(target)
    response = await async_client.get(
        reverse("users:detail", kwargs={"username": target.username}),
    )

    assert response.status_code == HTTPStatus.OK
    assert str(response.context["global_rank_name"]) == gettext("Junior Quizmaster")
    assert gettext("Junior Quizmaster") in response.content.decode()
