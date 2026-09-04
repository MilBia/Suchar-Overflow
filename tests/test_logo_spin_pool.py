"""Regression guard for the logo-spin easter egg's meta-suchar pool (#285).

`features/logo_spin.js` reads the pool from a JSON data island
(`#ee-logo-suchary`) that `base.html` emits for authenticated users. Two things
must hold and neither is covered by the JS/E2E suites:

1. The island renders **valid JSON** — a non-empty list of non-empty strings.
   The strings go through `|escapejs` (not `|json_script`, which needs a context
   variable base.html has no view to build), so a bad escape would surface as a
   `JSONDecodeError` here rather than a silent client-side parse failure.
2. The island stays **out of `{% compress js %}`**. `JsCompressor` would treat a
   `<script>` without `src` as an inline hunk, minify it into the bundle and
   drop the `id` — so with `COMPRESS_ENABLED = True` the island must still be
   present verbatim, not folded into a `/static/CACHE/js/` bundle.
"""

import json
import re
from typing import TYPE_CHECKING

import pytest
from django.test import Client
from django.urls import reverse

from suchar_overflow.conftest import make_user

if TYPE_CHECKING:
    from pytest_django.fixtures import Settings as SettingsWrapper

ISLAND_RE = re.compile(
    r'<script id="ee-logo-suchary" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def _home(client: Client) -> str:
    response = client.get(reverse("home"))
    assert response.status_code == 200, response.status_code  # noqa: PLR2004
    return response.content.decode()


@pytest.mark.django_db
def test_pool_island_is_valid_json_list_of_strings() -> None:
    client = Client()
    client.force_login(make_user("logo_spin_pool"))

    match = ISLAND_RE.search(_home(client))
    assert match, "the #ee-logo-suchary data island is missing for a logged-in user"

    pool = json.loads(match.group(1))
    assert isinstance(pool, list)
    assert len(pool) >= 2  # noqa: PLR2004
    assert all(isinstance(line, str) and line.strip() for line in pool)


@pytest.mark.django_db
def test_pool_island_absent_for_anonymous_users() -> None:
    assert not ISLAND_RE.search(_home(Client()))


@pytest.mark.django_db
def test_pool_island_survives_online_compression(settings: SettingsWrapper) -> None:
    settings.COMPRESS_ENABLED = True
    settings.COMPRESS_OFFLINE = False

    client = Client()
    client.force_login(make_user("logo_spin_pool_compress"))
    html = _home(client)

    match = ISLAND_RE.search(html)
    assert match, "compression folded the #ee-logo-suchary island into the bundle"
    json.loads(match.group(1))
