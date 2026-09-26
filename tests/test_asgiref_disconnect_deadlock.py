"""Regression guard for issue #426 — a client disconnect must not freeze the server.

Django's `ASGIHandler.__call__` wraps every request in asgiref's
`ThreadSensitiveContext`. `WhiteNoiseMiddleware` is sync-only, so Django runs it
in that context's executor thread, and it reaches the rest of the (async) stack
through `async_to_sync`. When the client disconnects while WhiteNoise is still
in its sync code, Django cancels the request task and leaves the context. Before
asgiref 3.12.0, `ThreadSensitiveContext.__aexit__` then joined the executor
thread *on the event loop*, while that thread was about to wait on the same loop
for `async_to_sync`: the worker deadlocked for good, with no log line and no
traceback. Only a restart brought it back (upstream django/asgiref#535).

The script below is that sequence without Django, so the test does not depend
on which request or middleware happens to hit the race. It runs in a
subprocess because a regression hangs the event loop, and no in-process
timeout can fire on a blocked loop.
"""

import subprocess
import sys
import textwrap

_SCRIPT = textwrap.dedent(
    """
    import asyncio
    import time

    from asgiref.sync import ThreadSensitiveContext
    from asgiref.sync import async_to_sync
    from asgiref.sync import sync_to_async


    async def rest_of_stack():
        await asyncio.sleep(0)


    def sync_middleware():
        time.sleep(0.3)  # still in sync code when the client goes away
        async_to_sync(rest_of_stack)()  # now needs the event loop


    async def request():
        async with ThreadSensitiveContext():
            task = asyncio.create_task(sync_to_async(sync_middleware)())
            await asyncio.sleep(0.1)
            task.cancel()  # what ASGIHandler does on http.disconnect
            try:
                await task
            except asyncio.CancelledError:
                pass


    asyncio.run(request())
    print("survived")
    """,
)


def test_disconnect_during_sync_middleware_does_not_deadlock() -> None:
    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _SCRIPT],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        msg = "event loop deadlocked leaving ThreadSensitiveContext (#426)"
        raise AssertionError(msg) from None
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "survived"
