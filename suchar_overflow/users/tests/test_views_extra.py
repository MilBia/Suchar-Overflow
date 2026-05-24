"""Extra UserDetailView tests: scheduled suchary, rank, heatmap, signup."""

import datetime
import json
from http import HTTPStatus
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


def detail_url(username):
    return reverse("users:detail", kwargs={"username": username})


# ===========================================================================
# Scheduled suchary — owner-only
# ===========================================================================


@pytest.mark.django_db
def test_scheduled_suchary_visible_to_owner(client):
    user = make_user("owner")
    future = timezone.now() + datetime.timedelta(days=1)
    Suchar.objects.create(text="Scheduled joke", author=user, published_at=future)

    client.force_login(user)
    response = client.get(detail_url("owner"))
    assert response.status_code == HTTPStatus.OK
    assert "scheduled_suchary" in response.context
    scheduled = list(response.context["scheduled_suchary"])
    assert len(scheduled) == 1
    assert scheduled[0].text == "Scheduled joke"


@pytest.mark.django_db
def test_scheduled_suchary_hidden_from_other_user(client):
    owner = make_user("owner2")
    visitor = make_user("visitor2")
    future = timezone.now() + datetime.timedelta(days=1)
    Suchar.objects.create(text="Hidden scheduled", author=owner, published_at=future)

    client.force_login(visitor)
    response = client.get(detail_url("owner2"))
    assert response.status_code == HTTPStatus.OK
    # scheduled_suchary context key must not exist for non-owner
    assert "scheduled_suchary" not in response.context


# ===========================================================================
# Global rank
# ===========================================================================


@pytest.mark.django_db
def test_global_rank_is_one_for_top_user(client):
    top = make_user("top")
    other = make_user("other_rank")
    s_top = Suchar.objects.create(text="funny joke", author=top)
    s_other = Suchar.objects.create(text="other joke", author=other)

    # top gets 3 funny votes, other gets 1
    for i in range(3):
        v = make_user(f"rv{i}")
        Vote.objects.create(suchar=s_top, user=v, is_funny=True)
    voter = make_user("rv_other")
    Vote.objects.create(suchar=s_other, user=voter, is_funny=True)

    client.force_login(top)
    response = client.get(detail_url("top"))
    assert response.context["global_rank"] == 1


@pytest.mark.django_db
def test_global_rank_increases_when_others_have_more_votes(client):
    u1 = make_user("rank_u1")
    u2 = make_user("rank_u2")
    s1 = Suchar.objects.create(text="j1", author=u1)
    s2 = Suchar.objects.create(text="j2", author=u2)

    # u2 gets 5 votes, u1 gets 1 → u1 rank = 2
    for i in range(5):
        v = make_user(f"rankv2_{i}")
        Vote.objects.create(suchar=s2, user=v, is_funny=True)
    v1 = make_user("rankv1_0")
    Vote.objects.create(suchar=s1, user=v1, is_funny=True)

    client.force_login(u1)
    response = client.get(detail_url("rank_u1"))
    assert response.context["global_rank"] == 2  # noqa: PLR2004


@pytest.mark.django_db
def test_global_rank_is_one_when_user_has_no_votes(client):
    user = make_user("novotes")
    Suchar.objects.create(text="joke", author=user)

    client.force_login(user)
    response = client.get(detail_url("novotes"))
    # No users have MORE votes, so rank = 0 + 1 = 1
    assert response.context["global_rank"] == 1


# ===========================================================================
# Heatmap
# ===========================================================================


@pytest.mark.django_db
def test_heatmap_weeks_is_list(client):
    user = make_user("heatmap_u")
    client.force_login(user)
    response = client.get(detail_url("heatmap_u"))
    assert isinstance(response.context["heatmap_weeks"], list)


@pytest.mark.django_db
def test_heatmap_weeks_each_has_days_and_month_label(client):
    user = make_user("heatmap_u2")
    client.force_login(user)
    response = client.get(detail_url("heatmap_u2"))
    for week in response.context["heatmap_weeks"]:
        assert "days" in week
        assert "month_label" in week
        for day in week["days"]:
            assert "date" in day
            assert "count" in day
            assert "level" in day


@pytest.mark.django_db
def test_heatmap_level_buckets(client):
    """Levels 0-4 must correspond to the documented thresholds."""
    user = make_user("heatmap_u3")
    # Create 5 suchary today to hit level 4
    today = timezone.now()
    for i in range(5):
        s = Suchar.objects.create(text=f"hm{i}", author=user)
        Suchar.objects.filter(pk=s.pk).update(created_at=today)

    client.force_login(user)
    response = client.get(detail_url("heatmap_u3"))

    # Find today's entry in any week
    today_str = today.date().strftime("%Y-%m-%d")
    found = False
    for week in response.context["heatmap_weeks"]:
        for day in week["days"]:
            if day["date"] == today_str:
                assert day["level"] == 4  # noqa: PLR2004
                assert day["count"] == 5  # noqa: PLR2004
                found = True
    assert found, "Today's date not found in heatmap"


