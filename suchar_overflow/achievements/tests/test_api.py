from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.core.cache import cache

from suchar_overflow.achievements.api import VALID_FRONTEND_SLUGS
from suchar_overflow.achievements.cache import pending_cache_key
from suchar_overflow.achievements.cache import toast_cache_key
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.conftest import make_user

if TYPE_CHECKING:
    from django.test import Client

UNSEEN_ACHIEVEMENTS_URL = "/api/achievements/unseen"
MARK_SEEN_URL = "/api/achievements/mark-seen"
FRONTEND_OWNED_URL = "/api/achievements/frontend-owned"
FRONTEND_EVENT_URL = "/api/achievements/frontend-event"
TOAST_URL = "/api/achievements/toast"


def make_achievement(slug: str, name: str = "Achievement") -> Achievement:
    return Achievement.objects.create(
        slug=slug,
        name=name,
        description="A test achievement.",
        icon_content="<svg></svg>",
        category="LIFETIME",
        event_type="SUCHAR_POSTED",
        metric="COUNT_SUCHAR",
        threshold=1,
    )


def make_frontend_achievement(
    slug: str,
    name: str = "Frontend Achievement",
) -> Achievement:
    achievement, _ = Achievement.objects.get_or_create(
        slug=slug,
        defaults={
            "name": name,
            "description": "A frontend achievement.",
            "icon_content": "<svg></svg>",
            "category": "LIFETIME",
            "event_type": "FRONTEND",
            "metric": "FRONTEND_EVENT",
            "threshold": 1,
        },
    )
    return achievement


@pytest.mark.django_db
def test_unseen_achievements_requires_login(client: Client) -> None:
    response = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_unseen_achievements_empty_by_default(client: Client) -> None:
    user = make_user("user1")
    client.force_login(user)

    response = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.django_db
def test_unseen_achievements_returns_awarded(client: Client) -> None:
    user = make_user("user1")
    client.force_login(user)

    ach = make_achievement("ach-1", name="Achievement Test")
    UserAchievement.objects.create(user=user, achievement=ach, is_seen=False)

    # Set pending cache key
    cache.set(pending_cache_key(user.pk), value=True)

    response = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response.status_code == HTTPStatus.OK

    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Achievement Test"
    assert data[0]["description"] == "A test achievement."
    assert data[0]["icon_content"] == "<svg></svg>"
    assert data[0]["tier"] == Achievement.Tier.NONE

    # Subsequent request should return empty (cache key cleared)
    response_again = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response_again.status_code == HTTPStatus.OK
    assert response_again.json() == []

    # Cache is cleared; is_seen stays False (bell/mine page marks it)
    user_ach = UserAchievement.objects.get(user=user, achievement=ach)
    assert user_ach.is_seen is False
    assert cache.get(pending_cache_key(user.pk)) is None


# ---------------------------------------------------------------------------
# POST /api/achievements/mark-seen
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_mark_seen_requires_login(client: Client) -> None:
    response = client.post(MARK_SEEN_URL)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_mark_seen_marks_all_unseen_as_seen(client: Client) -> None:
    user = make_user("user_ms")
    client.force_login(user)

    ach1 = make_achievement("ms-ach-1", name="One")
    ach2 = make_achievement("ms-ach-2", name="Two")
    ua1 = UserAchievement.objects.create(user=user, achievement=ach1, is_seen=False)
    ua2 = UserAchievement.objects.create(user=user, achievement=ach2, is_seen=False)

    response = client.post(MARK_SEEN_URL)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"ok": True}

    ua1.refresh_from_db()
    ua2.refresh_from_db()
    assert ua1.is_seen is True
    assert ua2.is_seen is True


@pytest.mark.django_db
def test_mark_seen_idempotent(client: Client) -> None:
    user = make_user("user_ms_idem")
    client.force_login(user)

    ach = make_achievement("ms-idem-ach")
    ua = UserAchievement.objects.create(user=user, achievement=ach, is_seen=True)

    response = client.post(MARK_SEEN_URL)
    assert response.status_code == HTTPStatus.OK

    ua.refresh_from_db()
    assert ua.is_seen is True


# ---------------------------------------------------------------------------
# GET /api/achievements/toast  (first-funny-vote 🥁, issue #292)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_toast_requires_login(client: Client) -> None:
    response = client.get(TOAST_URL)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_toast_returns_null_when_no_flag(client: Client) -> None:
    user = make_user("user_toast_none")
    client.force_login(user)
    cache.delete(toast_cache_key(user.pk))

    response = client.get(TOAST_URL)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"toast": None}


@pytest.mark.django_db
def test_toast_returns_payload_and_clears_flag(client: Client) -> None:
    user = make_user("user_toast_set")
    client.force_login(user)
    cache.set(toast_cache_key(user.pk), value=True, timeout=60)

    response = client.get(TOAST_URL)
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["toast"] is not None
    assert body["toast"]["title"]
    assert body["toast"]["body"]

    # The read is what clears the flag (mirrors GET /unseen).
    assert cache.get(toast_cache_key(user.pk)) is None
    assert client.get(TOAST_URL).json() == {"toast": None}


