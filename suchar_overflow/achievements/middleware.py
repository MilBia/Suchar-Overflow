from django.contrib import messages
from django.utils.translation import gettext as _

from .models import UserAchievement


class AchievementNotificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Check for unseen achievements
            new_achievements = UserAchievement.objects.filter(
                user=request.user,
                is_seen=False,
            ).select_related("achievement")

            if new_achievements.exists():
                for user_ach in new_achievements:
                    messages.success(
                        request,
                        _("Achievement Unlocked: %(name)s!")
                        % {"name": user_ach.achievement.name},
                    )
                    user_ach.is_seen = True
                    user_ach.save()

        return self.get_response(request)
