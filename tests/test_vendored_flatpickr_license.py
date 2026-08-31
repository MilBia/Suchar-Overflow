"""Regression guard for issue #251 — flatpickr's MIT notice must ship.

Since #238 `suchar_overflow/static/js/flatpickr.min.js` goes through
`RJSMinFilter` (`COMPRESS_JS_FILTERS`), which keeps only bang comments (`/*!`).
flatpickr's banner is a plain `/*` comment, so it is stripped from the served
`/static/CACHE/` bundle — the MIT licence text then appears in nothing
production serves. `flatpickr.LICENSE.txt` sits next to the bundle to carry the
notice; these tests pin that it stays present, complete, and version-matched so
the next manual refresh of `flatpickr.min.js` can't silently drop it.

Chart.js needs no equivalent file: its banner is `/*!`, which `rjsmin` keeps.
"""

import re
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "suchar_overflow" / "static"
BUNDLE = STATIC_DIR / "js" / "flatpickr.min.js"
LICENSE_FILE = STATIC_DIR / "js" / "flatpickr.LICENSE.txt"

_VERSION_RE = re.compile(r"flatpickr v(\d+\.\d+\.\d+)")
_PERMISSION_NOTICE = (
    "The above copyright notice and this permission notice shall be included in all"
)


def test_license_file_sits_next_to_the_bundle() -> None:
    """The notice must be collected by `collectstatic` right beside the JS."""
    assert LICENSE_FILE.is_file(), LICENSE_FILE
    assert LICENSE_FILE.parent == BUNDLE.parent


def test_license_file_carries_the_full_mit_notice() -> None:
    """MIT requires the copyright line *and* the permission notice verbatim."""
    text = LICENSE_FILE.read_text(encoding="utf-8")
    assert "MIT License" in text
    assert "Copyright (c) 2017 Gregory Petrosyan" in text
    assert _PERMISSION_NOTICE in text


def test_license_version_matches_the_vendored_bundle() -> None:
    """A refresh of `flatpickr.min.js` must refresh this file in lockstep."""
    # Search the whole file, not `.splitlines()[0]` — an empty file would raise
    # IndexError before the assertion below could report it. The version token
    # only appears in the banner / marker line of each file anyway.
    bundle_match = _VERSION_RE.search(BUNDLE.read_text(encoding="utf-8"))
    license_match = _VERSION_RE.search(LICENSE_FILE.read_text(encoding="utf-8"))

    assert bundle_match, "no `flatpickr v<x.y.z>` banner in flatpickr.min.js"
    assert license_match, "no `flatpickr v<x.y.z>` marker in flatpickr.LICENSE.txt"
    assert bundle_match.group(1) == license_match.group(1), (
        f"flatpickr.LICENSE.txt marks v{license_match.group(1)} but "
        f"flatpickr.min.js is v{bundle_match.group(1)} — refresh the notice "
        f"(see CLAUDE.md, 'Vendored JS libraries')."
    )
