from .models import UserAchievement


def achievements_bell(request):
    if not request.user.is_authenticated:
        return {"unseen_achievements_count": 0, "unseen_achievements_preview": []}
    unseen = list(
        UserAchievement.objects.filter(user=request.user, is_seen=False)
        .select_related("achievement")
        .order_by("-awarded_at"),
    )
    return {
        "unseen_achievements_count": len(unseen),
        "unseen_achievements_preview": unseen[:5],
    }
