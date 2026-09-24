"""E2E: the browser's time zone drives input/display via the `user_tz` cookie
(static/js/timezone.js → suchar_overflow/middleware.py, issue #410)."""

import datetime
from typing import TYPE_CHECKING

import pytest

from suchar_overflow.suchary.models import Suchar

if TYPE_CHECKING:
    from playwright.sync_api import Browser
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.users.models import User as UserModel

#: 12:00Z in July = 14:00 in Warsaw = 08:00 in New York.
_STORED = datetime.datetime(2024, 7, 10, 12, 0, tzinfo=datetime.UTC)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_anonymous_visitor_sees_times_in_browser_zone(
    browser: Browser,
    live_server: LiveServer,
    e2e_user: UserModel,
) -> None:
    """The first load still renders in the service zone and writes the cookie;
    from the next request on, times are shown in the browser's own zone. No
    login — the cookie writer runs for anonymous visitors too."""
    suchar = Suchar.objects.create(text="Suchar z Nowego Jorku.", author=e2e_user)
    Suchar.objects.filter(pk=suchar.pk).update(created_at=_STORED, published_at=_STORED)

    context = browser.new_context(locale="pl-PL", timezone_id="America/New_York")
    try:
        page = context.new_page()
        page.goto(f"{live_server.url}/suchary/")
        meta = page.locator(".suchar-meta").first
        assert meta.inner_text().endswith("14:00")

        cookies = {c["name"]: c["value"] for c in context.cookies()}
        assert cookies.get("user_tz") == "America/New_York"

        page.reload()
        assert page.locator(".suchar-meta").first.inner_text().endswith("08:00")
    finally:
        context.close()