@pytest.mark.django_db
def test_heatmap_starts_aligned_to_monday(client):
    """The first day in the first week must be a Monday (weekday=0)."""
    user = make_user("heatmap_u4")
    client.force_login(user)
    response = client.get(detail_url("heatmap_u4"))
    first_week = response.context["heatmap_weeks"][0]
    first_day_str = first_week["days"][0]["date"]
    first_day = datetime.date.fromisoformat(first_day_str)
    assert first_day.weekday() == 0  # Monday


# ===========================================================================
# Best joke
# ===========================================================================


@pytest.mark.django_db
def test_best_joke_is_highest_funny_vote_suchar(client):
    user = make_user("bestjoke_u")
    s_low = Suchar.objects.create(text="Low scorer", author=user)
    s_high = Suchar.objects.create(text="Top scorer", author=user)

    v1 = make_user("bj_v1")
    v2 = make_user("bj_v2")
    Vote.objects.create(suchar=s_high, user=v1, is_funny=True)
    Vote.objects.create(suchar=s_high, user=v2, is_funny=True)
    Vote.objects.create(suchar=s_low, user=v1, is_dry=True)

    client.force_login(user)
    response = client.get(detail_url("bestjoke_u"))
    assert response.context["best_joke"].text == "Top scorer"


@pytest.mark.django_db
def test_best_joke_is_none_when_no_suchary(client):
    user = make_user("bestjoke_empty")
    client.force_login(user)
    response = client.get(detail_url("bestjoke_empty"))
    assert response.context["best_joke"] is None


# ===========================================================================
# Activity chart context
# ===========================================================================


@pytest.mark.django_db
def test_activity_labels_and_values_are_json(client):
    user = make_user("chart_u")
    client.force_login(user)
    response = client.get(detail_url("chart_u"))
    labels = json.loads(response.context["activity_labels"])
    values = json.loads(response.context["activity_values"])
    assert isinstance(labels, list)
    assert isinstance(values, list)


@pytest.mark.django_db
def test_reception_data_is_list_of_two(client):
    user = make_user("recv_u")
    client.force_login(user)
    response = client.get(detail_url("recv_u"))
    data = json.loads(response.context["reception_data"])
    assert isinstance(data, list)
    assert len(data) == 2  # noqa: PLR2004


# ===========================================================================
# SignupView — protocol detection
# ===========================================================================


@pytest.mark.django_db(transaction=True)
def test_signup_enqueues_activation_email(client):
    with patch("suchar_overflow.users.views.django_rq.enqueue") as mock_enqueue:
        client.post(
            reverse("users:signup"),
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "password1": "S3cur3P@ss!",
                "password2": "S3cur3P@ss!",
            },
        )
    assert mock_enqueue.called
    args = mock_enqueue.call_args[0]
    # First arg is the task function, rest are its arguments
    assert args[0].__name__ == "send_activation_email"


@pytest.mark.django_db(transaction=True)
def test_signup_uses_http_protocol_when_not_secure(client):
    with patch("suchar_overflow.users.views.django_rq.enqueue") as mock_enqueue:
        client.post(
            reverse("users:signup"),
            {
                "username": "httpuser",
                "email": "httpuser@example.com",
                "password1": "S3cur3P@ss!",
                "password2": "S3cur3P@ss!",
            },
        )
    # enqueue args: (send_activation_email, user.pk, host, token, protocol)
    # protocol is the 5th positional arg (index 4)
    args = mock_enqueue.call_args[0]
    protocol = args[4]
    assert protocol == "http"


@pytest.mark.django_db(transaction=True)
def test_signup_uses_https_protocol_when_secure(client):
    with patch("suchar_overflow.users.views.django_rq.enqueue") as mock_enqueue:
        client.post(
            reverse("users:signup"),
            {
                "username": "httpsuser",
                "email": "httpsuser@example.com",
                "password1": "S3cur3P@ss!",
                "password2": "S3cur3P@ss!",
            },
            secure=True,
        )
    # enqueue args: (send_activation_email, user.pk, host, token, protocol)
    args = mock_enqueue.call_args[0]
    protocol = args[4]
    assert protocol == "https"


@pytest.mark.django_db
def test_signup_creates_inactive_user(client):
    with patch("suchar_overflow.users.views.django_rq.enqueue"):
        client.post(
            reverse("users:signup"),
            {
                "username": "inactive_test",
                "email": "inactive@example.com",
                "password1": "S3cur3P@ss!",
                "password2": "S3cur3P@ss!",
            },
        )
    user = User.objects.get(username="inactive_test")
    assert user.is_active is False
