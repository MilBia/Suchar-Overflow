"""Tests for the achievements_bell context processor."""

from typing import TYPE_CHECKING

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from suchar_overflow.achievements.context_processors import achievements_bell
from suchar_overflow.achievements.context_processors import bell_cache_key
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.conftest import make_user
from suchar_overflow.users.models import User

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.http import HttpRequest


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """LocMemCache is process-global and pytest-django never resets it."""
    cache.clear()
    yield
    cache.clear()


def make_achievement(slug: str, name: str = "Achievement") -> Achievement:
    ach, _ = Achievement.objects.get_or_create(
        slug=slug,
        defaults={
            "name": name,
            "description": "desc",
            "icon_content": "<svg></svg>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.SUCHAR_POSTED,
            "metric": Achievement.Metric.COUNT_SUCHAR,
            "threshold": 99,
        },
    )
    return ach


@pytest.mark.django_db
def test_anonymous_user_gets_zero_count() -> None:
    factory = RequestFactory()
    request = factory.get("/")
    request.user = type("AnonymousUser", (), {"is_authenticated": False})()

    ctx = achievements_bell(request)

    assert ctx["unseen_achievements_count"] == 0
    assert ctx["unseen_achievements_preview"] == []


@pytest.mark.django_db
def test_authenticated_user_with_no_unseen_gets_zero_count() -> None:
    user = make_user("cp_user1")
    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    ctx = achievements_bell(request)

    assert ctx["unseen_achievements_count"] == 0
    assert ctx["unseen_achievements_preview"] == []


@pytest.mark.django_db
def test_unseen_count_reflects_unseen_achievements() -> None:
    user = make_user("cp_user2")
    ach1 = make_achievement("cp-ach-1", "One")
    ach2 = make_achievement("cp-ach-2", "Two")
    UserAchievement.objects.create(user=user, achievement=ach1, is_seen=False)
    UserAchievement.objects.create(user=user, achievement=ach2, is_seen=False)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    ctx = achievements_bell(request)

    assert ctx["unseen_achievements_count"] == 2  # noqa: PLR2004
    assert len(ctx["unseen_achievements_preview"]) == 2  # noqa: PLR2004


@pytest.mark.django_db
def test_seen_achievements_not_counted() -> None:
    user = make_user("cp_user3")
    ach = make_achievement("cp-ach-seen", "Seen")
    UserAchievement.objects.create(user=user, achievement=ach, is_seen=True)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    ctx = achievements_bell(request)

    assert ctx["unseen_achievements_count"] == 0
    assert ctx["unseen_achievements_preview"] == []


@pytest.mark.django_db
def test_preview_capped_at_five() -> None:
    user = make_user("cp_user4")
    for i in range(7):
        ach = make_achievement(f"cp-ach-{i}", f"Achievement {i}")
        UserAchievement.objects.create(user=user, achievement=ach, is_seen=False)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    ctx = achievements_bell(request)

    assert ctx["unseen_achievements_count"] == 7  # noqa: PLR2004
    assert len(ctx["unseen_achievements_preview"]) == 5  # noqa: PLR2004


@pytest.mark.django_db
def test_preview_ordered_newest_first() -> None:
    user = make_user("cp_user5")
    ach1 = make_achievement("cp-order-1", "Older")
    ach2 = make_achievement("cp-order-2", "Newer")
    ua1 = UserAchievement.objects.create(user=user, achievement=ach1, is_seen=False)
    ua2 = UserAchievement.objects.create(user=user, achievement=ach2, is_seen=False)

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    ctx = achievements_bell(request)

    preview_pks = [ua.pk for ua in ctx["unseen_achievements_preview"]]
    assert preview_pks[0] == ua2.pk
    assert preview_pks[1] == ua1.pk


def _request_for(user: User) -> HttpRequest:
    request = RequestFactory().get("/")
    request.user = user
    return request


@pytest.mark.django_db
def test_query_does_not_join_the_user_table() -> None:
    """The queryset already filters by a known user; the JOIN only dragged
    every user column (password hash included) along for nothing."""
    user = make_user("cp_nojoin")
    UserAchievement.objects.create(
        user=user,
        achievement=make_achievement("cp-nojoin-1", "NoJoin"),
        is_seen=False,
    )
    request = _request_for(user)

    with CaptureQueriesContext(connection) as ctx:
        achievements_bell(request)

    sql = " ".join(query["sql"] for query in ctx.captured_queries)
    assert User._meta.db_table not in sql  # noqa: SLF001
    assert "password" not in sql
    # The filter itself still lives on the userachievement table.
    assert "user_id" in sql


