"""Regression guard for issue #249 — no vendored asset references a source map.

`suchar_overflow/static/js/chart.umd.min.js` used to end with the jsdelivr
`dist/` banner line `//# sourceMappingURL=chart.umd.min.js.map`, but the `.map`
file is deliberately not vendored (see "Vendored JS libraries" in `CLAUDE.md`).
Production's `STORAGES["staticfiles"]` is
`whitenoise.storage.CompressedManifestStaticFilesStorage`, whose post-processing
pass resolves every `sourceMappingURL` reference in `*.js`/`*.css` and raises a
hard error when the target is missing:

    Post-processing 'js/chart.umd.min.js' failed!
    CommandError: The file 'js/chart.umd.min.js.map' could not be found ...

`compose/production/django/start` runs `collectstatic` under `set -o errexit`
*before* `compress --force`, so on that path the production container never
starts. Dev and test settings use a plain non-manifest storage, so `just test`
never exercised the post-processing pass — this was invisible to CI.

The chosen fix strips the `sourceMappingURL` line when vendoring rather than
adding the `.map` file. This test pins that rule so the next manual refresh of a
vendored file can't silently reintroduce the banner.
"""

from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).resolve().parent.parent / "suchar_overflow" / "static"

# Hand-vendored, already-minified third-party bundles — the only files that ship
# with an upstream `sourceMappingURL` banner. Hand-written project JS/CSS never
# has one.
VENDORED_ASSETS = (
    STATIC_DIR / "js" / "chart.umd.min.js",
    STATIC_DIR / "js" / "flatpickr.min.js",
    STATIC_DIR / "css" / "pages" / "flatpickr.min.css",
)


@pytest.mark.parametrize("asset", VENDORED_ASSETS, ids=lambda p: p.name)
def test_vendored_asset_exists(asset: Path) -> None:
    """Catch a rename/move before the content assertion reports a false pass."""
    assert asset.is_file(), asset


@pytest.mark.parametrize("asset", VENDORED_ASSETS, ids=lambda p: p.name)
def test_vendored_asset_has_no_sourcemap_reference(asset: Path) -> None:
    """No `sourceMappingURL` banner — it breaks production `collectstatic`."""
    text = asset.read_text(encoding="utf-8")
    assert "sourceMappingURL" not in text, (
        f"{asset.name} references a source map; strip the "
        f"`//# sourceMappingURL=...` line (see CLAUDE.md, issue #249)."
    )


def test_no_vendored_map_files_committed() -> None:
    """The `.map` files stay out of the repo — the strip rule is the contract."""
    stray = sorted(STATIC_DIR.rglob("*.map"))
    assert not stray, stray
