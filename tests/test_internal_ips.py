"""``InternalIPs`` (used by ``config.settings.local``): the debug toolbar through :3000 (#466).

webpack-dev-server proxies :3000 to django, so the toolbar sees the ``node`` container's address as the
client. That container starts *after* django (it waits for its healthcheck) and gets a new address
whenever compose recreates it, so ``INTERNAL_IPS`` must resolve it per request: a lookup at settings
import time finds nothing on a fresh ``just up`` and the toolbar silently never shows on :3000.
"""

import socket

import pytest

from suchar_overflow.utils.debug import InternalIPs


class _Settings:
    INTERNAL_IPS = InternalIPs(["127.0.0.1", "10.0.2.2"])


@pytest.fixture
def local_settings(monkeypatch: pytest.MonkeyPatch) -> type[_Settings]:
    monkeypatch.setattr(InternalIPs, "ttl", 0.0)  # these tests change the answer between lookups
    return _Settings


def test_node_service_address_is_resolved_per_request(
    local_settings: type[_Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ips = local_settings.INTERNAL_IPS

    def unresolvable(name: str) -> None:
        raise socket.gaierror(name)

    monkeypatch.setattr(socket, "gethostbyname_ex", unresolvable)
    assert "172.19.0.7" not in ips

    monkeypatch.setattr(socket, "gethostbyname_ex", lambda name: (name, [], ["172.19.0.7"]))
    assert "172.19.0.7" in ips
    # The address changes when compose recreates the container: no caching.
    monkeypatch.setattr(socket, "gethostbyname_ex", lambda name: (name, [], ["172.19.0.9"]))
    assert "172.19.0.7" not in ips
    assert "172.19.0.9" in ips


def test_static_entries_never_trigger_a_lookup(
    local_settings: type[_Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(name: str) -> None:
        raise AssertionError(name)

    monkeypatch.setattr(socket, "gethostbyname_ex", fail)
    assert "127.0.0.1" in local_settings.INTERNAL_IPS


def test_unresolvable_node_is_just_not_internal(
    local_settings: type[_Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unresolvable(name: str) -> None:
        raise socket.gaierror(name)

    monkeypatch.setattr(socket, "gethostbyname_ex", unresolvable)
    assert "203.0.113.5" not in local_settings.INTERNAL_IPS


def test_lookup_result_is_kept_for_the_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def resolve(name: str) -> tuple[str, list[str], list[str]]:
        calls.append(name)
        return (name, [], ["172.19.0.7"])

    monkeypatch.setattr(socket, "gethostbyname_ex", resolve)
    ips = InternalIPs(["127.0.0.1"])
    assert "172.19.0.7" in ips
    assert "203.0.113.5" not in ips
    assert len(calls) == 1
