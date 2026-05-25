import asyncio

from asgiref.sync import markcoroutinefunction
from django.core.cache import cache

_CACHE_KEY = "achievements_pending:{user_pk}"


class AchievementNotificationMiddleware:
    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if asyncio.iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    _BYPASS_PATHS = ("/api/", "/achievements/stream/")

    def __call__(self, request):
        if asyncio.iscoroutinefunction(self):
            return self.__acall__(request)

        if not any(request.path.startswith(p) for p in self._BYPASS_PATHS):
            if request.user.is_authenticated:
                cache.delete(_CACHE_KEY.format(user_pk=request.user.pk))

        return self.get_response(request)

    async def __acall__(self, request):
        if not any(request.path.startswith(p) for p in self._BYPASS_PATHS):
            user = await request.auser()
            if user.is_authenticated:
                await cache.adelete(_CACHE_KEY.format(user_pk=user.pk))

        return await self.get_response(request)
