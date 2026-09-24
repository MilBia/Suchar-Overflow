"""Per-visitor time zone for input and display (#410, stage 2 of #405).

``suchar_overflow.middleware.user_timezone_middleware`` activates the zone from
the ``user_tz`` cookie (written by ``static/js/timezone.js``). It changes only
how naive form input is parsed and how templates display datetimes; the
invariance of rules/charts/contests under a foreign active zone is covered next
to each computation (``achievements/tests/test_timezone.py`` and the stats /
users view tests).
"""

import datetime
import re
import zoneinfo
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from asgiref.sync import sync_to_async
from django.test import RequestFactory
from django.urls import reverse

from suchar_overflow.conftest import make_user
from suchar_overflow.middleware import TIMEZONE_COOKIE_NAME
from suchar_overflow.middleware import zone_from_request
from suchar_overflow.suchary.models import Suchar

if TYPE_CHECKING:
    from django.test import AsyncClient
    from django.test import Client

NEW_YORK = zoneinfo.ZoneInfo("America/New_York")
WARSAW = zoneinfo.ZoneInfo("Europe/Warsaw")

#: 12:00Z in July = 14:00 CEST = 08:00 EDT.
STORED = datetime.datetime(2024, 7, 10, 12, 0, tzinfo=datetime.UTC)


def _published_suchar() -> Suchar:
    suchar = Suchar.objects.create(text="Displayed per zone", author=make_user("tz410"))
    Suchar.objects.filter(pk=suchar.pk).update(created_at=STORED, published_at=STORED)
    return suchar


def _rendered_publish_value(html: str) -> str:
    match = re.search(r'name="published_at"[^>]*value="([^"]*)"', html)
    assert match is not None
    return match.group(1)


def _rendered_tz(html: str) -> str:
    match = re.search(r'name="published_at_tz"\s+value="([^"]*)"', html)
    assert match is not None
    return match.group(1)


# ---------------------------------------------------------------------------
# zone_from_request — only exact IANA keys are accepted
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_displays_in_cookie_zone(client: Client) -> None:
    _published_suchar()
    client.cookies[TIMEZONE_COOKIE_NAME] = "America/New_York"

    html = client.get(reverse("suchary:list")).content.decode()

    assert ", 08:00<" in html
    assert ", 14:00<" not in html


@pytest.mark.django_db
@pytest.mark.parametrize("cookie", [None, "Mars/Olympus_Mons", "../../etc/passwd"])
def test_list_falls_back_to_service_zone(client: Client, cookie: str | None) -> None:
    _published_suchar()
    if cookie is not None:
        client.cookies[TIMEZONE_COOKIE_NAME] = cookie

    html = client.get(reverse("suchary:list")).content.decode()

    assert ", 14:00<" in html


@pytest.mark.django_db
def test_zone_does_not_leak_into_the_next_request(client: Client) -> None:
    _published_suchar()
    client.cookies[TIMEZONE_COOKIE_NAME] = "America/New_York"
    client.get(reverse("suchary:list"))
    del client.cookies[TIMEZONE_COOKIE_NAME]

    html = client.get(reverse("suchary:list")).content.decode()

    assert ", 14:00<" in html


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_list_displays_in_cookie_zone_async(async_client: AsyncClient) -> None:
    await sync_to_async(_published_suchar)()
    async_client.cookies[TIMEZONE_COOKIE_NAME] = "America/New_York"

    response = await async_client.get(reverse("suchary:list"))

    assert ", 08:00<" in response.content.decode()


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_list_falls_back_to_service_zone_async(async_client: AsyncClient) -> None:
    await sync_to_async(_published_suchar)()

    response = await async_client.get(reverse("suchary:list"))

    assert ", 14:00<" in response.content.decode()


# ---------------------------------------------------------------------------
# Input — the scheduling form reads naive values in the visitor's zone
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_scheduled_time_is_read_in_cookie_zone(client: Client) -> None:
    """14:00 entered in New York (EDT, UTC-4) publishes at 18:00Z."""
    author = make_user("tz410add")
    client.force_login(author)
    client.cookies[TIMEZONE_COOKIE_NAME] = "America/New_York"

    response = client.post(
        reverse("suchary:add"),
        {"text": "Scheduled from New York", "published_at": "2099-07-15 14:00"},
    )

    assert response.status_code == HTTPStatus.FOUND
    suchar = Suchar.objects.get(author=author)
    assert suchar.published_at == datetime.datetime(
        2099,
        7,
        15,
        18,
        0,
        tzinfo=datetime.UTC,
    )


@pytest.mark.django_db
def test_edit_form_round_trips_in_cookie_zone(client: Client) -> None:
    author = make_user("tz410edit")
    scheduled_at = datetime.datetime(2099, 7, 15, 14, 0, tzinfo=NEW_YORK)
    suchar = Suchar.objects.create(
        text="Scheduled",
        author=author,
        published_at=scheduled_at,
    )
    client.force_login(author)
    client.cookies[TIMEZONE_COOKIE_NAME] = "America/New_York"
    url = reverse("suchary:update", kwargs={"pk": suchar.pk})

    value = _rendered_publish_value(client.get(url).content.decode())
    assert value == "2099-07-15 14:00"
    response = client.post(url, {"text": "Scheduled, edited", "published_at": value})

    assert response.status_code == HTTPStatus.FOUND
    suchar.refresh_from_db()
    assert suchar.published_at == scheduled_at


