"""Regression guard for issue #431 — the interpreter must not be CPython 3.14.0-3.14.4.

Those releases shipped an incremental cycle collector that was reverted in
3.14.5. Every Django ASGI request leaves its request graph (request, session,
messages storage, resolver match, ...) in a reference cycle that only the cycle
collector frees, and the incremental collector fell behind that rate: under
sustained load the uvicorn worker's RSS grew without bound (measured 135 ->
270 MB over 8 rounds on 3.14.2 with `config.settings.production`, flat ~101 MB
on 3.14.7 with the same load).

The image stayed on 3.14.2 because astral's `uv:python3.14-bookworm-slim` tag
stopped being rebuilt; the Dockerfiles now take Python from the official
`python:3.14-slim-bookworm` image instead. This test runs in the local/CI image
only, so it catches a stale cached base image or a switch back to a frozen tag
there. The production image is not covered and needs `just prod-build --pull`.
"""

import sys

_FIRST_FIXED = (3, 14, 5)


def test_python_is_not_an_incremental_gc_release() -> None:
    # pyproject pins requires-python to 3.14.x, the only line that shipped it.
    assert sys.version_info[:3] >= _FIRST_FIXED, (
        f"Python {sys.version.split()[0]} has the incremental GC reverted in "
        "3.14.5 (#431); rebuild the image with a fresh base: `just build --pull`"
    )
