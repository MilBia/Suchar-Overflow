from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement

User = get_user_model()

UNSEEN_ACHIEVEMENTS_URL = "/api/achievements/unseen"
FRONTEND_OWNED_URL = "/api/achievements/frontend-owned"
FRONTEND_EVENT_URL = "/api/achievements/frontend-event"


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


def make_achievement(slug, name="Achievement"):
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


def make_frontend_achievement(slug, name="Frontend Achievement"):
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
def test_unseen_achievements_requires_login(client):
    response = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_unseen_achievements_empty_by_default(client):
    user = make_user("user1")
    client.force_login(user)

    response = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.django_db
def test_unseen_achievements_returns_awarded(client):
    user = make_user("user1")
    client.force_login(user)

    ach = make_achievement("ach-1", name="Achievement Test")
    UserAchievement.objects.create(user=user, achievement=ach, is_seen=False)

    # Set pending cache key
    cache.set(f"achievements_pending:{user.pk}", value=True)

    response = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response.status_code == HTTPStatus.OK

    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Achievement Test"
    assert data[0]["description"] == "A test achievement."
    assert data[0]["icon_content"] == "<svg></svg>"
    assert data[0]["tier"] == Achievement.Tier.NONE

    # Subsequent request should return empty
    response_again = client.get(UNSEEN_ACHIEVEMENTS_URL)
    assert response_again.status_code == HTTPStatus.OK
    assert response_again.json() == []

    # Check database and cache state
    user_ach = UserAchievement.objects.get(user=user, achievement=ach)
    assert user_ach.is_seen is True
    assert cache.get(f"achievements_pending:{user.pk}") is None


# ---------------------------------------------------------------------------
# GET /api/achievements/frontend-owned
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_frontend_owned_requires_login(client):
    response = client.get(FRONTEND_OWNED_URL)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_frontend_owned_empty_when_user_has_no_frontend_achievements(client):
    user = make_user("user_fe_empty")
    client.force_login(user)

    response = client.get(FRONTEND_OWNED_URL)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.django_db
def test_frontend_owned_returns_correct_slugs(client):
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
def test_frontend_owned_excludes_non_frontend_achievements(client):
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
def test_frontend_event_requires_login(client):
    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": "frontend-odkrywca"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_frontend_event_returns_400_for_invalid_slug(client):
    user = make_user("user_fe_bad_slug")
    client.force_login(user)

    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": "not-a-valid-slug"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.django_db
def test_frontend_event_returns_400_for_empty_slug(client):
    user = make_user("user_fe_empty_slug")
    client.force_login(user)

    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": ""},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.django_db
def test_frontend_event_happy_path_creates_user_achievement(client):
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
def test_frontend_event_idempotent_no_duplicate_created(client):
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
def test_frontend_event_sets_cache_key_on_new_award(client):
    user = make_user("user_fe_cache_set")
    client.force_login(user)

    make_frontend_achievement("frontend-odkrywca", name="Odkrywca")
    cache.delete(f"achievements_pending:{user.pk}")

    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": "frontend-odkrywca"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK

    assert cache.get(f"achievements_pending:{user.pk}") is True


@pytest.mark.django_db
def test_frontend_event_does_not_set_cache_key_when_already_owned(client):
    user = make_user("user_fe_cache_idem")
    client.force_login(user)

    ach = make_frontend_achievement("frontend-odkrywca", name="Odkrywca")
    UserAchievement.objects.create(user=user, achievement=ach)
    cache.delete(f"achievements_pending:{user.pk}")

    response = client.post(
        FRONTEND_EVENT_URL,
        data={"event_slug": "frontend-odkrywca"},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK

    assert cache.get(f"achievements_pending:{user.pk}") is None
