"""Cross-view regression guard for issue #229.

The profile's global rank (`UserDetailView._compute_rank`) and the
leaderboard's "Comedy Kings" position (`LeaderboardView`, via
`_ranked_top_n`) both rank users by funny votes received. Before #229 they
used different tie semantics — competition ranking on the profile, plain
list position on the leaderboard — so two authors tied on the same score
could see contradictory numbers for the same underlying state (e.g. "#1" on
one profile and "2nd place" on the leaderboard for the very same author).
Both must now agree on dense ranking.
"""

from typing import TYPE_CHECKING

import pytest
from django.core.cache import cache
from django.urls import reverse

from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

if TYPE_CHECKING:
    from django.test import Client


@pytest.mark.django_db
def test_tied_authors_see_the_same_rank_on_profile_and_leaderboard(
    client: Client,
) -> None:
    # Both caches key on the raw score/context, not the username — a test
    # elsewhere in the suite may have already cached a rank for the same
    # score or the leaderboard's single global key, which would make this
    # test read stale data instead of what it just created.
    cache.clear()
    leader = make_user("rc_leader")
    tie_a = make_user("rc_tie_a")
    tie_b = make_user("rc_tie_b")

    s_leader = Suchar.objects.create(text="leader joke", author=leader)
    s_a = Suchar.objects.create(text="tie a joke", author=tie_a)
    s_b = Suchar.objects.create(text="tie b joke", author=tie_b)

    for i in range(5):
        Vote.objects.create(suchar=s_leader, user=make_user(f"rc_lv{i}"), is_funny=True)
    for i in range(3):
        Vote.objects.create(suchar=s_a, user=make_user(f"rc_av{i}"), is_funny=True)
        Vote.objects.create(suchar=s_b, user=make_user(f"rc_bv{i}"), is_funny=True)

    client.force_login(leader)
    profile_rank_a = client.get(
        reverse("users:detail", kwargs={"username": "rc_tie_a"}),
    ).context["global_rank"]
    profile_rank_b = client.get(
        reverse("users:detail", kwargs={"username": "rc_tie_b"}),
    ).context["global_rank"]

    leaderboard_ranks = {
        author.username: author.rank
        for author in client.get(reverse("stats:leaderboard")).context[
            "top_authors_funny"
        ]
    }

    # leader sits alone on 5 votes (rank 1); tie_a/tie_b share 3 votes, one
    # tier down, so dense ranking puts them at 2 — never 2 and 3.
    expected_tied_rank = 2
    assert profile_rank_a == profile_rank_b == expected_tied_rank
    assert leaderboard_ranks["rc_tie_a"] == expected_tied_rank
    assert leaderboard_ranks["rc_tie_b"] == expected_tied_rank
    assert profile_rank_a == leaderboard_ranks["rc_tie_a"]
