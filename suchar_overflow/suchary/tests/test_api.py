import json
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from suchar_overflow.achievements.cache import suchar_toast_sent_cache_key
from suchar_overflow.achievements.cache import toast_cache_key
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Tag
from suchar_overflow.suchary.models import Vote

if TYPE_CHECKING:
    from django.test import Client

TAGS_URL = "/api/suchary/tags"
VOTE_URL = "/api/suchary/{pk}/vote"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def vote_url(pk: int) -> str:
    return VOTE_URL.format(pk=pk)


def _make_vote_achievement(
    slug: str,
    *,
    event_type: str,
    metric: str,
    threshold: int = 1,
) -> Achievement:
    return Achievement.objects.create(
        slug=slug,
        name=slug,
        description="desc",
        icon_content="<svg/>",
        category=Achievement.Category.LIFETIME,
        event_type=event_type,
        metric=metric,
        threshold=threshold,
    )


@pytest.fixture
def dry_master_achievement() -> Achievement:
    """The "Mistrz Suszu" row (#294).

    Migration 0017 seeds it, but a ``transaction=True`` test elsewhere in the
    suite can flush migration-seeded rows under ``--reuse-db`` (see the
    reuse-db flush note in CLAUDE.md), so tests that assert on it recreate it
    explicitly rather than trusting the baseline.
    """
    achievement, _ = Achievement.objects.update_or_create(
        slug="dry-master",
        defaults={
            "name": "Mistrz Suszu",
            "description": "desc",
            "icon_content": "<svg/>",
            "category": Achievement.Category.LIFETIME,
            "event_type": Achievement.EventType.VOTE_RECEIVED,
            "metric": Achievement.Metric.DRY_MASTER,
            "threshold": 1,
        },
    )
    return achievement


# ---------------------------------------------------------------------------
# list_tags
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_tags_empty(client: Client) -> None:
    response = client.get(TAGS_URL)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.django_db
def test_list_tags_returns_all(client: Client) -> None:
    Tag.objects.create(name="IT", slug="it")
    Tag.objects.create(name="Programowanie", slug="programowanie")

    response = client.get(TAGS_URL)
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 2  # noqa: PLR2004
    slugs = {item["slug"] for item in data}
    assert slugs == {"it", "programowanie"}


@pytest.mark.django_db
def test_list_tags_filtered_by_q(client: Client) -> None:
    Tag.objects.create(name="IT", slug="it")
    Tag.objects.create(name="Python", slug="python")
    Tag.objects.create(name="Programowanie", slug="programowanie")

    response = client.get(TAGS_URL, {"q": "it"})
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    # "IT" matches "it" case-insensitively; "Programowanie" does NOT contain "it"
    names = [item["name"] for item in data]
    assert "IT" in names
    assert "Python" not in names


@pytest.mark.django_db
def test_list_tags_q_empty_string_returns_all(client: Client) -> None:
    Tag.objects.create(name="IT", slug="it")
    Tag.objects.create(name="Python", slug="python")

    response = client.get(TAGS_URL, {"q": ""})
    assert response.status_code == HTTPStatus.OK
    assert len(response.json()) == 2  # noqa: PLR2004


@pytest.mark.django_db
def test_list_tags_capped_at_ten(client: Client) -> None:
    for i in range(15):
        Tag.objects.create(name=f"Tag{i}", slug=f"tag{i}")

    response = client.get(TAGS_URL)
    assert response.status_code == HTTPStatus.OK
    assert len(response.json()) == 10  # noqa: PLR2004


@pytest.mark.django_db
def test_list_tags_schema_fields(client: Client) -> None:
    Tag.objects.create(name="IT", slug="it")

    response = client.get(TAGS_URL)
    item = response.json()[0]
    assert "name" in item
    assert "slug" in item


# ---------------------------------------------------------------------------
# vote_suchar — auth requirement
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_requires_authentication(client: Client) -> None:
    author = make_user("author")
    suchar = Suchar.objects.create(text="Joke", author=author)

    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ---------------------------------------------------------------------------
