from django.contrib import messages
from django.core.cache import cache
from django.utils.translation import gettext as _

from .models import UserAchievement

_CACHE_KEY = "achievements_pending:{user_pk}"


class AchievementNotificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/"):
            return self.get_response(request)

        if request.user.is_authenticated:
            cache_key = _CACHE_KEY.format(user_pk=request.user.pk)
            if cache.get(cache_key):
                new_achievements = list(
                    UserAchievement.objects.filter(
                        user=request.user,
                        is_seen=False,
                    ).select_related("achievement"),
                )

                if new_achievements:
                    for user_ach in new_achievements:
                        messages.success(
                            request,
                            _("Achievement Unlocked: %(name)s!")
                            % {"name": user_ach.achievement.name},
                        )
                        user_ach.is_seen = True
                    UserAchievement.objects.bulk_update(new_achievements, ["is_seen"])

                cache.delete(cache_key)

        return self.get_response(request)
