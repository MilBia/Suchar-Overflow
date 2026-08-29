"""Regression guard for #205 — page-specific CSS/JS must go through compressor.

Seven page-specific blocks used to emit raw `<link>`/`<script>` tags, bypassing
`{% compress %}` even though `COMPRESS_ENABLED = True` in production. Wrapping
them has two failure modes that only appear with compression switched on, which
no other test in the unit suite does (dev/test keep `COMPRESS_ENABLED = False`,
so `{% compress %}` is a transparent passthrough):

1. **`defer` must survive.** `{% block javascript %}` lives in `<head>`, so every
   page script depends on `defer` to not run before the DOM exists. compressor
   renders its own `<script>` tag; if it dropped the attribute the scripts would
   break on every page.
2. **`json_script` output must stay outside the block.** `JsCompressor` treats a
   `<script>` without `src` as an inline hunk, minifies it and concatenates it
   into the bundle — the `id="..."` the page reads with `getElementById` would be
   gone. Its content also varies per request, which is a guaranteed hash mismatch
   under `COMPRESS_OFFLINE = True`.

Deliberately does not relocate `COMPRESS_ROOT`: compressor binds its storage
lazily once per process, so an override would only take effect if this happened
to be the first test in the run to touch compressor. Output lands in
`STATIC_ROOT`/CACHE (gitignored), the same place `manage.py compress` writes.
"""

import re
from typing import TYPE_CHECKING

import pytest
from compressor.cache import flush_offline_manifest
from compressor.storage import default_offline_manifest_storage
from django.conf import settings as django_settings
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse

from suchar_overflow.conftest import make_user

if TYPE_CHECKING:
    from django.test import Client
    from pytest_django.fixtures import Settings as SettingsWrapper

SCRIPT_TAG_RE = re.compile(r"<script\b(?=[^>]*\bsrc=)[^>]*>", re.IGNORECASE)
SCRIPT_SRC_RE = re.compile(r'\bsrc="([^"]+)"', re.IGNORECASE)
LINK_TAG_RE = re.compile(
    r'<link\b(?=[^>]*\brel="stylesheet")[^>]*\bhref="([^"]+)"',
    re.IGNORECASE,
)


def _render(client: Client, settings: SettingsWrapper, url: str) -> str:
    """GET ``url`` with online compression enabled and return the HTML."""
    settings.COMPRESS_ENABLED = True
    settings.COMPRESS_OFFLINE = False
    # compressor caches "already written" per content hash; clearing forces a
    # real rewrite so a stale bundle can't mask a regression.
    cache.clear()

    response = client.get(url)
    assert response.status_code == 200, (url, response.status_code)  # noqa: PLR2004
    return response.content.decode()


def _script_tags(html: str) -> list[str]:
    return SCRIPT_TAG_RE.findall(html)


def _script_srcs(html: str) -> list[str]:
    return [SCRIPT_SRC_RE.search(tag).group(1) for tag in _script_tags(html)]  # type: ignore[union-attr]


@pytest.fixture
def logged_in_client(client: Client) -> Client:
    client.force_login(make_user("compress_probe"))
    return client


# Bundle every logged-in page inherits from base.html: project.js.
# hidden_achievements.js moved to page-specific templates in #207 (it is
# only relevant to pages with a DOM/URL match for one of its 5 trackers) —
# see the per-page bundle counts below.
BASE_JS_BUNDLES = 1

# URL name, kwargs, and the number of separate compress bundles the page is
# expected to emit — base.html's inherited bundles plus the page's own
# blocks. Leaderboard adds two (the vendored chart library and its own
# script, kept apart by the json_script between them); suchary:list and
# suchary:add each add two (hidden_achievements.js — see #207 — plus their
# existing page script); achievements:list adds one (hidden_achievements.js
# only).
JS_PAGES: list[tuple[str, dict[str, str], int]] = [
    ("stats:leaderboard", {}, BASE_JS_BUNDLES + 2),
    ("suchary:list", {}, BASE_JS_BUNDLES + 2),
    ("suchary:add", {}, BASE_JS_BUNDLES + 2),
    ("achievements:list", {}, BASE_JS_BUNDLES + 1),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("url_name", "kwargs", "expected_bundles"), JS_PAGES)
def test_page_js_is_compressed_and_keeps_defer(
    logged_in_client: Client,
    settings: SettingsWrapper,
    url_name: str,
    kwargs: dict[str, str],
    expected_bundles: int,
) -> None:
    """Every `<script src>` is a CACHE bundle and every one keeps `defer`."""
    html = _render(logged_in_client, settings, reverse(url_name, kwargs=kwargs))

    srcs = _script_srcs(html)
    assert srcs, "page emitted no external scripts at all"
    uncompressed = [src for src in srcs if not src.startswith("/static/CACHE/js/")]
    assert not uncompressed, uncompressed
    assert len(set(srcs)) == expected_bundles, srcs

    missing_defer = [tag for tag in _script_tags(html) if " defer" not in tag]
    assert not missing_defer, missing_defer