# ---------------------------------------------------------------------------
# Edit form rendered in one zone, submitted in another
# ---------------------------------------------------------------------------


def _scheduled(author_name: str) -> tuple[Suchar, datetime.datetime]:
    scheduled_at = datetime.datetime(2099, 7, 15, 14, 0, tzinfo=WARSAW)
    suchar = Suchar.objects.create(
        text="Scheduled",
        author=make_user(author_name),
        published_at=scheduled_at,
    )
    return suchar, scheduled_at


@pytest.mark.django_db
def test_untouched_value_survives_cookie_set_after_render(client: Client) -> None:
    """First visit: the edit form renders in the service zone (no cookie yet),
    then timezone.js sets a New York cookie before submit. Posting the value
    back untouched must not move the publication by the Warsaw-New York
    offset."""
    suchar, scheduled_at = _scheduled("tz410first")
    client.force_login(suchar.author)
    url = reverse("suchary:update", kwargs={"pk": suchar.pk})

    html = client.get(url).content.decode()
    value = _rendered_publish_value(html)
    assert value == "2099-07-15 14:00"
    assert _rendered_tz(html) == "Europe/Warsaw"

    client.cookies[TIMEZONE_COOKIE_NAME] = "America/New_York"
    response = client.post(
        url,
        {
            "text": "Text-only edit",
            "published_at": value,
            "published_at_tz": "Europe/Warsaw",
        },
    )

    assert response.status_code == HTTPStatus.FOUND
    suchar.refresh_from_db()
    assert suchar.published_at == scheduled_at


@pytest.mark.django_db
def test_changed_value_is_read_in_active_zone(client: Client) -> None:
    """A time the user actually re-typed was typed on the browser's clock —
    the active (cookie) zone — whatever zone the form was rendered in."""
    suchar, _ = _scheduled("tz410changed")
    client.force_login(suchar.author)
    client.cookies[TIMEZONE_COOKIE_NAME] = "America/New_York"

    response = client.post(
        reverse("suchary:update", kwargs={"pk": suchar.pk}),
        {
            "text": "Moved",
            "published_at": "2099-07-15 16:00",
            "published_at_tz": "Europe/Warsaw",
        },
    )

    assert response.status_code == HTTPStatus.FOUND
    suchar.refresh_from_db()
    assert suchar.published_at == datetime.datetime(
        2099,
        7,
        15,
        20,
        0,
        tzinfo=datetime.UTC,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("rendered_tz", ["", "Mars/Olympus_Mons"])
def test_unknown_rendered_zone_falls_back_to_active_zone(
    client: Client,
    rendered_tz: str,
) -> None:
    """A missing or forged ``published_at_tz`` is ignored — the value is parsed
    in the active zone, as before the field existed."""
    suchar, _ = _scheduled(f"tz410forged{len(rendered_tz)}")
    client.force_login(suchar.author)
    client.cookies[TIMEZONE_COOKIE_NAME] = "America/New_York"

    client.post(
        reverse("suchary:update", kwargs={"pk": suchar.pk}),
        {
            "text": "Edit",
            "published_at": "2099-07-15 14:00",
            "published_at_tz": rendered_tz,
        },
    )

    suchar.refresh_from_db()
    assert suchar.published_at == datetime.datetime(
        2099,
        7,
        15,
        18,
        0,
        tzinfo=datetime.UTC,
    )


# ---------------------------------------------------------------------------
# Scheduling input on add / edit / invalid re-render
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_form_renders_empty_schedule_input(client: Client) -> None:
    """No pre-filled "now" from the model default — an empty input is what
    lets suchar_form.js treat any future value as a real schedule."""
    client.force_login(make_user("tz410addget"))

    html = client.get(reverse("suchary:add")).content.decode()

    assert _rendered_publish_value(html) == ""


@pytest.mark.django_db
def test_invalid_edit_rerender_keeps_schedule_and_rendered_zone(client: Client) -> None:
    """An invalid POST re-renders the posted value (not ``""``, which made the
    JS drop the schedule and publish on the next save) and echoes the zone the
    value was originally rendered in, so saving it untouched still keeps the
    stored instant."""
    suchar, scheduled_at = _scheduled("tz410invalid")
    client.force_login(suchar.author)
    url = reverse("suchary:update", kwargs={"pk": suchar.pk})
    client.cookies[TIMEZONE_COOKIE_NAME] = "America/New_York"

    invalid = client.post(
        url,
        {
            "text": "",
            "published_at": "2099-07-15 14:00",
            "published_at_tz": "Europe/Warsaw",
        },
    )

    assert invalid.status_code == HTTPStatus.OK
    html = invalid.content.decode()
    assert _rendered_publish_value(html) == "2099-07-15 14:00"
    assert _rendered_tz(html) == "Europe/Warsaw"

    fixed = client.post(
        url,
        {
            "text": "Now valid",
            "published_at": "2099-07-15 14:00",
            "published_at_tz": "Europe/Warsaw",
        },
    )

    assert fixed.status_code == HTTPStatus.FOUND
    suchar.refresh_from_db()
    assert suchar.published_at == scheduled_at


@pytest.mark.django_db
def test_invalid_add_rerender_keeps_typed_schedule(client: Client) -> None:
    client.force_login(make_user("tz410addinvalid"))

    response = client.post(
        reverse("suchary:add"),
        {
            "text": "",
            "published_at": "2099-07-15 14:00",
            "published_at_tz": "Europe/Warsaw",
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert _rendered_publish_value(response.content.decode()) == "2099-07-15 14:00"
