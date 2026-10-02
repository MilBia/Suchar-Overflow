"""Regression guard for #436 — every `{% static %}` path must exist.

Production serves static files through `CompressedManifestStaticFilesStorage`
(`config/settings/production.py`). Under a manifest storage `{% static %}` on a
path missing from the manifest raises `ValueError` at render time, and since
every page (the 500 page included) extends `base.html`, one stale reference
there turned the whole site into 500s. `base.html` pointed `og:image` at
`images/favicons/favicon.ico` for months after that file was deleted.

The rest of the unit suite never notices: `config.settings.test` keeps the
default `StaticFilesStorage`, whose `url()` never checks that the file exists.
So this module runs `collectstatic` into a temporary `STATIC_ROOT` with
Django's `ManifestStaticFilesStorage` (`manifest_strict = True` by default) and
renders the pages against it. Django's own `setting_changed` receiver resets
`staticfiles_storage` when `STORAGES` / `STATIC_ROOT` change, so the override
takes effect and is undone on teardown. The same
`ManifestStaticFilesStorage` production uses (#463).
"""

import json
import re
import struct
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from django.conf import settings as django_settings
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.template.loader import get_template
from django.urls import reverse

from suchar_overflow.conftest import make_user

if TYPE_CHECKING:
    from django.test import Client
    from pytest_django.fixtures import Settings as SettingsWrapper

TEMPLATES_DIR = Path(django_settings.APPS_DIR) / "templates"
STATIC_TAG_RE = re.compile(r"""{%\s*static\s+['"]([^'"]+)['"]""")
OG_IMAGE_RE = re.compile(r'<meta property="og:image"\s+content="([^"]*)"')

# Every template tree that inherits base.html's head, plus the pages with
# their own static references. `"__self__"` is the logged-in username.
PAGES: list[tuple[str, dict[str, str]]] = [
    ("home", {}),
    ("suchary:list", {}),
    ("suchary:add", {}),
    ("achievements:list", {}),
    ("achievements:mine", {}),
    ("stats:leaderboard", {}),
    ("users:detail", {"username": "__self__"}),
    ("users:update", {}),
    ("password_change", {}),
]


@pytest.fixture
def manifest_storage(settings: SettingsWrapper, tmp_path: Path, request: pytest.FixtureRequest) -> None:
    settings.STATIC_ROOT = str(tmp_path / "static")
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": ("django.contrib.staticfiles.storage.ManifestStaticFilesStorage"),
        },
    }
    # A dev-server build (`node` service) leaves libraries' own `sourceMappingURL` comments in the
    # bundles, which the manifest storage rejects; only the production build is collected, and only by
    # the tests that ask for it.
    ignore = [] if request.node.get_closest_marker("needs_bundles") else ["webpack_bundles"]
    call_command("collectstatic", "--noinput", verbosity=0, ignore_patterns=ignore)


def test_every_template_static_literal_exists() -> None:
    """Cheap, page-independent check: each literal `{% static %}` path is found.

    Covers templates no rendering test below reaches (e.g. a page behind data
    the fixtures don't create).
    """
    missing = [
        (str(template.relative_to(TEMPLATES_DIR)), path)
        for template in TEMPLATES_DIR.rglob("*.html")
        for path in STATIC_TAG_RE.findall(template.read_text(encoding="utf-8"))
        if finders.find(path) is None
    ]
    assert not missing, missing


@pytest.mark.django_db
@pytest.mark.usefixtures("manifest_storage")
def test_pages_render_under_manifest_storage(client: Client) -> None:
    user = make_user("manifest_probe")

    # Anonymous first: the home page is the one a link-preview crawler hits.
    response = client.get(reverse("home"))
    assert response.status_code == 200

    client.force_login(user)
    for url_name, kwargs in PAGES:
        resolved = dict(kwargs)
        if resolved.get("username") == "__self__":
            resolved["username"] = user.username
        url = reverse(url_name, kwargs=resolved)
        response = client.get(url)
        assert response.status_code == 200, (url, response.status_code)


_STATS_FILE = Path(django_settings.BASE_DIR) / "webpack-stats.json"


def _built_by_dev_server() -> bool:
    if not _STATS_FILE.is_file():
        return False
    return any("vendors-node_modules" in name for name in json.loads(_STATS_FILE.read_text(encoding="utf-8"))["assets"])


@pytest.mark.skipif(not _STATS_FILE.is_file(), reason="needs a webpack build: `just build-js`")
@pytest.mark.skipif(
    _built_by_dev_server(),
    reason="the bundles are the dev server's: `just build-js` with `node` stopped",
)
@pytest.mark.needs_bundles
@pytest.mark.usefixtures("manifest_storage")
def test_built_bundles_survive_collectstatic() -> None:
    """The bundles the loader names exist in STATIC_ROOT after a manifest-storage `collectstatic` (#468).

    `collectstatic` post-processing resolves every `url()` in the CSS (the `/static/fonts/…` paths) and
    every `sourceMappingURL`, and fails hard on a missing target, so reaching this line already proves
    those. What it adds: each URL `render_bundle` will emit (the stats' `publicPath`) is a real file.
    """
    stats = json.loads(_STATS_FILE.read_text(encoding="utf-8"))
    assert stats["status"] == "done"
    static_root = Path(django_settings.STATIC_ROOT)
    assert stats["assets"]
    for asset in stats["assets"].values():
        relative = asset["publicPath"].removeprefix(django_settings.STATIC_URL)
        assert (static_root / relative).is_file(), asset["publicPath"]
    # The licence notices for the bundled libraries ship with them (#251).
    assert (static_root / "webpack_bundles" / "licenses.txt").is_file()


@pytest.mark.django_db
@pytest.mark.usefixtures("manifest_storage")
def test_500_page_renders_under_manifest_storage() -> None:
    # Exactly how django.views.defaults.server_error renders it (see
    # tests/test_error_pages.py): no request, no context processors. Under the
    # #436 bug this raised the same ValueError as the page that failed.
    html = get_template("500.html").render()

    og_image = OG_IMAGE_RE.search(html)
    assert og_image is not None
    # No request, so no origin to prepend — a bare hashed path, not "://…".
    assert og_image.group(1).startswith("/static/images/og-image.")


@pytest.mark.django_db
@pytest.mark.usefixtures("manifest_storage")
def test_og_image_is_an_absolute_hashed_url(client: Client) -> None:
    html = client.get(reverse("home")).content.decode()

    og_image = OG_IMAGE_RE.search(html)
    assert og_image is not None
    url = og_image.group(1)
    assert url.startswith("http://testserver/static/images/og-image."), url
    # The manifest storage inserted its content hash: og-image.<hash>.png.
    assert re.search(r"/og-image\.[0-9a-f]{12}\.png$", url), url


def test_og_image_size_matches_its_meta_tags() -> None:
    """base.html declares og:image:width/height; keep them true to the PNG (#440).

    Read straight from the PNG's IHDR chunk: 8-byte signature, then the chunk
    length and type, then big-endian width and height.
    """
    png = finders.find("images/og-image.png")
    assert png is not None
    header = Path(png).read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", header[16:24])

    base = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
    assert f'<meta property="og:image:width" content="{width}" />' in base
    assert f'<meta property="og:image:height" content="{height}" />' in base
    assert (width, height) == (1200, 630)
