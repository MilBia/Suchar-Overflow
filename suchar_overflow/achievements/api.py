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

from .cache import invalidate_bell_cache
from .cache import pending_cache_key
from .cache import toast_cache_key
from .models import Achievement
from .models import UserAchievement

router = Router()

# Exact-match allowlist for POST /frontend-event. Every client-awardable slug
# must be listed here explicitly — an existing Achievement row is necessary but
# not sufficient. Group-A easter eggs (umbrella #278) use the `frontend-ee-`
# prefix by convention; each child issue adds its own concrete slug(s) to this
# set alongside the Achievement data migration (#283 added the first one,
# `frontend-ee-konami`).
VALID_FRONTEND_SLUGS = frozenset(
    {
        "frontend-recenzent-totalny",
        "frontend-stluczona-mysz",
        "frontend-zbieracz-sucharow",
        "frontend-niecierpliwy",
        "frontend-odkrywca",
        # Group-A easter eggs (umbrella #278): the `frontend-ee-` prefix.
        "frontend-ee-konami",  # #283 — Konami code
    },
)


class AchievementSchema(Schema):
    name: str
    description: str
    icon_content: str
    tier: int


class FrontendEventSchema(Schema):
    event_slug: str


class ToastPayloadSchema(Schema):
    title: str
    body: str


class ToastResponseSchema(Schema):
    toast: ToastPayloadSchema | None = None


@router.get("/unseen", response=list[AchievementSchema], auth=django_auth)
def list_unseen_achievements(request: HttpRequest) -> list[dict]:
    user = request.user
    assert isinstance(user, User)  # django_auth already rejects anonymous requests
    cache_key = pending_cache_key(user.pk)

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


@router.get("/toast", response=ToastResponseSchema, auth=django_auth)
def get_pending_toast(request: HttpRequest) -> dict[str, dict[str, str] | None]:
    """Return (and clear) the pending first-funny-vote 🥁 toast, if any.

    Called by the SSE client when the stream emits ``data: toast`` (issue
    #292). Mirrors ``GET /unseen``: the stream only flags, this read is what
    actually clears ``toast_pending:{pk}``. The text is translated here so it
    lands in the *author's* language, not the voter's.

    ``cache.delete`` returns whether the key existed, so it doubles as the
    "was a toast actually pending?" check — a single atomic op. Two racing
    SSE-driven fetches (a slow ``fetch`` that outlives the stream's 2 s poll)
    can't then both come back with a payload.
    """
    user = request.user
    assert isinstance(user, User)  # django_auth already rejects anonymous requests

    if not cache.delete(toast_cache_key(user.pk)):
        return {"toast": None}

    return {
        "toast": {
            "title": _("Ba dum tss 🥁"),
            "body": _("Your suchar just landed its first funny vote."),
        },
    }


@router.post("/mark-seen", auth=django_auth)
def mark_achievements_seen(request: HttpRequest) -> dict[str, bool]:
    user = request.user
    assert isinstance(user, User)  # django_auth already rejects anonymous requests
    UserAchievement.objects.filter(
        user=user,
        is_seen=False,
    ).update(is_seen=True)
    # Bulk .update() fires no post_save, so the signal receiver in signals.py
    # can't clear the bell count here — do it explicitly, otherwise the badge
    # would stay lit until BELL_CACHE_TTL expires.
    invalidate_bell_cache(user.pk)
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
def record_frontend_event(
    request: HttpRequest,
    payload: FrontendEventSchema,
) -> dict[str, bool]:
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
        cache_key = pending_cache_key(user.pk)
        cache.set(cache_key, value=True, timeout=30 * 24 * 60 * 60)

    return {"ok": True}
