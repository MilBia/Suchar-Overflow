"""Tests for the achievements_bell context processor."""

import pytest
from django.test import RequestFactory

from suchar_overflow.achievements.context_processors import achievements_bell
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.conftest import make_user


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
