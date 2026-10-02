"""Helpers for the local dev settings."""

import contextlib
import socket
import time


class InternalIPs(list):
    """``INTERNAL_IPS`` that also accepts the ``node`` service's address, looked up lazily.

    The ``node`` container starts after ``django`` (it waits for its healthcheck), so its address
    can't be read when settings are imported; and it changes whenever compose recreates it. The
    lookup runs only for an address the static entries don't already cover, and its result is kept
    for ``ttl`` seconds (the toolbar asks on every request, and DNS runs on the event loop).
    """

    ttl = 30.0
    _looked_up_at = float("-inf")
    _node_ips: tuple[str, ...] = ()

    def _node_addresses(self) -> tuple[str, ...]:
        now = time.monotonic()
        if now - self._looked_up_at >= self.ttl:
            self._node_ips = ()
            with contextlib.suppress(OSError):
                self._node_ips = tuple(socket.gethostbyname_ex("node")[2])
            self._looked_up_at = now
        return self._node_ips

    def __contains__(self, address: object) -> bool:
        return super().__contains__(address) or address in self._node_addresses()
