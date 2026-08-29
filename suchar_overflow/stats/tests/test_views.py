from datetime import timedelta
from http import HTTPStatus
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from django.core.cache import cache
from django.db import connection
from django.db.models import Count
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from suchar_overflow.conftest import make_user
from suchar_overflow.stats.views import LEADERBOARD_CACHE_KEY
from suchar_overflow.stats.views import LeaderboardView
from suchar_overflow.stats.views import _ranked_top_n
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Tag
from suchar_overflow.suchary.models import Vote

if TYPE_CHECKING:
    from django.test import Client

LEADERBOARD_URL = "stats:leaderboard"
# 1 authors query, 1 suchary query, 1 scoped tags prefetch (only the ~30
# rendered suchary, not the full table — see issue #183), 1 widest-window
# daily chart query, 1 all-time monthly chart query — down from 10.
MAX_UNCACHED_QUERIES = 5


# ---------------------------------------------------------------------------
# Basic rendering
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_leaderboard_renders(client: Client) -> None:
    response = client.get(reverse(LEADERBOARD_URL))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_leaderboard_empty_db_renders(client: Client) -> None:
    """Leaderboard must not crash when there is no data at all."""
    response = client.get(reverse(LEADERBOARD_URL))
    assert response.status_code == HTTPStatus.OK
    ctx = response.context
    # All querysets are empty — no exceptions raised
    assert list(ctx["top_authors_overall"]) == []
    assert list(ctx["top_suchars_overall"]) == []


# ---------------------------------------------------------------------------
# top_authors_overall
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_top_authors_overall_ordering(client: Client) -> None:
    u1 = make_user("u1")
    u2 = make_user("u2")
    s1 = Suchar.objects.create(text="Joke 1", author=u1)
    s2 = Suchar.objects.create(text="Joke 2", author=u2)

    # u1 gets 3 votes, u2 gets 1
    for i in range(3):
        v = make_user(f"voter_a{i}")
        Vote.objects.create(suchar=s1, user=v, is_funny=True)
    Vote.objects.create(suchar=s2, user=u1, is_funny=True)

    response = client.get(reverse(LEADERBOARD_URL))
    authors = list(response.context["top_authors_overall"])
    usernames = [a.username for a in authors]
    assert usernames.index("u1") < usernames.index("u2")


@pytest.mark.django_db
def test_top_authors_overall_excludes_zero_score(client: Client) -> None:
    u_no_votes = make_user("no_votes")
    Suchar.objects.create(text="Lonely joke", author=u_no_votes)

    response = client.get(reverse(LEADERBOARD_URL))
    usernames = [a.username for a in response.context["top_authors_overall"]]
    assert "no_votes" not in usernames


@pytest.mark.django_db
def test_top_authors_overall_capped_at_ten(client: Client) -> None:
    for i in range(15):
        u = make_user(f"user{i}")
        s = Suchar.objects.create(text=f"Joke {i}", author=u)
        v = make_user(f"vvv{i}")
        Vote.objects.create(suchar=s, user=v, is_funny=True)

    response = client.get(reverse(LEADERBOARD_URL))
    num_authors_with_votes = 15
    assert len(list(response.context["top_authors_overall"])) == min(
        num_authors_with_votes,
        10,
    )


# ---------------------------------------------------------------------------
# top_authors_funny / top_authors_dry
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_top_authors_funny_only_counts_funny_votes(client: Client) -> None:
    u_funny = make_user("funny_author")
    u_dry = make_user("dry_author")
    s_funny = Suchar.objects.create(text="Funny", author=u_funny)
    s_dry = Suchar.objects.create(text="Dry", author=u_dry)

    Vote.objects.create(suchar=s_funny, user=u_dry, is_funny=True)
    Vote.objects.create(suchar=s_dry, user=u_funny, is_dry=True)

    response = client.get(reverse(LEADERBOARD_URL))
    funny_authors = [a.username for a in response.context["top_authors_funny"]]
    dry_authors = [a.username for a in response.context["top_authors_dry"]]

    assert "funny_author" in funny_authors
    assert "funny_author" not in dry_authors
    assert "dry_author" in dry_authors
    assert "dry_author" not in funny_authors


