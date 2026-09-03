"""Tests for the achievement-notification cache-key helpers.

These pin the exact key *format*: every other test now builds the keys via
these helpers, so a typo in the format string would otherwise be invisible to
the whole suite (the helper and its callers would simply agree on the wrong
key).
"""

import pytest
from django.core.cache import cache

from suchar_overflow.achievements.cache import bell_cache_key
from suchar_overflow.achievements.cache import mark_suchar_toast_sent
from suchar_overflow.achievements.cache import pending_cache_key
from suchar_overflow.achievements.cache import suchar_toast_sent_cache_key
from suchar_overflow.achievements.cache import toast_cache_key


def test_pending_cache_key_format() -> None:
    assert pending_cache_key(5) == "achievements_pending:5"


def test_bell_cache_key_format() -> None:
    assert bell_cache_key(5) == "achievements_bell:5"


def test_toast_cache_key_format() -> None:
    assert toast_cache_key(5) == "toast_pending:5"


def test_suchar_toast_sent_cache_key_format() -> None:
    assert suchar_toast_sent_cache_key(7) == "toast_sent_suchar:7"


def test_keys_are_distinct() -> None:
    # The mechanisms have different lifecycles (see cache.py docstring); they
    # must never collide on the same id.
    keys = {
        pending_cache_key(5),
        bell_cache_key(5),
        toast_cache_key(5),
        suchar_toast_sent_cache_key(5),
    }
    assert len(keys) == 4  # noqa: PLR2004


@pytest.mark.django_db
def test_mark_suchar_toast_sent_latches_once() -> None:
    cache.delete(suchar_toast_sent_cache_key(42))

    assert mark_suchar_toast_sent(42) is True
    assert mark_suchar_toast_sent(42) is False
    assert mark_suchar_toast_sent(43) is True
