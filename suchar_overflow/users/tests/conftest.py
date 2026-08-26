from typing import TYPE_CHECKING

import pytest
from django.core.cache import cache

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _clear_user_rank_cache() -> Iterator[None]:
    """Keep the profile rank cache from leaking between tests.

    Mirrors `stats/tests/conftest.py`: the test settings use a `locmem` cache
    that lives for the whole process, so a rank computed in one test would
    otherwise be served to the next one. Unlike the leaderboard there is no
    single key to delete — the rank key embeds the user pk — so clear the lot.
    """
    cache.clear()
    yield
    cache.clear()
