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

Two more, unrelated keys live here too (issue #292, umbrella #279 — pure UI
delight, no achievement and no bell row behind them):

- ``toast_pending:{pk}`` (``toast_cache_key``) — a one-shot "the SSE client
  still has to fetch a lightweight 🥁 toast" flag, set by the voting path when
  a suchar gets its first *community* funny vote and cleared by
  ``GET /api/achievements/toast``.
- ``toast_sent_suchar:{pk}`` (``suchar_toast_sent_cache_key``) — a
  per-suchar "the 🥁 already fired for this one" latch, added via
  ``mark_suchar_toast_sent`` so un-voting and re-voting a suchar back through
  0 → 1 does not keep re-toasting its author. Best-effort only: the cache is
  not durable, so an eviction or the TTL lapsing can let a later genuine
  first-community-vote toast again — an acceptable outcome for a delight.
"""

from django.core.cache import cache

# How many unseen achievements the bell dropdown renders inline.
BELL_PREVIEW_LIMIT = 5

# Backstop TTL for the first-funny-vote toast flag. The SSE loop normally
# drains it within seconds; this only bounds how stale a "your suchar got its
# first funny vote" toast can be for an author who had no stream open when the
# vote landed.
TOAST_CACHE_TTL = 60 * 60

# How long the per-suchar "already toasted" latch lives. Long enough that
# ordinary un-vote / re-vote churn can't re-toast the author; not "forever",
# so the key space stays bounded. Mirrors ``pending_cache_key``'s 30 days.
TOAST_SENT_CACHE_TTL = 60 * 60 * 24 * 30

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


def toast_cache_key(user_id: int) -> str:
    """Cache key holding the "SSE 🥁 toast still pending" flag for one user.

    Set by the voting path on a suchar's first funny vote (issue #292),
    cleared by ``GET /api/achievements/toast``. Unrelated to the two
    achievement keys above — see this module's docstring.
    """
    return f"toast_pending:{user_id}"


def set_pending_toast(user_id: int) -> None:
    """Flag that ``user_id`` has a first-funny-vote 🥁 toast to be delivered.

    The SSE stream (``achievements/views.py``) picks the flag up on its next
    poll and emits ``data: toast``; the browser then fetches and clears it via
    ``GET /api/achievements/toast``.
    """
    cache.set(toast_cache_key(user_id), value=True, timeout=TOAST_CACHE_TTL)


def suchar_toast_sent_cache_key(suchar_id: int) -> str:
    """Cache key for the per-suchar "🥁 already fired for this one" latch."""
    return f"toast_sent_suchar:{suchar_id}"


def mark_suchar_toast_sent(suchar_id: int) -> bool:
    """Claim the one-time 🥁 toast for ``suchar_id``.

    Returns ``True`` exactly once per suchar (per TTL window): the first
    caller adds the latch key, every later caller sees it already there. Lets
    the voting path fire the author's toast only on the *first* time a suchar
    crosses 0 → 1 community funny votes, not on every re-vote.
    """
    return cache.add(
        suchar_toast_sent_cache_key(suchar_id),
        value=True,
        timeout=TOAST_SENT_CACHE_TTL,
    )


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
