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
takes effect and is undone on teardown. Plain `ManifestStaticFilesStorage`
rather than whitenoise's compressed subclass: the manifest lookup is the same,
and skipping the gzip/brotli pass keeps `collectstatic` fast.
"""

import re
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
def manifest_storage(settings: SettingsWrapper, tmp_path: Path) -> None:
    settings.STATIC_ROOT = str(tmp_path / "static")
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": (
                "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
            ),
        },
    }
    call_command("collectstatic", "--noinput", verbosity=0)


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
    assert response.status_code == 200  # noqa: PLR2004

    client.force_login(user)
    for url_name, kwargs in PAGES:
        resolved = dict(kwargs)
        if resolved.get("username") == "__self__":
            resolved["username"] = user.username
        url = reverse(url_name, kwargs=resolved)
        response = client.get(url)
        assert response.status_code == 200, (url, response.status_code)  # noqa: PLR2004


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
    assert og_image.group(1).startswith("/static/images/favicons/favicon.")


@pytest.mark.django_db
@pytest.mark.usefixtures("manifest_storage")
def test_og_image_is_an_absolute_hashed_url(client: Client) -> None:
    html = client.get(reverse("home")).content.decode()

    og_image = OG_IMAGE_RE.search(html)
    assert og_image is not None
    url = og_image.group(1)
    assert url.startswith("http://testserver/static/images/favicons/favicon."), url
    # The manifest storage inserted its content hash: favicon.<hash>.svg.
    assert re.search(r"/favicon\.[0-9a-f]{12}\.svg$", url), url
