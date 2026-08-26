from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import receiver

from suchar_overflow.achievements.context_processors import invalidate_bell_cache
from suchar_overflow.achievements.engine import AchievementEngine
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote


@receiver(post_save, sender=Suchar)
def check_suchar_achievements(
    sender: type[Suchar],  # noqa: ARG001
    instance: Suchar,
    created: bool,  # noqa: FBT001
    **kwargs: object,  # noqa: ARG001
) -> None:
    if created:
        user = instance.author
        AchievementEngine.check_achievements(
            user,
            Achievement.EventType.SUCHAR_POSTED,
            instance,
        )


@receiver(post_save, sender=Vote)
def check_vote_achievements(
    sender: type[Vote],  # noqa: ARG001
    instance: Vote,
    created: bool,  # noqa: FBT001
    **kwargs: object,  # noqa: ARG001
) -> None:
    if created:
        # Check for voter
        voter = instance.user
        AchievementEngine.check_achievements(
            voter,
            Achievement.EventType.VOTE_CAST,
            instance,
        )

        # Check for author of the suchar (receiving vote)
        author = instance.suchar.author
        AchievementEngine.check_achievements(
            author,
            Achievement.EventType.VOTE_RECEIVED,
            instance,
        )


@receiver(post_save, sender=UserAchievement)
@receiver(post_delete, sender=UserAchievement)
def invalidate_bell_cache_on_change(
    sender: type[UserAchievement],  # noqa: ARG001
    instance: UserAchievement,
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Keep the bell badge fresh the moment an achievement is awarded.

    Covers every ORM write path — the engine, the periodic award tasks, the
    frontend-event endpoint and the admin — so a new achievement shows up on
    the next page load instead of waiting out BELL_CACHE_TTL. `is_seen`
    flipped through the admin form lands here too; the bulk `.update()` in
    `POST /api/achievements/mark-seen` fires no signal and invalidates itself.

    Uses `instance.user_id` rather than `instance.user` — reading the FK
    object would issue a query on every award.
    """
    invalidate_bell_cache(instance.user_id)


# Note: EventType updates are handled in models.py.
