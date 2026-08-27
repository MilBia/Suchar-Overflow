"""Extra UserDetailView tests: scheduled suchary, rank, heatmap, signup."""

import datetime
from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Tag
from suchar_overflow.suchary.models import Vote
from suchar_overflow.users.views import UserDetailView
from suchar_overflow.users.views import user_rank_cache_key

if TYPE_CHECKING:
    from django.test import Client

    # `User` below is a runtime value (get_user_model()), so mypy rejects it
    # as an annotation — alias the concrete model class for typing instead.
    from suchar_overflow.users.models import User as UserType

User = get_user_model()


def detail_url(username: str) -> str:
    return reverse("users:detail", kwargs={"username": username})


# ===========================================================================
# Scheduled suchary — owner-only
# ===========================================================================


@pytest.mark.django_db
def test_scheduled_suchary_visible_to_owner(client: Client) -> None:
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
def test_scheduled_suchary_hidden_from_other_user(client: Client) -> None:
    owner = make_user("owner2")
    visitor = make_user("visitor2")
    future = timezone.now() + datetime.timedelta(days=1)
    Suchar.objects.create(text="Hidden scheduled", author=owner, published_at=future)

    client.force_login(visitor)
    response = client.get(detail_url("owner2"))
    assert response.status_code == HTTPStatus.OK
    # scheduled_suchary context key must not exist for non-owner
    assert "scheduled_suchary" not in response.context


@pytest.mark.django_db
def test_scheduled_suchary_tags_do_not_n_plus_one(client: Client) -> None:
    """Regression test for issue #199.

    `user_detail.html` iterates `suchar.tags.all` for every scheduled suchar.
    Without `prefetch_related("tags")` on the `scheduled_suchary` queryset
    that costs one extra query per scheduled suchar. The tag-query count must
    stay constant regardless of how many scheduled suchary the owner has.

    Goes through a full `client.get()` render (not `_build_context`
    directly) so it also covers the template — a regression like #183
    (`tags.first()` dropping the prefetch cache) would be invisible to a
    Python-level `suchar.tags.all()` loop. Same shape as
    `stats/tests/test_views.py::test_full_page_render_does_not_n_plus_one_on_tags`.
    """
    owner = make_user("prefetch_owner")
    tag = Tag.objects.create(name="Programowanie", slug="programowanie")
    future = timezone.now() + datetime.timedelta(days=1)
    scheduled_count = 3
    for i in range(scheduled_count):
        suchar = Suchar.objects.create(
            text=f"Scheduled joke {i}",
            author=owner,
            published_at=future,
        )
        suchar.tags.add(tag)

    client.force_login(owner)
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(detail_url("prefetch_owner"))

    assert response.status_code == HTTPStatus.OK
    # Guard against a vacuous pass: the scheduled suchary really are rendered.
    assert len(response.context["scheduled_suchary"]) == scheduled_count

    tag_queries = [q for q in ctx.captured_queries if "suchary_tag" in q["sql"]]
    max_tag_queries = 2  # one prefetch query, generously allow one more
    # Seed enough scheduled suchary that an N+1 would actually breach the
    # threshold — otherwise the assertion below can't detect the regression.
    assert scheduled_count > max_tag_queries
    assert len(tag_queries) <= max_tag_queries


# ===========================================================================
# Global rank
# ===========================================================================


@pytest.mark.django_db
def test_global_rank_is_one_for_top_user(client: Client) -> None:
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
def test_global_rank_increases_when_others_have_more_votes(client: Client) -> None:
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
def test_global_rank_is_one_when_user_has_no_votes(client: Client) -> None:
    user = make_user("novotes")
    Suchar.objects.create(text="joke", author=user)

    client.force_login(user)
    response = client.get(detail_url("novotes"))
    # No users have MORE votes, so rank = 0 + 1 = 1
    assert response.context["global_rank"] == 1