# vote_suchar — basic toggling
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_funny_toggle_on(client: Client) -> None:
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["funny_count"] == 1
    assert data["dry_count"] == 0
    assert data["user_is_funny"] is True
    assert data["user_is_dry"] is False


@pytest.mark.django_db
def test_vote_funny_toggle_off(client: Client) -> None:
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["funny_count"] == 0
    assert data["user_is_funny"] is False
    assert not Vote.objects.filter(user=voter, suchar=suchar).exists()


@pytest.mark.django_db
def test_vote_dry_toggle_on(client: Client) -> None:
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["dry_count"] == 1
    assert data["funny_count"] == 0
    assert data["user_is_dry"] is True
    assert data["user_is_funny"] is False


@pytest.mark.django_db
def test_vote_both_flags_then_toggle_off_one_keeps_vote(client: Client) -> None:
    """Toggling off one flag while the other stays True must preserve the Vote row."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True, is_dry=True)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["user_is_funny"] is False
    assert data["user_is_dry"] is True
    assert Vote.objects.filter(user=voter, suchar=suchar).exists()


@pytest.mark.django_db
def test_vote_both_flags_off_deletes_vote_row(client: Client) -> None:
    """Toggling the last active flag must delete the Vote row entirely."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_funny=False, is_dry=True)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["user_is_funny"] is False
    assert data["user_is_dry"] is False
    assert not Vote.objects.filter(user=voter, suchar=suchar).exists()


# ---------------------------------------------------------------------------
# vote_suchar — counts accuracy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_response_counts_multiple_voters(client: Client) -> None:
    author = make_user("author")
    voter1 = make_user("voter1")
    voter2 = make_user("voter2")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter1, is_funny=True)
    Vote.objects.create(suchar=suchar, user=voter2, is_dry=True)

    voter3 = make_user("voter3")
    client.force_login(voter3)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["funny_count"] == 2  # noqa: PLR2004
    assert data["dry_count"] == 1


# ---------------------------------------------------------------------------
# vote_suchar — error cases
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_nonexistent_suchar_returns_404(client: Client) -> None:
    voter = make_user("voter")
    client.force_login(voter)

    response = client.post(
        vote_url(99999),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.django_db
def test_vote_invalid_vote_type_returns_422(client: Client) -> None:
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "invalid"}),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.django_db
def test_vote_missing_payload_returns_422(client: Client) -> None:
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# vote_suchar — achievement engine sees the final flag state (issue #247)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_first_funny_vote_immediately_awards_funny_metric(client: Client) -> None:
    """The first funny vote counts toward COUNT_VOTE_FUNNY at once.

    Before #247 the flag was flipped in a follow-up ``save()`` that fires no
    signal, so the engine saw ``is_funny=False`` and the badge lagged a vote.
    """
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    ach = _make_vote_achievement(
        "funny-first",
        event_type=Achievement.EventType.VOTE_CAST,
        metric=Achievement.Metric.COUNT_VOTE_FUNNY,
    )

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert UserAchievement.objects.filter(user=voter, achievement=ach).exists()


@pytest.mark.django_db
def test_first_dry_vote_immediately_awards_dry_metric(client: Client) -> None:
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    ach = _make_vote_achievement(
        "dry-first",
        event_type=Achievement.EventType.VOTE_CAST,
        metric=Achievement.Metric.COUNT_VOTE_DRY,
    )

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert UserAchievement.objects.filter(user=voter, achievement=ach).exists()


@pytest.mark.django_db
def test_first_vote_gives_author_correct_sum_score(client: Client) -> None:
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    ach = _make_vote_achievement(
        "sum-score-1",
        event_type=Achievement.EventType.VOTE_RECEIVED,
        metric=Achievement.Metric.SUM_SCORE,
    )

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert UserAchievement.objects.filter(user=author, achievement=ach).exists()


