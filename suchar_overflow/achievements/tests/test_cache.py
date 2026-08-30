"""Tests for the achievement-notification cache-key helpers.

These pin the exact key *format*: every other test now builds the keys via
these helpers, so a typo in the format string would otherwise be invisible to
the whole suite (the helper and its callers would simply agree on the wrong
key).
"""

from suchar_overflow.achievements.cache import bell_cache_key
from suchar_overflow.achievements.cache import pending_cache_key


def test_pending_cache_key_format() -> None:
    assert pending_cache_key(5) == "achievements_pending:5"


def test_bell_cache_key_format() -> None:
    assert bell_cache_key(5) == "achievements_bell:5"


def test_keys_are_distinct() -> None:
    # The two mechanisms have different lifecycles (see cache.py docstring);
    # they must never collide on the same user id.
    assert pending_cache_key(5) != bell_cache_key(5)
