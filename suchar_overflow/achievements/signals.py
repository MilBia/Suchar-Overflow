from typing import TYPE_CHECKING

from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import receiver

from suchar_overflow.achievements.cache import invalidate_bell_cache
from suchar_overflow.achievements.engine import AchievementEngine
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote
from suchar_overflow.suchary.signals import vote_changed

if TYPE_CHECKING:
    from suchar_overflow.users.models import User


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


def _award_vote_achievements(
    voter: User,
    author: User,
    instance: Vote | None = None,
) -> None:
    """Re-evaluate vote-driven achievements for both sides of a vote.

    Runs the engine for the voter (``VOTE_CAST``) and the suchar's author
    (``VOTE_RECEIVED``). ``instance`` is optional because no vote metric
    rule reads it (they all compute from a fresh queryset), so the
    toggle/removal path can call this without a persisted row.
    """
    AchievementEngine.check_achievements(
        voter,
        Achievement.EventType.VOTE_CAST,
        instance,
    )
    AchievementEngine.check_achievements(
        author,
        Achievement.EventType.VOTE_RECEIVED,
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
        # The vote endpoint sets the flag via get_or_create(defaults=...),
        # so on the first vote this already sees the final state (#247).
        # instance.suchar.author resolves without a query — the endpoint
        # loads the suchar with select_related("author") (#203).
        _award_vote_achievements(instance.user, instance.suchar.author, instance)


@receiver(vote_changed)
def check_vote_achievements_on_toggle(
    sender: type[Vote],  # noqa: ARG001
    voter: User,
    author: User,
    **kwargs: object,  # noqa: ARG001
) -> None:
    # vote_changed fires from the vote endpoint after a toggle or removal on
    # an existing row, where post_save(created=True) never runs. Awarding is
    # idempotent (the engine skips owned achievements); it can also award a
    # threshold newly crossed by removing an opposing vote (#247).
    _award_vote_achievements(voter, author)


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
