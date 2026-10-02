"""No shipped JS/CSS points at a source map that is not there (#249, #468).

Production's manifest storage (`ManifestStaticFilesStorage`) resolves every `sourceMappingURL` in a
`*.js`/`*.css` during `collectstatic` and fails hard on a missing target, which stops the production
container before it starts. Dev and test settings use a plain storage, so `just test` would never
notice.

- Nothing hand-written under `static/` carries the reference: the vendored libraries (whose upstream
  `dist/` builds end with the banner) are gone, they come from npm now.
- A webpack build (production devtool `source-map`) writes real `.map` files next to its bundles, so
  every reference in it must resolve. That half needs a build, so it is skipped without one; CI builds
  before the pytest step.
"""

import re
from pathlib import Path

import pytest

_STATIC = Path(__file__).resolve().parent.parent / "suchar_overflow" / "static"
_BUNDLES = _STATIC / "webpack_bundles"
_REFERENCE_RE = re.compile(r"(?://|/\*)# ?sourceMappingURL=([^\s*]+)")


def _tracked(pattern: str) -> list[Path]:
    return sorted(path for path in _STATIC.rglob(pattern) if _BUNDLES not in path.parents)


def test_hand_written_static_assets_have_no_sourcemap_reference() -> None:
    # Loops instead of parametrizing: there may be no tracked .js/.css left, and an empty parameter set skips.
    for asset in [*_tracked("*.js"), *_tracked("*.css")]:
        assert "sourceMappingURL" not in asset.read_text(encoding="utf-8"), asset


def test_no_map_files_are_committed_under_static() -> None:
    assert not _tracked("*.map")


@pytest.mark.skipif(not _BUNDLES.is_dir(), reason="needs a webpack build: `just build-js`")
@pytest.mark.skipif(
    any(_BUNDLES.glob("js/vendors-node_modules*")),
    reason="the dev server's bundles: stop `node`, then `just build-js`",
)
def test_every_source_map_reference_in_the_bundles_resolves() -> None:
    bundles = [*_BUNDLES.rglob("*.js"), *_BUNDLES.rglob("*.css")]
    assert bundles
    for bundle in bundles:
        for reference in _REFERENCE_RE.findall(bundle.read_text(encoding="utf-8")):
            assert (bundle.parent / reference).is_file(), f"{bundle.name} -> {reference}"
