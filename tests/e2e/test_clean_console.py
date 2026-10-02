"""Every page loads its bundles without a console error or a CSP violation (#468).

The bundles are external `<script src>`/`<link>` tags from the site's own origin, so the policy
(`script-src 'self' <nonce>`) needs no change — this is the check that stays true if a loader option
or a library ever starts to inject an inline script, an `eval`, or a cross-origin socket (the dev
server's live-reload client is the usual suspect, and is not part of the production build).

It also pins that the global `project` entry is evaluated once per page: a page entry that copied
the shared modules instead of sharing them would open a second SSE connection.
"""

from typing import TYPE_CHECKING

import pytest

# A real import: Playwright inspects the handler's annotations when it is registered.
from playwright.sync_api import ConsoleMessage  # noqa: TC002

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

    from suchar_overflow.suchary.models import Suchar
    from suchar_overflow.users.models import User

_VIOLATION_HOOK = """
window.__cspViolations = [];
document.addEventListener('securitypolicyviolation', (event) => {
    window.__cspViolations.push(event.violatedDirective + ' ' + event.blockedURI);
});
window.__eventSources = 0;
const NativeEventSource = window.EventSource;
window.EventSource = function (...args) {
    window.__eventSources += 1;
    return new NativeEventSource(...args);
};
window.EventSource.prototype = NativeEventSource.prototype;
"""

# conftest's `block_sse_stream` aborts the stream request on purpose; the browser logs that as a failed load.
_EXPECTED_NOISE = ("achievements/stream", "Achievement stream error", "ERR_FAILED")


def _visit(page: Page, url: str, tolerate: tuple[str, ...] = ()) -> tuple[list[str], list[str]]:
    errors: list[str] = []

    def on_console(message: ConsoleMessage) -> None:
        if message.type != "error" or any(noise in message.text for noise in (*_EXPECTED_NOISE, *tolerate)):
            return
        errors.append(f"console.{message.type}: {message.text}")

    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on("console", on_console)
    page.add_init_script(_VIOLATION_HOOK)
    page.goto(url, wait_until="load")
    # `load` already implies readyState 'complete', so wait for the one thing that is still async: the
    # hidden-achievements init, on the pages that load that bundle.
    page.wait_for_function(
        "() => window.__hiddenAchievementsReady !== undefined"
        " || !document.querySelector('script[src*=\"hidden_achievements\"]')"
    )
    violations = page.evaluate("window.__cspViolations")
    return errors, violations


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "path",
    ["/", "/about/", "/accounts/login/", "/nie-ma-takiej-strony/"],
)
def test_anonymous_pages_are_clean(page: Page, live_server: LiveServer, path: str) -> None:
    # The browser logs a 404 page's own document load as a console error; that is the page working.
    tolerate = ("status of 404",) if path == "/nie-ma-takiej-strony/" else ()
    errors, violations = _visit(page, f"{live_server.url}{path}", tolerate)
    assert not errors, errors
    assert not violations, violations


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "path",
    [
        "/suchary/",
        "/suchary/add/",
        "/stats/leaderboard/",
        "/achievements/",
        "/achievements/mine/",
        "/users/e2etestuser/",
        # The only page besides the profile that renders the `dashboard` entry on its own.
        "/users/~update/",
    ],
)
def test_logged_in_pages_are_clean(
    login: Page,
    live_server: LiveServer,
    published_suchar: Suchar,  # noqa: ARG001
    e2e_user: User,  # noqa: ARG001
    path: str,
) -> None:
    errors, violations = _visit(login, f"{live_server.url}{path}")
    assert not errors, errors
    assert not violations, violations


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_suchar_list_opens_exactly_one_event_source(
    login: Page,
    live_server: LiveServer,
    published_suchar: Suchar,  # noqa: ARG001
) -> None:
    """`/suchary/` loads `project`, `hidden_achievements` and `voting`: one stream, not one per entry."""
    _visit(login, f"{live_server.url}/suchary/")
    assert login.evaluate("window.__eventSources") == 1
    # The shared modules are one instance: the page entries see the same `easterEggs` the project entry made.
    assert login.evaluate("typeof window.easterEggs === 'object' && typeof window.showToast === 'function'")