@pytest.mark.django_db
def test_toggling_dry_on_existing_funny_vote_reevaluates_dry_metric(
    client: Client,
) -> None:
    """#247 direction 3: flipping a flag on an existing vote re-checks
    achievements on the final state instead of waiting for the next vote."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)
    ach = _make_vote_achievement(
        "dry-after-toggle",
        event_type=Achievement.EventType.VOTE_CAST,
        metric=Achievement.Metric.COUNT_VOTE_DRY,
    )
    assert not UserAchievement.objects.filter(user=voter, achievement=ach).exists()

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert UserAchievement.objects.filter(user=voter, achievement=ach).exists()


@pytest.mark.django_db
def test_removing_dry_vote_awards_author_newly_crossed_sum_score(
    client: Client,
) -> None:
    """#247 direction 3: deleting a dry vote raises the author's SUM_SCORE,
    which can cross a threshold that should be awarded right away."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    ach = _make_vote_achievement(
        "sum-score-4",
        event_type=Achievement.EventType.VOTE_RECEIVED,
        metric=Achievement.Metric.SUM_SCORE,
        threshold=4,
    )
    Vote.objects.create(suchar=suchar, user=voter, is_dry=True)  # -1
    for i in range(4):  # +4  ->  net 3, still below the threshold
        Vote.objects.create(
            suchar=suchar,
            user=make_user(f"fan_{i}"),
            is_funny=True,
        )
    assert not UserAchievement.objects.filter(user=author, achievement=ach).exists()

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert not Vote.objects.filter(user=voter, suchar=suchar).exists()
    assert UserAchievement.objects.filter(user=author, achievement=ach).exists()


@pytest.mark.django_db
def test_toggle_after_first_vote_does_not_duplicate_vote_cast_award(
    client: Client,
) -> None:
    """Regression: re-checking on toggle must not double-award or error on an
    achievement the user already owns; COUNT_VOTE_CAST is flag-independent."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    ach = _make_vote_achievement(
        "cast-1",
        event_type=Achievement.EventType.VOTE_CAST,
        metric=Achievement.Metric.COUNT_VOTE_CAST,
    )

    client.force_login(voter)
    for _ in range(2):
        response = client.post(
            vote_url(suchar.pk),
            data=json.dumps({"vote_type": "dry"}),
            content_type="application/json",
        )
        assert response.status_code == HTTPStatus.OK

    assert UserAchievement.objects.filter(user=voter, achievement=ach).count() == 1


# ---------------------------------------------------------------------------
# vote_suchar — first-funny-vote 🥁 toast flag (issue #292)
# ---------------------------------------------------------------------------


def _post_vote(client: Client, suchar_pk: int, vote_type: str) -> None:
    response = client.post(
        vote_url(suchar_pk),
        data=json.dumps({"vote_type": vote_type}),
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK


def _reset_toast_cache(author_pk: int, suchar_pk: int) -> None:
    """Clear both 🥁 keys — the locmem cache is shared across the test session."""
    cache.delete(toast_cache_key(author_pk))
    cache.delete(suchar_toast_sent_cache_key(suchar_pk))


@pytest.mark.django_db
def test_first_funny_vote_sets_author_toast_flag(client: Client) -> None:
    author = make_user("rimshot_author")
    voter = make_user("rimshot_voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(voter)
    _post_vote(client, suchar.pk, "funny")

    assert cache.get(toast_cache_key(author.pk)) is True


@pytest.mark.django_db
def test_second_funny_vote_does_not_set_toast_flag(client: Client) -> None:
    author = make_user("rimshot_author_2")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=make_user("rimshot_first"), is_funny=True)
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(make_user("rimshot_second"))
    _post_vote(client, suchar.pk, "funny")

    assert cache.get(toast_cache_key(author.pk)) is None


@pytest.mark.django_db
def test_dry_vote_does_not_set_toast_flag(client: Client) -> None:
    author = make_user("rimshot_author_dry")
    voter = make_user("rimshot_voter_dry")
    suchar = Suchar.objects.create(text="Joke", author=author)
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(voter)
    _post_vote(client, suchar.pk, "dry")

    assert cache.get(toast_cache_key(author.pk)) is None


@pytest.mark.django_db
def test_dry_vote_on_suchar_with_one_funny_does_not_refire_toast(
    client: Client,
) -> None:
    """The `vote_type == "funny"` guard, not just the count, must gate the toast.

    A suchar already sitting at exactly one funny vote has
    ``counts["community_funny"] == 1``; a *dry* vote landing on it must not be
    mistaken for the 0→1 funny transition.
    """
    author = make_user("rimshot_author_onefunny")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(
        suchar=suchar,
        user=make_user("rimshot_the_funny_one"),
        is_funny=True,
    )
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(make_user("rimshot_dry_latecomer"))
    _post_vote(client, suchar.pk, "dry")

    assert cache.get(toast_cache_key(author.pk)) is None


@pytest.mark.django_db
def test_author_self_funny_vote_does_not_set_toast_flag(client: Client) -> None:
    author = make_user("rimshot_selfvoter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(author)
    _post_vote(client, suchar.pk, "funny")

    assert cache.get(toast_cache_key(author.pk)) is None


@pytest.mark.django_db
def test_author_self_vote_first_still_toasts_on_first_community_vote(
    client: Client,
) -> None:
    """Self-vote must not permanently eat the toast (PR #305 review, point 1).

    The author funny-votes their own suchar first; the toast is skipped. When
    a *real* voter then lands the first community funny vote,
    ``community_funny`` is 1 and the author still gets their 🥁.
    """
    author = make_user("rimshot_selffirst_author")
    suchar = Suchar.objects.create(text="Joke", author=author)
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(author)
    _post_vote(client, suchar.pk, "funny")
    assert cache.get(toast_cache_key(author.pk)) is None

    client.force_login(make_user("rimshot_selffirst_fan"))
    _post_vote(client, suchar.pk, "funny")

    assert cache.get(toast_cache_key(author.pk)) is True


@pytest.mark.django_db
def test_toggling_funny_on_existing_vote_sets_toast_flag(client: Client) -> None:
    """A dry-only vote flipped to funny is still the suchar's 0→1 funny move."""
    author = make_user("rimshot_author_toggle")
    voter = make_user("rimshot_voter_toggle")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_dry=True)
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(voter)
    _post_vote(client, suchar.pk, "funny")

    assert cache.get(toast_cache_key(author.pk)) is True


