"""E2E test for the developer console easter egg (features/console_egg.js, #287).

Loads a real page and inspects what the browser devtools console received. The
egg is pure delight — no achievement, no DOM, no network — so the console entry
is the only surface to assert. It also checks the two guards: logged-in only,
and once per browser session.
"""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import ConsoleMessage
    from playwright.sync_api import Page
    from pytest_django.live_server_helper import LiveServer

REPO_URL = "https://github.com/MilBia/Suchar-Overflow"
SESSION_KEY = "ee_console_shown"

# A self-resolving Promise, not a bare boolean expression: Playwright would
# rebuild a boolean predicate with in-page eval for its polling loop, which the
# app CSP (no 'unsafe-eval') blocks. A Promise resolves inside one CDP evaluate
# call that bypasses page CSP (see tests/e2e/test_hidden_achievements.py).
_READY_JS = """
    new Promise((resolve) => {
        const check = () => {
            if (window.__consoleEggReady === true) resolve(true);
            else setTimeout(check, 50);
        };
        check();
    })
"""


def _capture_console(page: Page) -> list[str]:
    messages: list[str] = []
    page.on("console", lambda msg: messages.append(_text(msg)))
    return messages


def _text(msg: ConsoleMessage) -> str:
    try:
        return msg.text
    except Exception:  # noqa: BLE001 - defensive: only used to build a haystack
        return ""


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_console_egg_greets_logged_in_developer(
    page: Page,
    live_server: LiveServer,
) -> None:
    messages = _capture_console(page)

    # The `login` fixture already landed on "/", which may have fired the egg
    # before the listener was attached — clear the session latch and reload.
    page.evaluate(f"() => sessionStorage.removeItem({SESSION_KEY!r})")
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    haystack = "\n".join(messages)
    assert REPO_URL in haystack
    assert "Suchar Overflow" in haystack


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("login")
def test_console_egg_fires_once_per_session(
    page: Page,
    live_server: LiveServer,
) -> None:
    messages = _capture_console(page)

    page.evaluate(f"() => sessionStorage.removeItem({SESSION_KEY!r})")
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)
    assert any(REPO_URL in m for m in messages)

    messages.clear()
    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)
    assert not any(REPO_URL in m for m in messages)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_console_egg_silent_for_anonymous_visitor(
    page: Page,
    live_server: LiveServer,
) -> None:
    messages = _capture_console(page)

    page.goto(f"{live_server.url}/")
    page.wait_for_function(_READY_JS, timeout=12_000)

    assert not any(REPO_URL in m for m in messages)
