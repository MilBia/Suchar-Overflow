"""Regression guard for issue #403 — the dev server must survive a reload.

`compose/local/django/start` runs `uvicorn --reload`. uvicorn's
`timeout_graceful_shutdown` defaults to no timeout, and every open
`/achievements/stream/` SSE connection is a response that never completes, so a
reload with a browser tab open waited for it forever: the reloader blocks
joining the old worker and new requests hang until the container is restarted.
"""

import re
from pathlib import Path

START_SCRIPT = (
    Path(__file__).resolve().parent.parent / "compose" / "local" / "django" / "start"
)

_TIMEOUT_RE = re.compile(r"--timeout-graceful-shutdown[ =](\d+)")


def test_local_uvicorn_bounds_graceful_shutdown() -> None:
    """A short bound lets the reload cancel SSE streams; clients reconnect."""
    text = START_SCRIPT.read_text(encoding="utf-8")
    start = text.find("exec uvicorn")
    assert start != -1, "local start script no longer execs uvicorn"
    uvicorn_cmd = text[start:]
    match = _TIMEOUT_RE.search(uvicorn_cmd)
    assert match, "local uvicorn must pass --timeout-graceful-shutdown (#403)"
    assert 0 < int(match.group(1)) <= 10  # noqa: PLR2004
