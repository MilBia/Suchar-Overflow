from django.core.cache import cache

# django-ninja resolves endpoint parameter types via get_type_hints() at
# request-handling time, forcing eager resolution — same gotcha as
# View.as_view() in users/mixins.py; this import must stay real, not
# TYPE_CHECKING-only.
from django.http import HttpRequest  # noqa: TC002
from django.utils.translation import gettext as _
from ninja import Router
from ninja import Schema
from ninja.errors import HttpError
from ninja.security import django_auth

from suchar_overflow.users.models import User

from .models import Achievement
from .models import UserAchievement

router = Router()

VALID_FRONTEND_SLUGS = frozenset(
    {
        "frontend-recenzent-totalny",
        "frontend-stluczona-mysz",
        "frontend-zbieracz-sucharow",
        "frontend-niecierpliwy",
        "frontend-odkrywca",
    },
)


class AchievementSchema(Schema):
    name: str
    description: str
    icon_content: str
    tier: int


class FrontendEventSchema(Schema):
    event_slug: str


@router.get("/unseen", response=list[AchievementSchema], auth=django_auth)
def list_unseen_achievements(request: HttpRequest) -> list[dict]:
    user = request.user
    assert isinstance(user, User)  # django_auth already rejects anonymous requests
    cache_key = f"achievements_pending:{user.pk}"

    if not cache.get(cache_key):
        return []

    unseen_achievements = list(
        UserAchievement.objects.filter(
            user=user,
            is_seen=False,
        ).select_related("achievement"),
    )

    if not unseen_achievements:
        cache.delete(cache_key)
        return []

    response_data = [
        {
            "name": _(user_ach.achievement.name),
            "description": _(user_ach.achievement.description),
            "icon_content": user_ach.achievement.icon_content,
            "tier": user_ach.achievement.tier,
        }
        for user_ach in unseen_achievements
    ]

    cache.delete(cache_key)
    return response_data


@router.post("/mark-seen", auth=django_auth)
def mark_achievements_seen(request: HttpRequest) -> dict:
    user = request.user
    assert isinstance(user, User)  # django_auth already rejects anonymous requests
    UserAchievement.objects.filter(
        user=user,
        is_seen=False,
    ).update(is_seen=True)
    return {"ok": True}


@router.get("/frontend-owned", response=list[str], auth=django_auth)
def list_frontend_owned(request: HttpRequest) -> list[str]:
    user = request.user
    assert isinstance(user, User)  # django_auth already rejects anonymous requests
    return list(
        UserAchievement.objects.filter(
            user=user,
            achievement__event_type=Achievement.EventType.FRONTEND,
        ).values_list("achievement__slug", flat=True),
    )


@router.post("/frontend-event", auth=django_auth)
def record_frontend_event(request: HttpRequest, payload: FrontendEventSchema) -> dict:
    user = request.user
    assert isinstance(user, User)  # django_auth already rejects anonymous requests
    if payload.event_slug not in VALID_FRONTEND_SLUGS:
        raise HttpError(400, "Invalid achievement slug")

    try:
        achievement = Achievement.objects.get(slug=payload.event_slug)
    except Achievement.DoesNotExist as exc:
        raise HttpError(404, "Achievement not found") from exc

    already_owned = UserAchievement.objects.filter(
        user=user,
        achievement=achievement,
    ).exists()

    if not already_owned:
        UserAchievement.objects.create(user=user, achievement=achievement)
        cache_key = f"achievements_pending:{user.pk}"
        cache.set(cache_key, value=True, timeout=30 * 24 * 60 * 60)

    return {"ok": True}