@pytest.mark.django_db
def test_leaderboard_renders_card_per_tab_via_shared_partials(client: Client) -> None:
    u_funny = make_user("badge_funny_author")
    u_dry = make_user("badge_dry_author")
    s_funny = Suchar.objects.create(text="Funny joke", author=u_funny)
    s_dry = Suchar.objects.create(text="Dry joke", author=u_dry)
    Vote.objects.create(suchar=s_funny, user=u_dry, is_funny=True)
    Vote.objects.create(suchar=s_dry, user=u_funny, is_dry=True)

    response = client.get(reverse(LEADERBOARD_URL))
    content = response.content.decode()

    # Two cards (authors + suchary) per tab, three tabs.
    cards_per_tab = 2
    assert content.count("card-header-gold") == cards_per_tab
    assert content.count("card-header-funny") == cards_per_tab
    assert content.count("card-header-dry") == cards_per_tab
    assert gettext("Most Active Authors") in content
    assert gettext("Hall of Fame") in content
    assert gettext("Comedy Kings") in content
    assert gettext("Top Funny Jokes") in content
    assert gettext("Lords of Drought") in content
    assert gettext("Top Dry Jokes") in content
    # Only the "overall" badge variant shows the funny/dry breakdown line.
    assert "stats-text-sm" in content


@pytest.mark.django_db
def test_leaderboard_author_card_ties_share_dense_rank(client: Client) -> None:
    """Issue #229: two authors tied on funny votes must show the same rank
    number on the leaderboard, and the next distinct tier must not skip a
    number — the same dense-ranking semantics as the profile's global_rank.
    """
    tie_a = make_user("dense_tie_a")
    tie_b = make_user("dense_tie_b")
    behind = make_user("dense_behind")
    s_a = Suchar.objects.create(text="joke a", author=tie_a)
    s_b = Suchar.objects.create(text="joke b", author=tie_b)
    s_behind = Suchar.objects.create(text="joke c", author=behind)
    for i in range(3):
        Vote.objects.create(suchar=s_a, user=make_user(f"va{i}"), is_funny=True)
        Vote.objects.create(suchar=s_b, user=make_user(f"vb{i}"), is_funny=True)
    Vote.objects.create(suchar=s_behind, user=make_user("vc0"), is_funny=True)

    response = client.get(reverse(LEADERBOARD_URL))
    content = response.content.decode()
    funny_authors_section = content.split(gettext("Comedy Kings"))[1].split(
        gettext("Top Funny Jokes"),
    )[0]
    # s_a and s_b (3 funny votes each) also tie on the suchar-level ranking,
    # one tier above s_behind (1 funny vote) — same fixture, same assertion,
    # covering `_leaderboard_suchar_card.html`'s `{{ suchar.rank }}` too.
    funny_suchary_section = content.split(gettext("Top Funny Jokes"))[1].split(
        gettext("Lords of Drought"),
    )[0]

    for section in (funny_authors_section, funny_suchary_section):
        assert section.count(">#1</span>") == 2  # noqa: PLR2004
        assert section.count(">#2</span>") == 1
        assert ">#3</span>" not in section


# ---------------------------------------------------------------------------
# top_suchars_overall
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_top_suchars_overall_ordering(client: Client) -> None:
    author = make_user("author")
    s_popular = Suchar.objects.create(text="Popular", author=author)
    s_unpopular = Suchar.objects.create(text="Unpopular", author=author)

    for i in range(5):
        v = make_user(f"vp{i}")
        Vote.objects.create(suchar=s_popular, user=v, is_funny=True)
    v = make_user("vu0")
    Vote.objects.create(suchar=s_unpopular, user=v, is_funny=True)

    response = client.get(reverse(LEADERBOARD_URL))
    suchars = list(response.context["top_suchars_overall"])
    texts = [s.text for s in suchars]
    assert texts.index("Popular") < texts.index("Unpopular")


@pytest.mark.django_db
def test_top_suchars_overall_excludes_zero_score(client: Client) -> None:
    author = make_user("author")
    Suchar.objects.create(text="No votes joke", author=author)

    response = client.get(reverse(LEADERBOARD_URL))
    texts = [s.text for s in response.context["top_suchars_overall"]]
    assert "No votes joke" not in texts