@pytest.mark.django_db
def test_second_call_without_unseen_hits_cache_and_skips_db() -> None:
    user = make_user("cp_cache_empty")
    request = _request_for(user)

    achievements_bell(request)  # warms the cache

    with CaptureQueriesContext(connection) as ctx:
        result = achievements_bell(request)

    assert ctx.captured_queries == []
    assert result["unseen_achievements_count"] == 0
    assert result["unseen_achievements_preview"] == []


@pytest.mark.django_db
def test_newly_awarded_achievement_appears_without_waiting_for_ttl() -> None:
    """Freshness guarantee: the post_save receiver drops the cached count, so
    a just-awarded achievement is visible on the very next request."""
    user = make_user("cp_cache_invalidate")
    request = _request_for(user)

    assert achievements_bell(request)["unseen_achievements_count"] == 0
    assert cache.get(bell_cache_key(user.pk)) == 0

    UserAchievement.objects.create(
        user=user,
        achievement=make_achievement("cp-fresh-1", "Fresh"),
        is_seen=False,
    )

    assert cache.get(bell_cache_key(user.pk)) is None
    result = achievements_bell(request)
    assert result["unseen_achievements_count"] == 1
    assert len(result["unseen_achievements_preview"]) == 1


@pytest.mark.django_db
def test_deleting_an_achievement_invalidates_the_cached_count() -> None:
    user = make_user("cp_cache_delete")
    user_ach = UserAchievement.objects.create(
        user=user,
        achievement=make_achievement("cp-del-1", "Deleted"),
        is_seen=False,
    )
    request = _request_for(user)
    assert achievements_bell(request)["unseen_achievements_count"] == 1

    user_ach.delete()

    assert cache.get(bell_cache_key(user.pk)) is None
    assert achievements_bell(request)["unseen_achievements_count"] == 0


@pytest.mark.django_db
def test_mark_seen_endpoint_invalidates_the_cached_count(client: Client) -> None:
    """POST /api/achievements/mark-seen uses a bulk .update(), which fires no
    post_save — it has to clear the bell cache itself."""
    user = make_user("cp_cache_markseen")
    UserAchievement.objects.create(
        user=user,
        achievement=make_achievement("cp-seen-1", "Dismissed"),
        is_seen=False,
    )
    request = _request_for(user)
    assert achievements_bell(request)["unseen_achievements_count"] == 1
    assert cache.get(bell_cache_key(user.pk)) == 1

    client.force_login(user)
    response = client.post("/api/achievements/mark-seen")

    assert response.status_code == 200  # noqa: PLR2004
    assert cache.get(bell_cache_key(user.pk)) is None
    assert achievements_bell(request)["unseen_achievements_count"] == 0


@pytest.mark.django_db
def test_stale_positive_count_is_corrected_by_the_live_preview_query() -> None:
    """Backstop for any write path that bypasses both invalidation hooks (e.g.
    a bulk admin update): a short preview query is authoritative over the
    cached total, so the badge can't outlive the rows behind it."""
    user = make_user("cp_cache_stale")
    UserAchievement.objects.create(
        user=user,
        achievement=make_achievement("cp-stale-1", "Stale"),
        is_seen=False,
    )
    cache.set(bell_cache_key(user.pk), 42, 300)

    result = achievements_bell(_request_for(user))

    assert result["unseen_achievements_count"] == 1
    assert cache.get(bell_cache_key(user.pk)) == 1


@pytest.mark.django_db
def test_cached_count_survives_a_full_preview_page() -> None:
    """With the preview full (>= limit) the cached total is trusted, so the
    warm path costs one query instead of a count() on top."""
    user = make_user("cp_cache_full")
    for i in range(6):
        UserAchievement.objects.create(
            user=user,
            achievement=make_achievement(f"cp-full-{i}", f"Full {i}"),
            is_seen=False,
        )
    request = _request_for(user)

    assert achievements_bell(request)["unseen_achievements_count"] == 6  # noqa: PLR2004
    assert cache.get(bell_cache_key(user.pk)) == 6  # noqa: PLR2004

    with CaptureQueriesContext(connection) as ctx:
        result = achievements_bell(request)

    assert len(ctx.captured_queries) == 1
    assert result["unseen_achievements_count"] == 6  # noqa: PLR2004
    assert len(result["unseen_achievements_preview"]) == 5  # noqa: PLR2004
