from http import HTTPStatus

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.urls import reverse

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement

User = get_user_model()

ACHIEVEMENT_LIST_URL = "achievements:list"


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


def make_achievement(
    slug,
    name="Achievement",
    *,
    is_secret=False,
    theme="",
    tier=Achievement.Tier.NONE,
):
    return Achievement.objects.create(
        slug=slug,
        name=name,
        description="A test achievement.",
        icon_content="<svg></svg>",
        category="LIFETIME",
        event_type="SUCHAR_POSTED",
        metric="COUNT_SUCHAR",
        threshold=1,
        is_secret=is_secret,
        theme=theme,
        tier=tier,
    )


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_achievement_list_requires_login(async_client):
    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_achievement_list_renders_for_authenticated_user(async_client):
    user = await sync_to_async(make_user)("user1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_achievement_list_shows_all_non_grouped_achievements(async_client):
    user = await sync_to_async(make_user)("user1")
    await async_client.aforce_login(user)
    await sync_to_async(make_achievement)("ach-1", name="Achievement One")
    await sync_to_async(make_achievement)("ach-2", name="Achievement Two")

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    achs = response.context["achievements"]
    names = [a.name for a in achs]
    assert "Achievement One" in names
    assert "Achievement Two" in names


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_user_achievements_set_in_context(async_client):
    user = await sync_to_async(make_user)("user1")
    await async_client.aforce_login(user)
    ach = await sync_to_async(make_achievement)("ach-1")
    await UserAchievement.objects.acreate(user=user, achievement=ach)

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert ach.pk in response.context["user_achievements"]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_unearned_achievement_not_in_user_achievements(async_client):
    user = await sync_to_async(make_user)("user1")
    await async_client.aforce_login(user)
    ach = await sync_to_async(make_achievement)("ach-1")

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert ach.pk not in response.context["user_achievements"]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_series_first_locked_achievement_is_visible(async_client):
    user = await sync_to_async(make_user)("user1")
    await async_client.aforce_login(user)

    ach_bronze = await sync_to_async(make_achievement)(
        "series-bronze",
        name="Bronze",
        theme="Programming",
        tier=Achievement.Tier.BRONZE,
    )
    await sync_to_async(make_achievement)(
        "series-silver",
        name="Silver",
        theme="Programming",
        tier=Achievement.Tier.SILVER,
    )

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    ids = [a.id for a in response.context["achievements"]]
    assert ach_bronze.id in ids


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_series_locked_second_tier_hidden_until_first_earned(async_client):
    user = await sync_to_async(make_user)("user1")
    await async_client.aforce_login(user)

    await sync_to_async(make_achievement)(
        "series-bronze",
        name="Bronze",
        theme="Programming",
        tier=Achievement.Tier.BRONZE,
    )
    ach_silver = await sync_to_async(make_achievement)(
        "series-silver",
        name="Silver",
        theme="Programming",
        tier=Achievement.Tier.SILVER,
    )

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    ids = [a.id for a in response.context["achievements"]]
    assert ach_silver.id not in ids


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_series_second_tier_visible_after_first_earned(async_client):
    user = await sync_to_async(make_user)("user1")
    await async_client.aforce_login(user)

    ach_bronze = await sync_to_async(make_achievement)(
        "series-bronze",
        name="Bronze",
        theme="Programming",
        tier=Achievement.Tier.BRONZE,
    )
    ach_silver = await sync_to_async(make_achievement)(
        "series-silver",
        name="Silver",
        theme="Programming",
        tier=Achievement.Tier.SILVER,
    )
    await UserAchievement.objects.acreate(user=user, achievement=ach_bronze)

    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    ids = [a.id for a in response.context["achievements"]]
    assert ach_silver.id in ids


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_achievement_list_user_has_no_earned_achievements(async_client):
    user = await sync_to_async(make_user)("user1")
    await async_client.aforce_login(user)
    response = await async_client.get(reverse(ACHIEVEMENT_LIST_URL))
    assert response.status_code == HTTPStatus.OK
    assert response.context["user_achievements"] == set()