# ---------------------------------------------------------------------------
# _ranked_top_n
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ranked_top_n_orders_descending_and_caps_at_limit() -> None:
    author = make_user("top_n_author")
    for i in range(5):
        Suchar.objects.create(text=f"Joke {i}", author=author)
    suchary_by_score = list(Suchar.objects.annotate(score=Count("votes")))
    for suchar, votes in zip(suchary_by_score, [1, 3, 0, 2, 4], strict=True):
        for j in range(votes):
            voter = make_user(f"voter_{suchar.pk}_{j}")
            Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    items = list(Suchar.objects.annotate(score=Count("votes")))
    result = _ranked_top_n(items, "score", limit=3)

    assert len(result) == 3  # noqa: PLR2004
    # .score comes from the .annotate(score=Count(...)) call above, not a
    # static model field — django-stubs can't see it.
    scores = [s.score for s in result]  # type: ignore[union-attr]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.django_db
def test_ranked_top_n_excludes_zero_order_field() -> None:
    author = make_user("top_n_zero_author")
    scored = Suchar.objects.create(text="Scored", author=author)
    Suchar.objects.create(text="Unscored", author=author)
    voter = make_user("top_n_zero_voter")
    Vote.objects.create(suchar=scored, user=voter, is_funny=True)

    items = list(Suchar.objects.annotate(score=Count("votes")))
    result = _ranked_top_n(items, "score")

    assert [s.pk for s in result] == [scored.pk]


def test_ranked_top_n_breaks_sort_ties_by_pk_ascending() -> None:
    """Sort order among equal-score items must be deterministic and
    independent of input order — Python's stable sort alone would just
    preserve whatever order the caller passed in, which for a
    DB-materialized list is not guaranteed stable across query plans.
    """
    items = [
        SimpleNamespace(pk=3, score=5),
        SimpleNamespace(pk=1, score=5),
        SimpleNamespace(pk=2, score=5),
    ]

    # SimpleNamespace is a deliberate lightweight stand-in (only .pk and the
    # order_field are needed) so this test doesn't have to hit the DB.
    result = _ranked_top_n(items, "score")  # type: ignore[arg-type]

    assert [item.pk for item in result] == [1, 2, 3]


def test_ranked_top_n_ties_share_dense_rank() -> None:
    """Issue #229: equal scores share a rank, and the next distinct score
    follows immediately with no gap (dense ranking, not competition ranking).
    """
    items = [
        SimpleNamespace(pk=1, score=10),
        SimpleNamespace(pk=2, score=10),
        SimpleNamespace(pk=3, score=8),
        SimpleNamespace(pk=4, score=5),
    ]

    result = _ranked_top_n(items, "score")  # type: ignore[arg-type]

    assert [item.rank for item in result] == [1, 1, 2, 3]  # type: ignore[union-attr]


def test_ranked_top_n_does_not_leak_rank_across_calls_on_shared_items() -> None:
    """`authors`/`all_suchary` in `_build_context` are each ranked three times
    (overall/funny/dry) from the *same* underlying objects. Each item's rank
    differs per metric, so `_ranked_top_n` must hand back copies rather than
    mutating the shared originals, or the second call's ranks would bleed
    into the first call's already-returned result.
    """
    shared = [
        SimpleNamespace(pk=1, score_a=5, score_b=1),
        SimpleNamespace(pk=2, score_a=1, score_b=5),
    ]

    by_a = _ranked_top_n(shared, "score_a")  # type: ignore[arg-type]
    by_b = _ranked_top_n(shared, "score_b")  # type: ignore[arg-type]

    assert [item.rank for item in by_a] == [1, 2]  # type: ignore[union-attr]
    assert [item.rank for item in by_b] == [1, 2]  # type: ignore[union-attr]
    assert not hasattr(shared[0], "rank")
    assert not hasattr(shared[1], "rank")


# ---------------------------------------------------------------------------
# Chart data
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_chart_data_is_valid_json(client: Client) -> None:
    response = client.get(reverse(LEADERBOARD_URL))
    # These must be JSON-parseable strings
    datasets = response.context["chart_datasets"]
    assert "7" in datasets
    assert "30" in datasets
    assert "90" in datasets
    assert "all" in datasets
    assert "labels" in datasets["30"]
    assert "values" in datasets["30"]


@pytest.mark.django_db
def test_chart_data_reflects_recent_activity(client: Client) -> None:
    author = make_user("author")
    Suchar.objects.create(text="Recent joke", author=author)
    # created_at is auto_now_add — this suchar was created "now", within last 30 days

    response = client.get(reverse(LEADERBOARD_URL))
    datasets = response.context["chart_datasets"]
    values = datasets["30"]["values"]
    assert sum(values) >= 1


