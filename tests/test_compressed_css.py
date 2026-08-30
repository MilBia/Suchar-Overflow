"""Regression guard for #204 — the global CSS bundle must be self-contained.

`base.html` composes the global stylesheet from ~21 separate `<link>` tags
inside a single `{% compress css %}` block (the two `pages/*.css` sheets moved
to page-specific blocks in #250). Before #204 the same modules were
pulled in by CSS `@import` from a single `css/base.css`. django-compressor's
filters (`CssAbsoluteFilter`, `RCSSMinFilter`) neither resolve nor inline a
bare `@import 'x.css'` — they copy it into the output
(`/static/CACHE/css/output.<hash>.css`) verbatim, so the compressor emits its
one bundle *plus* ~22 render-blocking requests the browser can only discover
sequentially, defeating the point of compressing at all.

These tests run under the default, non-manifest `StaticFilesStorage`, where a
copied relative `@import` additionally 404s from `CACHE/css/`. Production runs a
`CompressedManifestStaticFilesStorage` whose `collectstatic` pass rewrites
`@import 'x'` → `@import url("x.<hash>")` before `compress` runs, so there the
imports happen to resolve — meaning this file guards "no `@import` survives into
the bundle" (plus absolutised `url(...)` and cascade order), not a reproduction
of any particular production render.

Nothing else in the unit suite exercises `COMPRESS_ENABLED = True` (dev and test
settings keep it off, so `{% compress %}` is a transparent passthrough), so this
breakage was invisible to CI. These tests turn compression on for a single
request and assert on the bundle that comes out.
"""

import re
from typing import TYPE_CHECKING

import pytest
from compressor.storage import default_storage as compressor_storage
from django.core.cache import cache
from django.test import Client

if TYPE_CHECKING:
    from pytest_django.fixtures import Settings

# Attribute order differs between the raw template tags and compressor's
# generated tag, so match any <link ... rel="stylesheet" ...> and pull its href.
LINK_RE = re.compile(
    r'<link(?=[^>]*\brel="stylesheet")[^>]*\bhref="([^"]+)"',
    re.IGNORECASE,
)


@pytest.fixture
def compressed_home(settings: Settings) -> str:
    """GET / with compression on and return the single bundled CSS file body.

    Deliberately does not relocate ``COMPRESS_ROOT``: compressor binds its
    storage lazily once per process, so an override would only take effect if
    this happened to be the first test in the run to touch compressor. The
    bundle is instead read back through compressor's own storage, wherever it
    put it (``STATIC_ROOT``/CACHE — gitignored, same place ``manage.py
    compress`` writes).
    """
    settings.COMPRESS_ENABLED = True
    settings.COMPRESS_OFFLINE = False
    # compressor remembers "already written" per content hash in the cache;
    # clearing forces a real rewrite so a stale file can't mask a regression.
    cache.clear()

    response = Client().get("/")
    assert response.status_code == 200  # noqa: PLR2004

    hrefs = LINK_RE.findall(response.content.decode())
    # base.html's {% compress css %} block must collapse to exactly one request.
    assert len(hrefs) == 1, hrefs
    href = hrefs[0]
    assert href.startswith("/static/CACHE/css/"), href

    with compressor_storage.open(href.removeprefix("/static/")) as fh:
        return fh.read().decode()


@pytest.mark.django_db
def test_compressed_bundle_has_no_css_imports(compressed_home: str) -> None:
    """No `@import` survives into the bundle — they would 404 from CACHE/css/."""
    assert "@import" not in compressed_home


@pytest.mark.django_db
def test_compressed_bundle_rewrites_relative_urls(compressed_home: str) -> None:
    """CssAbsoluteFilter must absolutise fonts.css's `../fonts/*.woff2` refs.

    Only fires when each module is its own compressor input; an `@import`ed
    file is never seen by the filter.
    """
    assert "/static/fonts/Inter-Regular.woff2" in compressed_home
    assert "../fonts/" not in compressed_home


@pytest.mark.django_db
def test_compressed_bundle_preserves_cascade_order(compressed_home: str) -> None:
    """Concatenation order == the `<link>` order == the documented cascade.

    utilities.css and components/forms.css both carry comments relying on
    utilities → components → project ordering; a reshuffled block would break
    them silently (all use the same specificity). The page-specific sheets
    that also relied on this (pages/leaderboard.css, pages/profile.css) left
    the global bundle in #250 and now load from their own blocks after it.
    """
    markers = [
        "@font-face",  # fonts.css — first
        "--hue-primary:",  # variables.css — the sole declaration; `var(...)` uses
        # elsewhere lack the trailing colon, so this can't false-match
        ".ms-auto",  # utilities.css — before components
        ".invalid-feedback",  # components/forms.css — after utilities
        ".theme-transition",  # project.css — last
    ]
    offsets = [compressed_home.find(m) for m in markers]
    assert all(o != -1 for o in offsets), dict(zip(markers, offsets, strict=True))
    assert offsets == sorted(offsets), dict(zip(markers, offsets, strict=True))
