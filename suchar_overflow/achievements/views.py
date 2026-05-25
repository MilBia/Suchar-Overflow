import asyncio

from asgiref.sync import sync_to_async
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.views import View

from suchar_overflow.users.mixins import AsyncLoginRequiredMixin

from .models import Achievement
from .models import UserAchievement


@login_required
async def achievement_stream(request):
    """SSE: check for pending achievements in a loop, keeping connection open."""
    user = await request.auser()

    async def event_stream():
        cache_key = f"achievements_pending:{user.pk}"
        yield "retry: 5000\n\n"
        while True:
            try:
                if await cache.aget(cache_key):
                    yield "data: new\n\n"
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class MyAchievementsView(AsyncLoginRequiredMixin, View):
    template_name = "achievements/mine.html"

    async def get(self, request, *args, **kwargs):
        user = await request.auser()
        await UserAchievement.objects.filter(
            user=user,
            is_seen=False,
        ).aupdate(is_seen=True)

        user_achievements = [
            ua
            async for ua in UserAchievement.objects.filter(user=user)
            .select_related("achievement")
            .order_by("-awarded_at")
        ]
        return await sync_to_async(render)(
            request,
            self.template_name,
            {"user_achievements": user_achievements},
        )


class AchievementListView(AsyncLoginRequiredMixin, View):
    template_name = "achievements/list.html"

    async def get(self, request, *args, **kwargs):
        user = await request.auser()
        user_achs = {
            pk
            async for pk in UserAchievement.objects.filter(
                user=user,
            ).values_list("achievement_id", flat=True)
        }

        all_achs = [
            a async for a in Achievement.objects.all().order_by("theme", "tier", "id")
        ]
        visible_achs = []
        grouped: dict[tuple[str, str], list[Achievement]] = {}

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
                if ach.id not in user_achs:
                    break

        visible_achs.sort(key=lambda x: (x.theme or "", x.tier, x.id))

        return await sync_to_async(render)(
            request,
            self.template_name,
            {"achievements": visible_achs, "user_achievements": user_achs},
        )