@pytest.mark.django_db
def test_removing_only_funny_vote_does_not_set_toast_flag(client: Client) -> None:
    author = make_user("rimshot_author_remove")
    voter = make_user("rimshot_voter_remove")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(voter)
    _post_vote(client, suchar.pk, "funny")  # toggles the only funny vote off

    assert not Vote.objects.filter(user=voter, suchar=suchar).exists()
    assert cache.get(toast_cache_key(author.pk)) is None


@pytest.mark.django_db
def test_toast_fires_only_once_per_suchar_across_revotes(client: Client) -> None:
    """Un-voting then re-voting a suchar back through 0→1 must not re-toast.

    ``mark_suchar_toast_sent`` latches per suchar (PR #305 review, point 5).
    """
    author = make_user("rimshot_once_author")
    voter = make_user("rimshot_once_voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(voter)
    _post_vote(client, suchar.pk, "funny")  # 0 -> 1, toasts
    assert cache.get(toast_cache_key(author.pk)) is True
    cache.delete(toast_cache_key(author.pk))

    _post_vote(client, suchar.pk, "funny")  # 1 -> 0, removes the vote
    _post_vote(client, suchar.pk, "funny")  # 0 -> 1 again

    assert cache.get(toast_cache_key(author.pk)) is None


@pytest.mark.django_db
def test_first_funny_vote_adds_no_query_for_the_toast(client: Client) -> None:
    """`community_funny` rides the existing aggregate — no extra SQL round trip.

    The author-excluding count that drives the toast is a third aggregate on
    the *same* ``suchar.votes.aggregate(...)`` call, so it lands in exactly one
    query alongside ``funny`` / ``dry`` — never a separate ``SELECT`` and never
    a standalone author lookup (PR #305 review, point 1).
    """
    author = make_user("rimshot_noquery_author")
    voter = make_user("rimshot_noquery_voter")
    suchar = Suchar.objects.create(text="Joke", author=author)
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(voter)
    with CaptureQueriesContext(connection) as ctx:
        _post_vote(client, suchar.pk, "funny")

    community_funny_queries = [
        q["sql"] for q in ctx.captured_queries if "community_funny" in q["sql"]
    ]
    assert len(community_funny_queries) == 1, community_funny_queries
    # Same statement carries the other two counts — it is one aggregate call.
    assert '"funny"' in community_funny_queries[0]
    assert '"dry"' in community_funny_queries[0]
    # And it never had to reach into users_user to exclude the author.
    assert '"users_user"' not in community_funny_queries[0]
    assert cache.get(toast_cache_key(author.pk)) is True


# ---------------------------------------------------------------------------
# vote_suchar — query efficiency (issue #203, point 1)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_loads_author_with_the_suchar(client: Client) -> None:
    """The suchar lookup must join the author in.

    ``check_vote_achievements`` reads ``instance.suchar.author`` for every
    newly created Vote; without ``select_related("author")`` on the view's
    ``get_object_or_404`` that costs one extra query per first-time vote.
    """
    author = make_user("selrel_author")
    voter = make_user("selrel_voter")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(voter)
    with CaptureQueriesContext(connection) as ctx:
        response = client.post(
            vote_url(suchar.pk),
            data=json.dumps({"vote_type": "funny"}),
            content_type="application/json",
        )
    assert response.status_code == HTTPStatus.OK
    # The vote must actually be new — the signal (and therefore the author
    # access this test guards) only fires on created=True.
    assert Vote.objects.filter(user=voter, suchar=suchar).exists()

    suchar_selects = [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].startswith("SELECT") and '"suchary_suchar"' in q["sql"]
    ]
    assert suchar_selects, "expected the endpoint to load the suchar"
    assert any('"users_user"' in sql for sql in suchar_selects), (
        "the suchar must be fetched with its author joined in "
        f"(queries seen: {suchar_selects})"
    )

    # The effect issue #203 point 1 actually asks for: no separate author
    # re-fetch on top of that join. The voter's own row is loaded by auth
    # middleware; the author's row must never be fetched on its own.
    standalone_author_lookups = [
        q["sql"]
        for q in ctx.captured_queries
        if f'"users_user"."id" = {author.pk}' in q["sql"]
        and '"suchary_suchar"' not in q["sql"]
    ]
    assert not standalone_author_lookups, (
        "the author was re-fetched in a standalone query despite select_related "
        f"({standalone_author_lookups})"
    )