@pytest.mark.django_db
def test_chart_labels_and_values_have_same_length(client: Client) -> None:
    author = make_user("author")
    Suchar.objects.create(text="Joke", author=author)

    response = client.get(reverse(LEADERBOARD_URL))
    datasets = response.context["chart_datasets"]
    for key in datasets:
        assert len(datasets[key]["labels"]) == len(datasets[key]["values"])


@pytest.mark.django_db
def test_chart_ignores_old_suchars(client: Client) -> None:
    """Suchars older than 30 days must not appear in the 30-day activity chart."""
    author = make_user("author")
    old = Suchar.objects.create(text="Old joke", author=author)
    Suchar.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=60),
    )

    response = client.get(reverse(LEADERBOARD_URL))
    datasets = response.context["chart_datasets"]
    assert sum(datasets["30"]["values"]) == 0
    assert sum(datasets["all"]["values"]) >= 1


# ---------------------------------------------------------------------------
# Query count and caching (issue #179)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_build_context_executes_at_most_five_queries() -> None:
    author = make_user("query_count_author")
    suchar = Suchar.objects.create(text="Joke", author=author)
    voter = make_user("query_count_voter")
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    with CaptureQueriesContext(connection) as ctx:
        LeaderboardView()._build_context()  # noqa: SLF001

    assert len(ctx.captured_queries) <= MAX_UNCACHED_QUERIES


@pytest.mark.django_db
def test_full_page_render_does_not_n_plus_one_on_tags(client: Client) -> None:
    """Regression test for issue #183: `tags.first()` in the suchar card
    template used to hit the DB twice per card (once for `.slug`, once for
    `.name`) regardless of prefetching, because `.first()` clones the
    queryset via `order_by("pk")` and drops any prefetch cache. Rendering
    must stay bounded regardless of how many suchary/tags are on the page.
    """
    author = make_user("render_author")
    tag = Tag.objects.create(name="Programming", slug="programming")
    for i in range(10):
        suchar = Suchar.objects.create(text=f"Joke {i}", author=author)
        suchar.tags.add(tag)
        voter = make_user(f"render_voter_{i}")
        Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    with CaptureQueriesContext(connection) as ctx:
        response = client.get(reverse(LEADERBOARD_URL))

    assert response.status_code == HTTPStatus.OK
    tag_queries = [q for q in ctx.captured_queries if "suchary_tag" in q["sql"]]
    max_tag_queries = 2  # one prefetch query, generously allow one more
    assert len(tag_queries) <= max_tag_queries


@pytest.mark.django_db
def test_get_cached_context_second_call_within_ttl_does_not_query_db() -> None:
    author = make_user("cache_author")
    suchar = Suchar.objects.create(text="Joke", author=author)
    voter = make_user("cache_voter")
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    view = LeaderboardView()
    view._get_cached_context()  # noqa: SLF001

    with CaptureQueriesContext(connection) as ctx:
        view._get_cached_context()  # noqa: SLF001

    assert len(ctx.captured_queries) == 0


@pytest.mark.django_db
def test_leaderboard_second_request_within_ttl_issues_no_aggregating_queries(
    client: Client,
) -> None:
    author = make_user("cache_author")
    suchar = Suchar.objects.create(text="Joke", author=author)
    voter = make_user("cache_voter")
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    client.get(reverse(LEADERBOARD_URL))

    with CaptureQueriesContext(connection) as ctx:
        client.get(reverse(LEADERBOARD_URL))

    assert not any("GROUP BY" in q["sql"] for q in ctx.captured_queries)


@pytest.mark.django_db
def test_leaderboard_cache_repopulates_after_cache_clear(client: Client) -> None:
    """Not a TTL test: deleting the cache key stands in for expiry, since the
    view itself has no lever to expire the cache early. This only proves a
    fresh `_build_context` call re-reads current DB state, not that TTL fires.
    """
    author = make_user("ttl_author")
    Suchar.objects.create(text="Old", author=author)
    client.get(reverse(LEADERBOARD_URL))

    cache.delete(LEADERBOARD_CACHE_KEY)

    suchar2 = Suchar.objects.create(text="New", author=author)
    voter = make_user("ttl_voter")
    Vote.objects.create(suchar=suchar2, user=voter, is_funny=True)

    response = client.get(reverse(LEADERBOARD_URL))
    texts = [s.text for s in response.context["top_suchars_overall"]]
    assert "New" in texts
