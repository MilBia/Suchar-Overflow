import json
from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()

LEADERBOARD_URL = "stats:leaderboard"


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


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
# Chart data
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_chart_data_is_valid_json(client):
    response = client.get(reverse(LEADERBOARD_URL))
    # These must be JSON-parseable strings
    json.loads(response.context["chart_labels"])
    json.loads(response.context["chart_values"])


@pytest.mark.django_db
def test_chart_data_reflects_recent_activity(client):
    author = make_user("author")
    Suchar.objects.create(text="Recent joke", author=author)
    # created_at is auto_now_add — this suchar was created "now", within last 30 days

    response = client.get(reverse(LEADERBOARD_URL))
    values = json.loads(response.context["chart_values"])
    assert sum(values) >= 1


@pytest.mark.django_db
def test_chart_labels_and_values_have_same_length(client):
    author = make_user("author")
    Suchar.objects.create(text="Joke", author=author)

    response = client.get(reverse(LEADERBOARD_URL))
    labels = json.loads(response.context["chart_labels"])
    values = json.loads(response.context["chart_values"])
    assert len(labels) == len(values)


@pytest.mark.django_db
def test_chart_ignores_old_suchars(client):
    """Suchars older than 30 days must not appear in the activity chart."""
    author = make_user("author")
    old = Suchar.objects.create(text="Old joke", author=author)
    Suchar.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timezone.timedelta(days=60),
    )

    response = client.get(reverse(LEADERBOARD_URL))
    values = json.loads(response.context["chart_values"])
    assert sum(values) == 0
