"""E2E guard: a page in the back/forward cache must not hold its SSE stream (#428).

Chromium keeps a bfcache'd page's live ``EventSource`` connected. Over plain
HTTP/1.1 (the dev server) every link click in one tab then parked another
``/achievements/stream/`` connection, and ~5 clicks exhausted the browser's
6-connections-per-host limit — the next navigation hung until the bfcache
entries were evicted (~60 s). ``project.js`` now closes the stream on
``pagehide`` and reopens it on a persisted ``pageshow``.

Playwright launches Chromium with ``--disable-back-forward-cache`` by default,
so the shared ``browser`` fixture never restores a page from bfcache. This test
launches its own full-Chromium browser without that switch (keeping the
session-wide fixture untouched for every other test) and replaces
``EventSource`` with a recording fake: nothing reaches the live server's SSE
endpoint, and the open/close log lives in ``sessionStorage`` so it survives
the navigations.
"""

import json
from typing import TYPE_CHECKING

import pytest

from tests.e2e.conftest import TEST_PASSWORD

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any

    from playwright.sync_api import BrowserType
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.users.models import User as UserModel

_LOG_KEY = "__sse_log"

# Runs before any page script in every document. `docId` is per document, so a
# page restored from bfcache (same document — the init script does not re-run)
# keeps its id while a fresh load of the same URL gets a new one.
_FAKE_EVENT_SOURCE_JS = """
(() => {
  const docId = Math.random().toString(36).slice(2);
  let seq = 0;
  const log = (entry) => {
    const all = JSON.parse(sessionStorage.getItem('%(key)s') || '[]');
    all.push({ ...entry, doc: docId, path: location.pathname });
    sessionStorage.setItem('%(key)s', JSON.stringify(all));
  };
  class FakeEventSource {
    constructor(url) {
      this.url = url;
      this.readyState = FakeEventSource.OPEN;
      this.id = `${docId}:${++seq}`;
      log({ ev: 'open', id: this.id });
    }
    close() {
      if (this.readyState === FakeEventSource.CLOSED) return;
      this.readyState = FakeEventSource.CLOSED;
      log({ ev: 'close', id: this.id });
    }
    addEventListener() {}
    removeEventListener() {}
  }
  FakeEventSource.CONNECTING = 0;
  FakeEventSource.OPEN = 1;
  FakeEventSource.CLOSED = 2;
  window.EventSource = FakeEventSource;
  // Registered before project.js's own listeners, so each logs first.
  window.addEventListener('pagehide', (e) => {
    log({ ev: 'pagehide', persisted: e.persisted });
  });
  window.addEventListener('pageshow', (e) => {
    log({ ev: 'pageshow', persisted: e.persisted });
  });
})();
""" % {"key": _LOG_KEY}  # noqa: UP031


@pytest.fixture
def bfcache_page(
    browser_type: BrowserType,
    browser_type_launch_args: dict[str, Any],
    browser_context_args: dict[str, Any],
) -> Iterator[Page]:
    browser = browser_type.launch(
        **browser_type_launch_args,
        ignore_default_args=["--disable-back-forward-cache"],
        # The default headless shell refuses bfcache outright
        # (`BackForwardCacheDisabledForDelegate` in CDP's
        # Page.backForwardCacheNotUsed); full Chromium's new headless mode,
        # already installed by `playwright install chromium`, supports it.
        channel="chromium",
    )
    context = browser.new_context(**browser_context_args)
    context.add_init_script(_FAKE_EVENT_SOURCE_JS)
    page = context.new_page()
    yield page
    context.close()
    browser.close()


def _read_log(page: Page) -> list[dict[str, Any]]:
    return json.loads(
        page.evaluate(f"() => sessionStorage.getItem('{_LOG_KEY}') || '[]'"),
    )


def _wait_for_restore(page: Page) -> dict[str, Any]:
    """Return the persisted-``pageshow`` entry once the restore has logged it."""
    for _ in range(50):
        restores = [
            e for e in _read_log(page) if e["ev"] == "pageshow" and e["persisted"]
        ]
        if restores:
            return restores[-1]
        page.wait_for_timeout(100)
    pytest.fail(f"no page was restored from bfcache; log: {_read_log(page)}")


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_bfcached_page_releases_and_restores_its_stream(
    bfcache_page: Page,
    live_server: LiveServer,
    e2e_user: UserModel,  # noqa: ARG001
) -> None:
    page = bfcache_page
    page.goto(f"{live_server.url}/accounts/login/")
    page.fill("input[name='username']", "e2etestuser")
    page.fill("input[name='password']", TEST_PASSWORD)
    page.click("button[type='submit']")
    page.wait_for_url(f"{live_server.url}/**")

    page.goto(f"{live_server.url}/suchary/")
    page.goto(f"{live_server.url}/achievements/mine/")
    # A bfcache restore fires no `load`, so the default go_back() would time out.
    page.go_back(wait_until="commit")
    restore = _wait_for_restore(page)
    assert restore["path"] == "/suchary/"

    # Only the restored document's own entries: a normally unloaded page is
    # discarded without close(), which the fake can't observe.
    log = [
        e
        for e in _read_log(page)
        if e["doc"] == restore["doc"] and e["ev"] in {"open", "close", "pagehide"}
    ]
    # The first load's stream is closed while the page leaves for the bfcache,
    # then a fresh one opens on restore — from `pageshow` or a restore-time
    # `visibilitychange`, whichever runs first; never both.
    assert [e["ev"] for e in log] == ["open", "pagehide", "close", "open"]
    assert log[1]["persisted"], "the page did not enter the bfcache"
    first, closed, reopened = log[0], log[2], log[3]
    assert closed["id"] == first["id"]
    assert reopened["id"] != first["id"]