# ---------------------------------------------------------------------------
# vote_suchar — "Mistrz Suszu" / overdried latch (issue #294)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("dry_master_achievement")
def test_vote_endpoint_latches_overdried_and_awards_dry_master(
    client: Client,
) -> None:
    """The 10th dry vote in-window, cast through the endpoint, latches the
    suchar and awards the migration-seeded "dry-master" achievement."""
    author = make_user("dm_author")
    suchar = Suchar.objects.create(text="Joke", author=author)
    for i in range(9):
        Vote.objects.create(
            suchar=suchar,
            user=make_user(f"dm_dry_{i}"),
            is_dry=True,
        )
    assert not suchar.is_overdried

    last_voter = make_user("dm_last")
    client.force_login(last_voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    suchar.refresh_from_db()
    assert suchar.is_overdried is True
    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug="dry-master",
    ).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("dry_master_achievement")
def test_vote_endpoint_removing_last_funny_latches_overdried(
    client: Client,
) -> None:
    """Pulling the only funny vote through the endpoint emits vote_changed
    with the suchar, so the overdried latch can still fire in-window (#294)."""
    author = make_user("dm2_author")
    suchar = Suchar.objects.create(text="Joke", author=author)
    # Funny vote first, so the latch stays blocked while the dry votes land.
    funny_voter = make_user("dm2_funny")
    Vote.objects.create(suchar=suchar, user=funny_voter, is_funny=True)
    for i in range(10):
        Vote.objects.create(
            suchar=suchar,
            user=make_user(f"dm2_dry_{i}"),
            is_dry=True,
        )
    suchar.refresh_from_db()
    assert suchar.is_overdried is False

    client.force_login(funny_voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert not Vote.objects.filter(user=funny_voter, suchar=suchar).exists()
    suchar.refresh_from_db()
    assert suchar.is_overdried is True
    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug="dry-master",
    ).exists()
