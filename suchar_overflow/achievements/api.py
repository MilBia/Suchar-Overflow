from django.core.cache import cache
from django.utils.translation import gettext as _
from ninja import Router
from ninja import Schema
from ninja.security import django_auth

from .models import UserAchievement

router = Router()


class AchievementSchema(Schema):
    name: str
    description: str
    icon_content: str
    tier: int


@router.get("/unseen", response=list[AchievementSchema], auth=django_auth)
def list_unseen_achievements(request):
    user = request.user
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

    response_data = []
    for user_ach in unseen_achievements:
        # Wrap translatable strings in _() to ensure
        # evaluation in current language context
        response_data.append(
            {
                "name": _(user_ach.achievement.name),
                "description": _(user_ach.achievement.description),
                "icon_content": user_ach.achievement.icon_content,
                "tier": user_ach.achievement.tier,
            },
        )
        user_ach.is_seen = True

    UserAchievement.objects.bulk_update(unseen_achievements, ["is_seen"])
    cache.delete(cache_key)

    return response_data
