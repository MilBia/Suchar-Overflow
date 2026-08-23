from django.db.models.signals import post_save
from django.dispatch import receiver

from suchar_overflow.achievements.engine import AchievementEngine
from suchar_overflow.achievements.models import Achievement
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


# Note: EventType updates are handled in models.py.