@pytest.mark.django_db
def test_user_detail_js_is_compressed_and_keeps_defer(
    client: Client,
    settings: SettingsWrapper,
) -> None:
    """Same as above for the profile page, which must be fetched by username."""
    user = make_user("compress_profile")
    client.force_login(user)
    html = _render(
        client,
        settings,
        reverse("users:detail", kwargs={"username": user.username}),
    )

    srcs = _script_srcs(html)
    uncompressed = [src for src in srcs if not src.startswith("/static/CACHE/js/")]
    assert not uncompressed, uncompressed
    # base.html's bundle, plus the vendored chart library and the page's own
    # script, which the json_script blocks keep in separate ones.
    # hidden_achievements.js is deliberately absent here (#207): the profile
    # page's `latest_suchary` is sliced to 5 cards, so the only tracker whose
    # DOM it matches (Recenzent Totalny, needs 20 hovered cards) can never
    # fire on this page.
    assert len(set(srcs)) == BASE_JS_BUNDLES + 2, srcs
    missing_defer = [tag for tag in _script_tags(html) if " defer" not in tag]
    assert not missing_defer, missing_defer


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url_name", "kwargs", "json_ids"),
    [
        ("stats:leaderboard", {}, ["chart-datasets-data"]),
        (
            "users:detail",
            {"username": "__self__"},
            ["activity-labels-data", "activity-values-data", "reception-data-data"],
        ),
    ],
)
def test_json_script_survives_compression(
    client: Client,
    settings: SettingsWrapper,
    url_name: str,
    kwargs: dict[str, str],
    json_ids: list[str],
) -> None:
    """`json_script` blocks stay outside `{% compress %}`, so their ids survive.

    Pulled into a compress block they would be minified into the bundle and the
    `getElementById` lookups in leaderboard.js / user_detail.js would return null.
    """
    user = make_user("compress_json")
    client.force_login(user)
    if kwargs.get("username") == "__self__":
        kwargs = {"username": user.username}

    html = _render(client, settings, reverse(url_name, kwargs=kwargs))

    for json_id in json_ids:
        assert f'id="{json_id}"' in html, json_id


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url_name", "expected_bundles"),
    [
        ("achievements:list", 2),
        ("achievements:mine", 2),
        ("suchary:add", 2),
    ],
)
def test_page_css_is_compressed(
    logged_in_client: Client,
    settings: SettingsWrapper,
    url_name: str,
    expected_bundles: int,
) -> None:
    """Page-specific stylesheets collapse into their own CACHE bundle.

    base.html's block is one bundle, the page's own block is the second — they
    are deliberately *not* merged, so each template keeps its own output file.
    """
    html = _render(logged_in_client, settings, reverse(url_name))

    hrefs = LINK_TAG_RE.findall(html)
    uncompressed = [href for href in hrefs if not href.startswith("/static/CACHE/css/")]
    assert not uncompressed, uncompressed
    assert len(set(hrefs)) == expected_bundles, hrefs


# Every page that gained its own `{% compress %}` block in #205, plus the home
# page as a control. `"__self__"` is resolved to the logged-in user's username.
OFFLINE_PAGES: list[tuple[str, dict[str, str]]] = [
    ("home", {}),
    ("achievements:list", {}),
    ("achievements:mine", {}),
    ("suchary:add", {}),
    ("suchary:list", {}),
    ("stats:leaderboard", {}),
    ("users:detail", {"username": "__self__"}),
    ("users:update", {}),
]


@pytest.mark.django_db
def test_pages_render_under_offline_compression(
    client: Client,
    settings: SettingsWrapper,
) -> None:
    """Build the offline manifest, then render every #205 page against it.

    This is the only automated guard for the `{{ block.super }}` rule: pulling
    it inside a `{% compress %}` block still lets `compress --force` report
    success, and the `OfflineGenerationError` only surfaces at render time when
    the runtime hash misses the manifest. The online tests above never enter
    that code path (`_render` pins `COMPRESS_OFFLINE = False`).

    Both the in-memory manifest cache and the on-disk `manifest.json` (which
    `staticfiles/CACHE/` keeps around — it is a bind mount, not per-run) are
    cleared on teardown so a later test or a dev `manage.py` run can't read a
    manifest built for this one weird settings combination.
    """
    user = make_user("compress_offline")
    client.force_login(user)

    settings.COMPRESS_ENABLED = True
    settings.COMPRESS_OFFLINE = True
    cache.clear()
    try:
        call_command("compress", "--force", verbosity=0)
        for url_name, kwargs in OFFLINE_PAGES:
            resolved = dict(kwargs)
            if resolved.get("username") == "__self__":
                resolved["username"] = user.username
            url = reverse(url_name, kwargs=resolved)
            response = client.get(url)
            assert response.status_code == 200, (url, response.status_code)  # noqa: PLR2004
    finally:
        # django-stubs doesn't know compressor's settings; "manifest.json" is
        # its documented default for COMPRESS_OFFLINE_MANIFEST.
        manifest = getattr(
            django_settings,
            "COMPRESS_OFFLINE_MANIFEST",
            "manifest.json",
        )
        if default_offline_manifest_storage.exists(manifest):
            default_offline_manifest_storage.delete(manifest)
        flush_offline_manifest()