@pytest.mark.django_db
def test_global_rank_ignores_dry_votes_received(client: Client) -> None:
    """Regression for #195.

    The rank compares the profile owner against other users' *funny* vote
    counts. It used to feed the owner's total (funny + dry) count into that
    comparison, so dry votes inflated their position: `dry_only` below came
    out as rank 1 ahead of `funny_only`, who has three times as many funny
    votes.
    """
    dry_only = make_user("dry_only")
    funny_only = make_user("funny_only")
    s_dry = Suchar.objects.create(text="a dry one", author=dry_only)
    s_funny = Suchar.objects.create(text="a funny one", author=funny_only)

    for i in range(5):
        Vote.objects.create(suchar=s_dry, user=make_user(f"dv{i}"), is_dry=True)
    for i in range(3):
        Vote.objects.create(suchar=s_funny, user=make_user(f"fv{i}"), is_funny=True)

    client.force_login(dry_only)
    response = client.get(detail_url("dry_only"))
    # 5 dry votes are worth nothing here; funny_only's 3 funny votes rank higher.
    assert response.context["global_rank"] == 2  # noqa: PLR2004


@pytest.mark.django_db
def test_global_rank_ties_share_position() -> None:
    """Standard competition ranking: users tied on funny votes share a rank.

    PR #222 picked this semantics deliberately (the leaderboard breaks ties by
    pk instead); pin it here so a future change to `_compute_rank` can't drop it
    silently. Tested against `_compute_rank` directly — the rank cache is keyed
    by score, so two tied owners would otherwise just read the same entry and
    the assertion would pass even for broken counting.
    """
    for name in ("tie_a", "tie_b"):
        owner = make_user(name)
        s = Suchar.objects.create(text=f"joke {name}", author=owner)
        Vote.objects.create(suchar=s, user=make_user(f"v_{name}"), is_funny=True)
    leader = make_user("tie_leader")
    s_lead = Suchar.objects.create(text="top joke", author=leader)
    for i in range(3):
        Vote.objects.create(suchar=s_lead, user=make_user(f"lv{i}"), is_funny=True)

    # tie_a and tie_b both sit on 1 funny vote, behind the single leader on 3.
    assert UserDetailView._compute_rank(1) == 2  # noqa: SLF001, PLR2004
    assert UserDetailView._compute_rank(3) == 1  # noqa: SLF001


@pytest.mark.django_db
def test_global_rank_second_view_within_ttl_does_not_recompute(client: Client) -> None:
    """Acceptance criterion from #195: a second profile view inside the TTL
    serves the cached rank instead of re-running the aggregate.
    """
    user = make_user("rank_cache_u")
    suchar = Suchar.objects.create(text="joke", author=user)
    Vote.objects.create(suchar=suchar, user=make_user("rank_cache_v"), is_funny=True)

    client.force_login(user)
    real_compute = UserDetailView._compute_rank  # noqa: SLF001
    with patch.object(
        UserDetailView,
        "_compute_rank",
        wraps=real_compute,
    ) as compute_spy:
        first = client.get(detail_url("rank_cache_u")).context["global_rank"]
        second = client.get(detail_url("rank_cache_u")).context["global_rank"]

    assert first == second == 1
    compute_spy.assert_called_once()


@pytest.mark.django_db
def test_global_rank_recomputes_after_cache_expiry(client: Client) -> None:
    """Deleting the key stands in for TTL expiry (the view has no lever to
    expire it early) — this only proves a recomputed rank reflects fresh DB
    state, not that the TTL itself fires.
    """
    user = make_user("rank_stale_u")
    Suchar.objects.create(text="joke", author=user)

    client.force_login(user)
    assert client.get(detail_url("rank_stale_u")).context["global_rank"] == 1

    rival = make_user("rank_stale_rival")
    s_rival = Suchar.objects.create(text="better joke", author=rival)
    Vote.objects.create(suchar=s_rival, user=make_user("rank_stale_v"), is_funny=True)

    # Still cached under the owner's own score (0 funny votes), so the new rival
    # is invisible — the owner's key didn't change.
    assert client.get(detail_url("rank_stale_u")).context["global_rank"] == 1

    cache.delete(user_rank_cache_key(0))
    response = client.get(detail_url("rank_stale_u"))
    assert response.context["global_rank"] == 2  # noqa: PLR2004