# ---------------------------------------------------------------------------
# GET /api/achievements/frontend-owned
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_frontend_owned_requires_login(client: Client) -> None:
    response = client.get(FRONTEND_OWNED_URL)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_frontend_owned_empty_when_user_has_no_frontend_achievements(
    client: Client,
) -> None:
    user = make_user("user_fe_empty")
    client.force_login(user)

    response = client.get(FRONTEND_OWNED_URL)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.django_db
def test_frontend_owned_returns_correct_slugs(client: Client) -> None:
    user = make_user("user_fe_slugs")
    client.force_login(user)

    ach1 = make_frontend_achievement("frontend-odkrywca", name="Odkrywca")
    ach2 = make_frontend_achievement("frontend-niecierpliwy", name="Niecierpliwy")
    UserAchievement.objects.create(user=user, achievement=ach1)
    UserAchievement.objects.create(user=user, achievement=ach2)

    response = client.get(FRONTEND_OWNED_URL)
    assert response.status_code == HTTPStatus.OK

    data = response.json()
    assert sorted(data) == sorted(["frontend-odkrywca", "frontend-niecierpliwy"])


@pytest.mark.django_db
def test_frontend_owned_excludes_non_frontend_achievements(client: Client) -> None:
    user = make_user("user_fe_excl")
    client.force_login(user)

    frontend_ach = make_frontend_achievement("frontend-odkrywca", name="Odkrywca")
    # Use get_or_create: data migrations may have seeded SUCHAR_POSTED achievements
    non_frontend_ach, _ = Achievement.objects.get_or_create(
        slug="test-non-frontend-excl",
        defaults={
            "name": "Non Frontend",
            "description": "A test achievement.",
            "icon_content": "<svg></svg>",
            "category": "LIFETIME",
            "event_type": "SUCHAR_POSTED",
            "metric": "COUNT_SUCHAR",
            "threshold": 1,
        },
    )
    UserAchievement.objects.create(user=user, achievement=frontend_ach)
    UserAchievement.objects.create(user=user, achievement=non_frontend_ach)

    response = client.get(FRONTEND_OWNED_URL)
    assert response.status_code == HTTPStatus.OK

    data = response.json()
    assert data == ["frontend-odkrywca"]
    assert "test-non-frontend-excl" not in data


# ---------------------------------------------------------------------------
# POST /api/achievements/frontend-event
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_frontend_event_requires_login(client: Client) -> None:
    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": "frontend-odkrywca"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_frontend_event_returns_400_for_invalid_slug(client: Client) -> None:
    user = make_user("user_fe_bad_slug")
    client.force_login(user)

    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": "not-a-valid-slug"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.django_db
def test_frontend_event_returns_400_for_empty_slug(client: Client) -> None:
    user = make_user("user_fe_empty_slug")
    client.force_login(user)

    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": ""},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.django_db
def test_frontend_event_happy_path_creates_user_achievement(client: Client) -> None:
    user = make_user("user_fe_happy")
    client.force_login(user)

    # The migration seeds this achievement; use get_or_create to be safe
    make_frontend_achievement("frontend-odkrywca", name="Odkrywca")

    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": "frontend-odkrywca"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"ok": True}

    ach = Achievement.objects.get(slug="frontend-odkrywca")
    assert UserAchievement.objects.filter(user=user, achievement=ach).count() == 1


@pytest.mark.django_db
def test_frontend_event_idempotent_no_duplicate_created(client: Client) -> None:
    user = make_user("user_fe_idem")
    client.force_login(user)

    ach = make_frontend_achievement("frontend-odkrywca", name="Odkrywca")
    UserAchievement.objects.create(user=user, achievement=ach)

    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": "frontend-odkrywca"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"ok": True}

    assert UserAchievement.objects.filter(user=user, achievement=ach).count() == 1


@pytest.mark.django_db
def test_frontend_event_sets_cache_key_on_new_award(client: Client) -> None:
    user = make_user("user_fe_cache_set")
    client.force_login(user)

    make_frontend_achievement("frontend-odkrywca", name="Odkrywca")
    cache.delete(pending_cache_key(user.pk))

    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": "frontend-odkrywca"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK

    assert cache.get(pending_cache_key(user.pk)) is True


@pytest.mark.django_db
def test_frontend_event_does_not_set_cache_key_when_already_owned(
    client: Client,
) -> None:
    user = make_user("user_fe_cache_idem")
    client.force_login(user)

    ach = make_frontend_achievement("frontend-odkrywca", name="Odkrywca")
    UserAchievement.objects.create(user=user, achievement=ach)
    cache.delete(pending_cache_key(user.pk))

    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": "frontend-odkrywca"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK

    assert cache.get(pending_cache_key(user.pk)) is None


# ---------------------------------------------------------------------------
# Konami easter egg — frontend-ee-konami (#283)
# ---------------------------------------------------------------------------


def test_konami_slug_is_in_the_frontend_allowlist() -> None:
    assert "frontend-ee-konami" in VALID_FRONTEND_SLUGS


@pytest.mark.django_db
def test_frontend_event_awards_the_konami_achievement(client: Client) -> None:
    user = make_user("user_fe_konami")
    client.force_login(user)

    # Seeded by migration 0020; get_or_create keeps the test independent of it.
    make_frontend_achievement("frontend-ee-konami", name="Kod Konami")

    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": "frontend-ee-konami"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"ok": True}

    ach = Achievement.objects.get(slug="frontend-ee-konami")
    assert UserAchievement.objects.filter(user=user, achievement=ach).count() == 1
