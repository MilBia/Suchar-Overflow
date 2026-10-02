"""The global stylesheet is composed in ``webpack/src/scss/project.scss`` (#467).

It replaces ``tests/test_compressed_css.py`` (#204), which guarded the ``{% compress css %}``
block. The same two properties matter now, and both are checked on the source so the test needs
no build:

- **Position is the cascade order.** ``utilities`` and ``components/forms`` carry comments that
  depend on it, so the ``@use`` list must keep fonts → core → components → site.
- **No module is left out or loaded twice.** A partial nobody ``@use``s would silently drop its
  rules from the bundle.

Plus the font URLs (absolute ``/static/fonts/…``: css-loader is told to leave them alone, the
manifest storage hashes them) and the page sheets staying out of the global bundle (#250).
"""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCSS = _ROOT / "webpack/src/scss"
_PROJECT = (_SCSS / "project.scss").read_text(encoding="utf-8")
_USE_RE = re.compile(r"^@use '([^']+)';", re.MULTILINE)

_CANONICAL_ORDER = [
    "fonts",
    "variables",
    "reset",
    "typography",
    "layout",
    "utilities",
    "components/buttons",
    "components/navbar",
    "components/cards",
    "components/forms",
    "components/modals",
    "components/toasts",
    "components/list_group",
    "components/pagination",
    "components/dropdowns",
    "components/voting",
    "components/heatmap",
    "components/achievement-badge",
    "components/suchar-card",
    "components/footer",
    "components/error-page",
    "site",
]


def test_global_modules_keep_the_canonical_cascade_order() -> None:
    assert _USE_RE.findall(_PROJECT) == _CANONICAL_ORDER


def _module_name(path: Path) -> str:
    return path.relative_to(_SCSS).with_name(path.name.removeprefix("_")).with_suffix("").as_posix()


def test_every_partial_is_used_exactly_once() -> None:
    partials = {_module_name(p) for pattern in ("_*.scss", "components/_*.scss") for p in _SCSS.glob(pattern)}
    used = _USE_RE.findall(_PROJECT)
    assert sorted(used) == sorted(partials)
    assert len(used) == len(set(used))


def test_no_deprecated_sass_import_anywhere() -> None:
    for path in _SCSS.rglob("*.scss"):
        text = path.read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        assert not re.search(r"^\s*@import\b", code, re.MULTILINE), f"{path.relative_to(_ROOT)} uses @import"


def test_page_sheets_stay_out_of_the_global_bundle() -> None:
    # They load from their own entries after it, so their `!important` rules win on order (#250).
    assert "pages/" not in _PROJECT
    assert {p.name for p in (_SCSS / "pages").glob("*.scss")} == {
        "achievement-page.scss",
        "leaderboard.scss",
        "profile.scss",
        "suchar_form.scss",
    }


def test_cascade_markers_appear_in_order_in_the_sources() -> None:
    # Same markers the compressor-era test used, found by walking the @use list.
    markers = ["@font-face", "--hue-primary:", ".ms-auto", ".invalid-feedback", ".theme-transition"]
    text = "".join(
        next(_SCSS.glob(f"{Path(name).parent}/_{Path(name).name}.scss")).read_text(encoding="utf-8")
        for name in _USE_RE.findall(_PROJECT)
    )
    offsets = [text.find(m) for m in markers]
    assert all(o != -1 for o in offsets), dict(zip(markers, offsets, strict=True))
    assert offsets == sorted(offsets), dict(zip(markers, offsets, strict=True))


def test_font_urls_are_absolute_static_paths_to_existing_files() -> None:
    fonts = (_SCSS / "_fonts.scss").read_text(encoding="utf-8")
    assert "../fonts/" not in fonts
    urls = re.findall(r"url\('([^']+)'\)", fonts)
    assert urls
    for url in urls:
        assert url.startswith("/static/fonts/"), url
        assert (_ROOT / "suchar_overflow/static" / url.removeprefix("/static/")).is_file(), url