@pytest.mark.django_db
def test_global_rank_reflects_owner_score_change_within_ttl(client: Client) -> None:
    """The rank cache is keyed by the owner's own funny total, so a change to
    that total is served from a different key — the owner's own progress is
    never hidden by the TTL, only other users' votes are. Under the old pk key
    this second view would still show the stale rank.
    """
    owner = make_user("own_change_u")
    rival = make_user("own_change_rival")
    s_rival = Suchar.objects.create(text="rival joke", author=rival)
    for i in range(2):
        Vote.objects.create(suchar=s_rival, user=make_user(f"ocr{i}"), is_funny=True)

    client.force_login(owner)
    # 0 funny votes → behind the rival on 2.
    before = client.get(detail_url("own_change_u")).context["global_rank"]
    assert before == 2  # noqa: PLR2004

    s_owner = Suchar.objects.create(text="owner joke", author=owner)
    for i in range(5):
        Vote.objects.create(suchar=s_owner, user=make_user(f"oco{i}"), is_funny=True)

    # No invalidation ran, but the owner's funny total is now 5 — a different
    # cache key — so the improved rank shows on the very next view.
    after = client.get(detail_url("own_change_u")).context["global_rank"]
    assert after == 1


# ===========================================================================
# Heatmap
# ===========================================================================


@pytest.mark.django_db
def test_heatmap_weeks_is_list(client: Client) -> None:
    user = make_user("heatmap_u")
    client.force_login(user)
    response = client.get(detail_url("heatmap_u"))
    assert isinstance(response.context["heatmap_weeks"], list)


@pytest.mark.django_db
def test_heatmap_weeks_each_has_days_and_month_label(client: Client) -> None:
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
def test_heatmap_level_buckets(client: Client) -> None:
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
def test_heatmap_starts_aligned_to_monday(client: Client) -> None:
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
def test_best_joke_is_highest_funny_vote_suchar(client: Client) -> None:
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
def test_best_joke_is_none_when_no_suchary(client: Client) -> None:
    user = make_user("bestjoke_empty")
    client.force_login(user)
    response = client.get(detail_url("bestjoke_empty"))
    assert response.context["best_joke"] is None


# ===========================================================================
# Activity chart context
# ===========================================================================


@pytest.mark.django_db
def test_activity_labels_and_values_are_lists(client: Client) -> None:
    user = make_user("chart_u")
    client.force_login(user)
    response = client.get(detail_url("chart_u"))
    assert isinstance(response.context["activity_labels"], list)
    assert isinstance(response.context["activity_values"], list)


@pytest.mark.django_db
def test_reception_data_is_list_of_two(client: Client) -> None:
    user = make_user("recv_u")
    client.force_login(user)
    response = client.get(detail_url("recv_u"))
    data = response.context["reception_data"]
    assert isinstance(data, list)
    assert len(data) == 2  # noqa: PLR2004


# ===========================================================================
# SignupView — protocol detection
# ===========================================================================


@pytest.mark.django_db(transaction=True)
def test_signup_uses_http_protocol_when_not_secure(client: Client) -> None:
    client.post(
        reverse("users:signup"),
        {
            "username": "httpuser",
            "email": "httpuser@example.com",
            "password1": "S3cur3P@ss!",
            "password2": "S3cur3P@ss!",
        },
    )
    assert len(mail.outbox) == 1
    assert "http://" in mail.outbox[0].body
    assert "https://" not in mail.outbox[0].body


@pytest.mark.django_db(transaction=True)
def test_signup_uses_https_protocol_when_secure(client: Client) -> None:
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
    assert len(mail.outbox) == 1
    assert "https://" in mail.outbox[0].body


@pytest.mark.django_db(transaction=True)
def test_signup_creates_inactive_user(client: Client) -> None:
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


