import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_leaderboard_cache():
    cache.clear()
    yield
    cache.clear()
