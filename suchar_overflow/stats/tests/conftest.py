from typing import TYPE_CHECKING

import pytest
from django.core.cache import cache

from suchar_overflow.stats.views import LEADERBOARD_CACHE_KEY

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _clear_leaderboard_cache() -> Iterator[None]:
    cache.delete(LEADERBOARD_CACHE_KEY)
    yield
    cache.delete(LEADERBOARD_CACHE_KEY)
