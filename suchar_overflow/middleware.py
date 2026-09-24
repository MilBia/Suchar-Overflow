import functools
import zoneinfo
from typing import TYPE_CHECKING

from asgiref.sync import iscoroutinefunction
from django.utils import timezone
from django.utils.decorators import sync_and_async_middleware

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from collections.abc import Callable

    from django.http import HttpRequest
    from django.http import HttpResponseBase

#: Written by ``static/js/timezone.js`` from the browser's
#: ``Intl.DateTimeFormat().resolvedOptions().timeZone`` (#410).
TIMEZONE_COOKIE_NAME = "user_tz"


@functools.cache
def _known_zones() -> frozenset[str]:
    # Scans the tz database once per process; the cookie is client-controlled,
    # so only an exact IANA key is ever handed to ZoneInfo.
    return frozenset(zoneinfo.available_timezones())


def known_zone(name: str | None) -> zoneinfo.ZoneInfo | None:
    """``ZoneInfo(name)`` for an exact IANA key, else ``None``.

    For any client-supplied zone name (the cookie, the edit form's
    ``published_at_tz`` field).
    """
    if not name or name not in _known_zones():
        return None
    return zoneinfo.ZoneInfo(name)


def zone_from_request(request: HttpRequest) -> zoneinfo.ZoneInfo | None:
    """The visitor's zone from the cookie, or ``None`` (missing / unknown)."""
    return known_zone(request.COOKIES.get(TIMEZONE_COOKIE_NAME))


@sync_and_async_middleware
def user_timezone_middleware(
    get_response: Callable[[HttpRequest], HttpResponseBase]
    | Callable[[HttpRequest], Awaitable[HttpResponseBase]],
) -> Callable[..., object]:
    """Activate the visitor's browser time zone for the request (#410).

    Affects only what follows the *current* zone: parsing naive form input
    (``SucharForm.published_at``) and template display (``|date``). Everything
    that buckets or scores by day/hour — achievement rules, contest periods,
    the leaderboard and profile charts/heatmap — pins the service zone
    (``timezone.get_default_timezone()``) explicitly, so it reads the same
    whoever's request runs it. Without a valid cookie the service zone
    (``TIME_ZONE``) stays in effect.
    """
    if iscoroutinefunction(get_response):

        async def async_middleware(request: HttpRequest) -> HttpResponseBase:
            zone = zone_from_request(request)
            if zone is None:
                return await get_response(request)
            with timezone.override(zone):
                return await get_response(request)

        return async_middleware

    def middleware(request: HttpRequest) -> HttpResponseBase:
        zone = zone_from_request(request)
        if zone is None:
            return get_response(request)  # type: ignore[return-value]
        with timezone.override(zone):
            return get_response(request)  # type: ignore[return-value]

    return middleware
