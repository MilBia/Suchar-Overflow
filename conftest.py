"""Root fixtures shared by ``suchar_overflow/*/tests`` and ``tests/`` (unit and E2E)."""

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def rq_queue() -> Iterator[MagicMock]:
    """Replace ``django_rq.get_queue`` so no test needs Redis for the job queue (#460).

    Yields the queue mock: assert on ``rq_queue.enqueue`` (and ``enqueue_in`` /
    ``enqueue_at``). Production code must call ``django_rq.get_queue(...)`` through the
    module attribute (not ``from django_rq import get_queue``) so the patch reaches it.
    """
    with patch("django_rq.get_queue") as get_queue:
        yield get_queue.return_value
