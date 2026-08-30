"""Cache keys and invalidation helpers for the achievement-notification UI.

Two independent cache mechanisms track the same phenomenon ("an awarded but
unread achievement"), with deliberately different lifecycles:

- ``achievements_pending:{pk}`` (``pending_cache_key``) — a one-shot "the SSE
  client still has to fetch its toast" flag, set by ``AchievementEngine`` /
  ``POST /api/achievements/frontend-event`` and cleared by
  ``GET /api/achievements/unseen``. It does *not* track ``is_seen``.
- ``achievements_bell:{pk}`` (``bell_cache_key``) — mirrors the persisted
  ``is_seen=False`` rows behind the bell badge and survives the toast fetch.

Merging the two was considered and rejected (see issue #231): their lifecycles
genuinely differ.
"""

from django.core.cache import cache

# How many unseen achievements the bell dropdown renders inline.
BELL_PREVIEW_LIMIT = 5

# Backstop TTL only — correctness comes from invalidation (see
# invalidate_bell_cache below), not from expiry. Matches
# stats.views.LEADERBOARD_CACHE_TTL so both caches age the same way.
BELL_CACHE_TTL = 60 * 5


def pending_cache_key(user_id: int) -> str:
    """Cache key holding the "SSE toast still pending" flag for one user.

    Deliberately distinct from ``bell_cache_key`` — see this module's
    docstring for the difference in lifecycle.
    """
    return f"achievements_pending:{user_id}"


def bell_cache_key(user_id: int) -> str:
    """Cache key holding the unseen-achievement *count* for one user.

    Deliberately distinct from ``pending_cache_key`` (set by
    ``AchievementEngine``, cleared by ``GET /api/achievements/unseen``): that
    key is a one-shot "the SSE client still has to fetch its toast" flag, this
    one mirrors the persisted ``is_seen=False`` rows behind the bell badge and
    survives the toast fetch.
    """
    return f"achievements_bell:{user_id}"


def invalidate_bell_cache(user_id: int) -> None:
    """Drop a user's cached bell count so the next request recomputes it.

    Called from the write paths that change the number of unseen achievements
    without leaving a fresh cache entry behind them: the ``UserAchievement``
    post_save/post_delete receivers in ``signals.py`` (covering the engine, the
    periodic tasks, the frontend-event endpoint and the admin) and
    ``POST /api/achievements/mark-seen``, whose bulk ``.update()`` fires no
    model signals.

    Not every bulk ``is_seen`` write calls this: ``MyAchievementsView.get``
    also does a signal-less ``.aupdate(is_seen=True)``, but it renders a
    template in the same request, so the short-preview branch in
    ``context_processors.achievements_bell`` recomputes the count to 0 on the
    spot (see the comment there). It is also intentionally not called from that
    async view because it is synchronous (``cache.delete`` on ``django_redis``
    would block the event loop).
    """
    cache.delete(bell_cache_key(user_id))
