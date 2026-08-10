import json
from datetime import timedelta
from http import HTTPStatus

import pytest
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from suchar_overflow.conftest import make_user
from suchar_overflow.stats.views import _top_n
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

LEADERBOARD_URL = "stats:leaderboard"


# ---------------------------------------------------------------------------
# Basic rendering
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_leaderboard_renders(client):
    response = client.get(reverse(LEADERBOARD_URL))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_leaderboard_empty_db_renders(client):
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
def test_top_authors_overall_ordering(client):
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
def test_top_authors_overall_excludes_zero_score(client):
    u_no_votes = make_user("no_votes")
    Suchar.objects.create(text="Lonely joke", author=u_no_votes)

    response = client.get(reverse(LEADERBOARD_URL))
    usernames = [a.username for a in response.context["top_authors_overall"]]
    assert "no_votes" not in usernames


@pytest.mark.django_db
def test_top_authors_overall_capped_at_ten(client):
    for i in range(15):
        u = make_user(f"user{i}")
        s = Suchar.objects.create(text=f"Joke {i}", author=u)
        v = make_user(f"vvv{i}")
        Vote.objects.create(suchar=s, user=v, is_funny=True)

    response = client.get(reverse(LEADERBOARD_URL))
    assert len(list(response.context["top_authors_overall"])) <= 10  # noqa: PLR2004


# ---------------------------------------------------------------------------
# top_authors_funny / top_authors_dry
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_top_authors_funny_only_counts_funny_votes(client):
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
def test_leaderboard_renders_card_per_tab_via_shared_partials(client):
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


# ---------------------------------------------------------------------------
# top_suchars_overall
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_top_suchars_overall_ordering(client):
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
def test_top_suchars_overall_excludes_zero_score(client):
    author = make_user("author")
    Suchar.objects.create(text="No votes joke", author=author)

    response = client.get(reverse(LEADERBOARD_URL))
    texts = [s.text for s in response.context["top_suchars_overall"]]
    assert "No votes joke" not in texts


# ---------------------------------------------------------------------------
# _top_n
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_top_n_orders_descending_and_caps_at_limit():
    author = make_user("top_n_author")
    for i in range(5):
        Suchar.objects.create(text=f"Joke {i}", author=author)
    suchary_by_score = list(Suchar.objects.annotate(score=Count("votes")))
    for suchar, votes in zip(suchary_by_score, [1, 3, 0, 2, 4], strict=True):
        for j in range(votes):
            voter = make_user(f"voter_{suchar.pk}_{j}")
            Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    result = _top_n(
        Suchar.objects.all(),
        {"score": Count("votes")},
        "score",
        limit=3,
    )

    assert len(result) == 3  # noqa: PLR2004
    scores = [s.score for s in result]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.django_db
def test_top_n_excludes_zero_order_field():
    author = make_user("top_n_zero_author")
    scored = Suchar.objects.create(text="Scored", author=author)
    Suchar.objects.create(text="Unscored", author=author)
    voter = make_user("top_n_zero_voter")
    Vote.objects.create(suchar=scored, user=voter, is_funny=True)

    result = _top_n(Suchar.objects.all(), {"score": Count("votes")}, "score")

    assert [s.pk for s in result] == [scored.pk]


# ---------------------------------------------------------------------------
# Chart data
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_chart_data_is_valid_json(client):
    response = client.get(reverse(LEADERBOARD_URL))
    # These must be JSON-parseable strings
    datasets = json.loads(response.context["chart_datasets"])
    assert "7" in datasets
    assert "30" in datasets
    assert "90" in datasets
    assert "all" in datasets
    assert "labels" in datasets["30"]
    assert "values" in datasets["30"]


@pytest.mark.django_db
def test_chart_data_reflects_recent_activity(client):
    author = make_user("author")
    Suchar.objects.create(text="Recent joke", author=author)
    # created_at is auto_now_add — this suchar was created "now", within last 30 days

    response = client.get(reverse(LEADERBOARD_URL))
    datasets = json.loads(response.context["chart_datasets"])
    values = datasets["30"]["values"]
    assert sum(values) >= 1


@pytest.mark.django_db
def test_chart_labels_and_values_have_same_length(client):
    author = make_user("author")
    Suchar.objects.create(text="Joke", author=author)

    response = client.get(reverse(LEADERBOARD_URL))
    datasets = json.loads(response.context["chart_datasets"])
    for key in datasets:
        assert len(datasets[key]["labels"]) == len(datasets[key]["values"])


@pytest.mark.django_db
def test_chart_ignores_old_suchars(client):
    """Suchars older than 30 days must not appear in the 30-day activity chart."""
    author = make_user("author")
    old = Suchar.objects.create(text="Old joke", author=author)
    Suchar.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=60),
    )

    response = client.get(reverse(LEADERBOARD_URL))
    datasets = json.loads(response.context["chart_datasets"])
    assert sum(datasets["30"]["values"]) == 0
    assert sum(datasets["all"]["values"]) >= 1
