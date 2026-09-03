"""Boundary tests for the Comedy Rank name mapping (issue #291).

The mapping is a pure function of three integers, so these tests never touch
the DB. Assertions compare against ``gettext(...)`` of the English catalog
msgid rather than a hardcoded Polish rendering — CI never compiles
``locale/*.mo`` (see CLAUDE.md).
"""

import pytest
from django.utils.translation import gettext

from suchar_overflow.users.comedy_ranks import comedy_rank_name


@pytest.mark.django_db
def test_zero_funny_score_is_the_floor_rank() -> None:
    name = comedy_rank_name(
        funny_score=0,
        higher_users=41,
        ranked_population=41,
    )
    assert name == gettext("Junior Quizmaster")


@pytest.mark.django_db
def test_zero_funny_score_beats_being_alone_at_the_top() -> None:
    """A no-vote site puts everyone at rank 1; they still haven't earned it."""
    name = comedy_rank_name(
        funny_score=0,
        higher_users=0,
        ranked_population=0,
    )
    assert name == gettext("Junior Quizmaster")


@pytest.mark.django_db
def test_nobody_above_is_the_top_rank() -> None:
    name = comedy_rank_name(
        funny_score=5,
        higher_users=0,
        ranked_population=8,
    )
    assert name == gettext("Godfather of Puns")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("higher_users", "ranked_population", "expected_msgid"),
    [
        # p == 0.10 -> still Pun Sommelier (upper bound inclusive)
        (1, 10, "Pun Sommelier"),
        # p == 0.11 -> drops to the next band
        (11, 100, "Laughter Carousel Chairman"),
        # p == 0.35 -> still Laughter Carousel Chairman
        (35, 100, "Laughter Carousel Chairman"),
        # p == 0.36 -> drops a band
        (36, 100, "Wedding Uncle"),
        # p == 0.70 -> still Wedding Uncle
        (70, 100, "Wedding Uncle"),
        # p == 0.71 -> floor band
        (71, 100, "Junior Quizmaster"),
    ],
)
def test_percentile_band_boundaries(
    higher_users: int,
    ranked_population: int,
    expected_msgid: str,
) -> None:
    name = comedy_rank_name(
        funny_score=7,
        higher_users=higher_users,
        ranked_population=ranked_population,
    )
    assert name == gettext(expected_msgid)
