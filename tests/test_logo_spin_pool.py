"""Regression guard for the logo-spin easter egg's meta-suchar pool (#285).

`features/logo_spin.js` reads the pool from a JSON data island
(`#ee-logo-suchary`) that `base.html` emits for authenticated users. Two things
must hold and neither is covered by the JS/E2E suites:

1. The island renders **valid JSON** — a non-empty list of non-empty strings.
   The strings go through `|escapejs` (not `|json_script`, which needs a context
   variable base.html has no view to build), so a bad escape would surface as a
   `JSONDecodeError` here rather than a silent client-side parse failure.
2. The island stays a **plain inline `<script>` in the page**, not part of a webpack bundle: its text
   is translated per request by `{% trans %}`, which a build step could not do.
"""

import json
import re

import pytest
from django.test import Client
from django.urls import reverse

from suchar_overflow.conftest import make_user

# Attribute-order-tolerant: djlint (or a future formatter) may reorder `id` and
# `type` or wrap the tag — all that matters is a <script> carrying this id.
ISLAND_RE = re.compile(
    r"<script\b[^>]*\bid=[\"']ee-logo-suchary[\"'][^>]*>(.*?)</script>",
    re.DOTALL,
)


def _home(client: Client) -> str:
    response = client.get(reverse("home"))
    assert response.status_code == 200, response.status_code
    return response.content.decode()


@pytest.mark.django_db
def test_pool_island_is_valid_json_list_of_strings() -> None:
    client = Client()
    client.force_login(make_user("logo_spin_pool"))

    match = ISLAND_RE.search(_home(client))
    assert match, "the #ee-logo-suchary data island is missing for a logged-in user"

    pool = json.loads(match.group(1))
    assert isinstance(pool, list)
    assert len(pool) >= 2
    assert all(isinstance(line, str) and line.strip() for line in pool)


@pytest.mark.django_db
def test_pool_island_absent_for_anonymous_users() -> None:
    assert not ISLAND_RE.search(_home(Client()))
