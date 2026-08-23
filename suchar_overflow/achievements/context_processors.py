from typing import TYPE_CHECKING

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
    unseen = list(
        UserAchievement.objects.filter(user=request.user, is_seen=False)
        .select_related("user", "achievement")
        .order_by("-awarded_at"),
    )
    return {
        "unseen_achievements_count": len(unseen),
        "unseen_achievements_preview": unseen[:5],
    }
