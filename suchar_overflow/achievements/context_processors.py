from typing import TYPE_CHECKING

from django.core.cache import cache

from .cache import BELL_CACHE_TTL
from .cache import BELL_PREVIEW_LIMIT
from .cache import bell_cache_key
from .models import UserAchievement

if TYPE_CHECKING:
    from typing import TypedDict

    from django.http import HttpRequest

    class AchievementsBellContext(TypedDict):
        unseen_achievements_count: int
        unseen_achievements_preview: list[UserAchievement]


def achievements_bell(request: HttpRequest) -> AchievementsBellContext:
    if not request.user.is_authenticated:
        return {"unseen_achievements_count": 0, "unseen_achievements_preview": []}

    cache_key = bell_cache_key(request.user.pk)
    cached_count = cache.get(cache_key)
    if cached_count == 0:
        # Hot path: this processor runs for *every* rendered template, and for
        # most users on most requests there is nothing to show. Serve that from
        # the cache without touching the DB at all.
        return {"unseen_achievements_count": 0, "unseen_achievements_preview": []}

    unseen = UserAchievement.objects.filter(user=request.user, is_seen=False)
    # No select_related("user") — the queryset is already filtered by a known
    # user, nothing reads `ua.user` (UserAchievement.__str__ falls back to
    # `user_id`), and the JOIN dragged every user column, password hash
    # included, into a value that then gets cached (cf. the defer("password")
    # note in stats/views.py).
    preview = list(
        unseen.select_related("achievement").order_by("-awarded_at")[
            :BELL_PREVIEW_LIMIT
        ],
    )

    if len(preview) < BELL_PREVIEW_LIMIT:
        # The live LIMIT query came back short, so it is the exact total —
        # authoritative even over a stale cached count. This branch is also
        # what keeps MyAchievementsView honest: after its .aupdate() there are
        # zero unseen rows, so the count is recomputed to 0 here.
        count = len(preview)
    elif cached_count is None:
        count = unseen.count()
    else:
        count = cached_count

    if count != cached_count:
        # Only write when the value actually changed. Re-setting an unchanged
        # count on every warm request would keep pushing BELL_CACHE_TTL out,
        # so a stale count >= BELL_PREVIEW_LIMIT (which the short-preview branch
        # can't correct) would never expire for an active user — the TTL
        # backstop only works if it's allowed to run out.
        cache.set(cache_key, count, BELL_CACHE_TTL)
    return {
        "unseen_achievements_count": count,
        "unseen_achievements_preview": preview,
    }
