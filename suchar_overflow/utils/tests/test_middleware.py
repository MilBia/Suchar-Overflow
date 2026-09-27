"""``zone_from_request`` in isolation (#410).

Request-level behaviour of ``user_timezone_middleware`` (display, form parsing,
no leak between requests) is covered in ``tests/test_user_timezone.py``.
"""

import zoneinfo

import pytest
from django.test import RequestFactory

from suchar_overflow.utils.middleware import TIMEZONE_COOKIE_NAME
from suchar_overflow.utils.middleware import zone_from_request

NEW_YORK = zoneinfo.ZoneInfo("America/New_York")


# Only exact IANA keys are accepted.
@pytest.mark.parametrize(
    ("cookie", "expected"),
    [
        ("America/New_York", NEW_YORK),
        (
            "America/Argentina/Buenos_Aires",
            zoneinfo.ZoneInfo("America/Argentina/Buenos_Aires"),
        ),
        (None, None),
        ("", None),
        ("Mars/Olympus_Mons", None),
        ("../../etc/passwd", None),
        ("america/new_york", None),
        ("Europe/Warsaw\x00", None),
    ],
)
def test_zone_from_request(
    cookie: str | None,
    expected: zoneinfo.ZoneInfo | None,
) -> None:
    request = RequestFactory().get("/")
    if cookie is not None:
        request.COOKIES[TIMEZONE_COOKIE_NAME] = cookie
    assert zone_from_request(request) == expected
