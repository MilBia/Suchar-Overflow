from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import StreamingHttpResponse
from django.views.generic import ListView

from .models import Achievement
from .models import UserAchievement


@login_required
def achievement_stream(request):
    """SSE endpoint: checks once for pending achievements, sets retry interval, closes.
    The browser auto-reconnects after the retry interval, replacing JS polling.
    """

    def event_stream(user_pk):
        cache_key = f"achievements_pending:{user_pk}"
        if cache.get(cache_key):
            yield "data: new\n\n"
        else:
            yield "retry: 10000\n\n"

    response = StreamingHttpResponse(
        event_stream(request.user.pk),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class NotificationInboxView(LoginRequiredMixin, ListView):
    model = UserAchievement
    template_name = "achievements/inbox.html"
    context_object_name = "user_achievements"

    def get_queryset(self):
        return (
            UserAchievement.objects.filter(user=self.request.user)
            .select_related("achievement")
            .order_by("-awarded_at")
        )


class AchievementListView(LoginRequiredMixin, ListView):
    model = Achievement
    template_name = "achievements/list.html"
    context_object_name = "achievements"

    def get_queryset(self):
        return Achievement.objects.all().order_by("theme", "tier", "id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_achievements = set()
        if self.request.user.is_authenticated:
            user_achs = UserAchievement.objects.filter(
                user=self.request.user,
            ).values_list("achievement_id", flat=True)
            user_achievements = set(user_achs)

        context["user_achievements"] = user_achievements

        # Grupowanie i filtrowanie tierów
        all_achs = self.get_queryset()
        visible_achs = []
        grouped = {}

        for ach in all_achs:
            if ach.theme and ach.tier != Achievement.Tier.NONE:
                key = (ach.theme, ach.metric)
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(ach)
            else:
                visible_achs.append(ach)

        for series in grouped.values():
            for ach in series:
                visible_achs.append(ach)
                if ach.id not in user_achievements:
                    # found first locked achievement in series, stop revealing
                    break

        # Wymuszamy domyślne sortowanie zgodnie z widokiem bazy
        visible_achs.sort(key=lambda x: (x.theme or "", x.tier, x.id))
        context["achievements"] = visible_achs

        return context