# ---------------------------------------------------------------------------
# Consolidated form partial (snippets/form_field.html) rendering
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_password_change_form_uses_shared_error_bubble_styling(client: Client) -> None:
    user = make_user("pwchange_user", password="OriginalPass123")  # noqa: S106
    client.force_login(user)

    response = client.post(
        reverse("password_change"),
        {
            "old_password": "wrong-password",
            "new_password1": "NewSecretPass123",
            "new_password2": "NewSecretPass123",
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert "error-bubble" in response.content.decode()


@pytest.mark.django_db
def test_user_update_form_uses_shared_field_partial(client: Client) -> None:
    user = make_user("form_field_user")
    client.force_login(user)

    response = client.get(reverse("users:update"))

    assert response.status_code == HTTPStatus.OK
    content = response.content.decode()
    assert "error-bubble-container" not in content
    assert 'class="form-label"' in content


# ===========================================================================
# Achievement badges — query count (issue #198)
# ===========================================================================


def _award_achievements(user: UserType, slugs: list[str]) -> None:
    for slug in slugs:
        achievement = Achievement.objects.create(
            name=f"Achievement {slug}",
            slug=slug,
            description=f"Description {slug}",
            icon_content="<svg></svg>",
        )
        UserAchievement.objects.create(user=user, achievement=achievement)


def _achievement_queries(ctx: CaptureQueriesContext) -> list[str]:
    return [
        q["sql"]
        for q in ctx.captured_queries
        if "achievements_achievement" in q["sql"]
        or "achievements_userachievement" in q["sql"]
    ]


@pytest.mark.django_db
def test_profile_badges_query_count_does_not_grow_with_badge_count(
    client: Client,
) -> None:
    """Regression test for issue #198.

    The template used to call `object.user_achievements.exists` and
    `.all` (two queries on the same relation) and then dereference
    `user_ach.achievement` per badge without `select_related`, so the
    profile page cost `2 + N` achievement queries. Rendering must now stay
    flat regardless of how many badges the profile owner has.
    """
    owner = make_user("badge_owner")
    viewer = make_user("badge_viewer")
    client.force_login(viewer)

    # `_achievement_queries` also catches the viewer's own `achievements_bell`
    # context-processor query, which is cached after the first hit — clear it
    # before each measurement so the only thing that varies between the two
    # requests is the owner's badge fetch.
    _award_achievements(owner, ["badge-a", "badge-b"])
    cache.clear()
    with CaptureQueriesContext(connection) as first_ctx:
        first_response = client.get(detail_url("badge_owner"))
    first_queries = _achievement_queries(first_ctx)

    _award_achievements(owner, ["badge-c", "badge-d", "badge-e"])
    cache.clear()
    with CaptureQueriesContext(connection) as second_ctx:
        second_response = client.get(detail_url("badge_owner"))
    second_queries = _achievement_queries(second_ctx)

    # Guard against a vacuous pass: the badges really are rendered.
    assert first_response.content.decode().count("achievement-container") == 2  # noqa: PLR2004
    assert second_response.content.decode().count("achievement-container") == 5  # noqa: PLR2004

    assert len(second_queries) == len(first_queries), (
        f"Liczba zapytań o osiągnięcia rośnie z liczbą odznak: "
        f"{len(first_queries)} (2 odznaki) -> {len(second_queries)} (5 odznak)"
    )


@pytest.mark.django_db
def test_profile_without_badges_renders_empty_state(client: Client) -> None:
    owner = make_user("badgeless_owner")
    viewer = make_user("badgeless_viewer")
    client.force_login(viewer)

    response = client.get(detail_url("badgeless_owner"))

    assert response.status_code == HTTPStatus.OK
    assert response.context["user_achievements"] == []
    assert "achievement-container" not in response.content.decode()
    assert not UserAchievement.objects.filter(user=owner).exists()


@pytest.mark.django_db
def test_build_context_fetches_badges_in_one_query() -> None:
    """Acceptance criterion of issue #198: exactly one query for the badges.

    Exercised directly on `_build_context` (like the leaderboard precedent in
    `stats/tests/test_views.py`) so the `achievements_bell` context processor
    and the session lookups of a full request don't blur the count.
    """
    owner = make_user("badge_query_owner")
    _award_achievements(owner, ["badge-q1", "badge-q2", "badge-q3"])

    with CaptureQueriesContext(connection) as ctx:
        context = UserDetailView()._build_context(owner, is_owner=False)  # noqa: SLF001

    badge_queries = [
        q["sql"] for q in ctx.captured_queries if "achievements_" in q["sql"]
    ]
    assert len(badge_queries) == 1
    assert len(context["user_achievements"]) == 3  # noqa: PLR2004


@pytest.mark.django_db
def test_build_context_orders_badges_newest_first() -> None:
    """The JOIN leaves row order undefined, so the view sorts explicitly.

    Newest-first matches the `achievements_bell` context processor and keeps
    the badge order stable across page loads.
    """
    owner = make_user("badge_order_owner")
    # `awarded_at` is `auto_now_add`, so the rows are created oldest-first.
    _award_achievements(owner, ["badge-o1", "badge-o2", "badge-o3"])

    context = UserDetailView()._build_context(owner, is_owner=False)  # noqa: SLF001

    slugs = [ua.achievement.slug for ua in context["user_achievements"]]
    assert slugs == ["badge-o3", "badge-o2", "badge-o1"]
