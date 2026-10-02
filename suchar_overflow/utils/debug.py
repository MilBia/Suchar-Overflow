"""Helpers for the local dev settings."""

import contextlib
import socket


class InternalIPs(list):
    """``INTERNAL_IPS`` that also accepts the ``node`` service's address, looked up per request.

    The ``node`` container starts after ``django`` (it waits for its healthcheck), so its address
    can't be read when settings are imported; and it changes whenever compose recreates it. The
    lookup runs only for an address the static entries don't already cover.
    """

    def __contains__(self, address: object) -> bool:
        if super().__contains__(address):
            return True
        with contextlib.suppress(OSError):
            return address in socket.gethostbyname_ex("node")[2]
        return False
