import pytest
from django.core.cache import cache

from suchar_overflow.stats.views import LEADERBOARD_CACHE_KEY


@pytest.fixture(autouse=True)
def _clear_leaderboard_cache():
    cache.delete(LEADERBOARD_CACHE_KEY)
    yield
    cache.delete(LEADERBOARD_CACHE_KEY)
