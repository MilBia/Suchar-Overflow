from django.core.cache import cache

_CACHE_KEY = "achievements_pending:{user_pk}"


class AchievementNotificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    _BYPASS_PATHS = ("/api/", "/achievements/stream/")

    def __call__(self, request):
        if any(request.path.startswith(p) for p in self._BYPASS_PATHS):
            return self.get_response(request)

        if request.user.is_authenticated:
            cache_key = _CACHE_KEY.format(user_pk=request.user.pk)
            cache.delete(cache_key)

        return self.get_response(request)
