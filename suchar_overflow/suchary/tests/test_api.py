import json
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.translation import gettext

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

    from suchar_overflow.users.models import User

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


def _tag_on_published_suchar(name: str, slug: str, author: User) -> Tag:
    """Create a Tag and attach it to one already-published suchar."""
    tag = Tag.objects.create(name=name, slug=slug)
    suchar = Suchar.objects.create(text=f"joke {slug}", author=author)
    suchar.tags.add(tag)
    return tag


@pytest.mark.django_db
def test_list_tags_empty(client: Client) -> None:
    response = client.get(TAGS_URL)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.django_db
def test_list_tags_returns_tags_on_published_suchary(client: Client) -> None:
    author = make_user("tagger")
    _tag_on_published_suchar("IT", "it", author)
    _tag_on_published_suchar("Programowanie", "programowanie", author)

    response = client.get(TAGS_URL)
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 2  # noqa: PLR2004
    slugs = {item["slug"] for item in data}
    assert slugs == {"it", "programowanie"}


@pytest.mark.django_db
def test_list_tags_excludes_tag_only_on_scheduled_suchar(client: Client) -> None:
    """A tag used only on a not-yet-published suchar must not leak into
    autocomplete — a stranger could otherwise infer someone is drafting on a
    topic before it goes live (#389).
    """
    author = make_user("tagger")
    _tag_on_published_suchar("Live", "live", author)

    secret = Tag.objects.create(name="Secret", slug="secret")
    scheduled = Suchar.objects.create(
        text="scheduled joke",
        author=author,
        published_at=timezone.now() + timedelta(days=1),
    )
    scheduled.tags.add(secret)

    response = client.get(TAGS_URL)
    slugs = {item["slug"] for item in response.json()}
    assert slugs == {"live"}


@pytest.mark.django_db
def test_list_tags_includes_tag_shared_by_published_and_scheduled(
    client: Client,
) -> None:
    """A tag on both a published and a scheduled suchar still shows — the
    published use already makes it public.
    """
    author = make_user("tagger")
    tag = _tag_on_published_suchar("Shared", "shared", author)
    scheduled = Suchar.objects.create(
        text="scheduled joke",
        author=author,
        published_at=timezone.now() + timedelta(days=1),
    )
    scheduled.tags.add(tag)

    response = client.get(TAGS_URL)
    assert [item["slug"] for item in response.json()] == ["shared"]


@pytest.mark.django_db
def test_list_tags_no_duplicate_for_tag_on_multiple_published_suchary(
    client: Client,
) -> None:
    author = make_user("tagger")
    tag = Tag.objects.create(name="Popular", slug="popular")
    for i in range(3):
        suchar = Suchar.objects.create(text=f"joke {i}", author=author)
        suchar.tags.add(tag)

    response = client.get(TAGS_URL)
    assert [item["slug"] for item in response.json()] == ["popular"]


@pytest.mark.django_db
def test_list_tags_filtered_by_q(client: Client) -> None:
    author = make_user("tagger")
    _tag_on_published_suchar("IT", "it", author)
    _tag_on_published_suchar("Python", "python", author)
    _tag_on_published_suchar("Programowanie", "programowanie", author)

    response = client.get(TAGS_URL, {"q": "it"})
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    # "IT" matches "it" case-insensitively; "Programowanie" does NOT contain "it"
    names = [item["name"] for item in data]
    assert "IT" in names
    assert "Python" not in names


@pytest.mark.django_db
def test_list_tags_q_empty_string_returns_all_published(client: Client) -> None:
    author = make_user("tagger")
    _tag_on_published_suchar("IT", "it", author)
    _tag_on_published_suchar("Python", "python", author)

    response = client.get(TAGS_URL, {"q": ""})
    assert response.status_code == HTTPStatus.OK
    assert len(response.json()) == 2  # noqa: PLR2004


@pytest.mark.django_db
def test_list_tags_capped_at_ten(client: Client) -> None:
    author = make_user("tagger")
    for i in range(15):
        _tag_on_published_suchar(f"Tag{i:02d}", f"tag{i:02d}", author)

    response = client.get(TAGS_URL)
    assert response.status_code == HTTPStatus.OK
    assert len(response.json()) == 10  # noqa: PLR2004


@pytest.mark.django_db
def test_list_tags_ordered_by_name(client: Client) -> None:
    author = make_user("tagger")
    _tag_on_published_suchar("Zeta", "zeta", author)
    _tag_on_published_suchar("Alpha", "alpha", author)
    _tag_on_published_suchar("Mu", "mu", author)

    response = client.get(TAGS_URL)
    assert [item["name"] for item in response.json()] == ["Alpha", "Mu", "Zeta"]


@pytest.mark.django_db
def test_list_tags_schema_fields(client: Client) -> None:
    author = make_user("tagger")
    _tag_on_published_suchar("IT", "it", author)

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
def test_vote_unpublished_suchar_returns_404(client: Client) -> None:
    """A scheduled suchar must be indistinguishable from a missing one (#331).

    Otherwise a guessed/sequential PK lets a voter inflate counts and trigger
    achievements/toasts on a suchar nobody else can see yet, and skew the
    best-suchar award window (which counts the period a suchar was
    *published* in — see ``find_best_suchary``, #371).
    """
    author = make_user("scheduled_author")
    voter = make_user("scheduled_voter")
    suchar = Suchar.objects.create(
        text="Joke from the future",
        author=author,
        published_at=timezone.now() + timedelta(days=1),
    )
    ach = _make_vote_achievement(
        "unpublished-funny",
        event_type=Achievement.EventType.VOTE_CAST,
        metric=Achievement.Metric.COUNT_VOTE_FUNNY,
    )
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert not Vote.objects.filter(user=voter, suchar=suchar).exists()
    assert not UserAchievement.objects.filter(user=voter, achievement=ach).exists()
    assert cache.get(toast_cache_key(author.pk)) is None


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_vote_unpublished_suchar_body_matches_nonexistent_suchar_body(
    client: Client,
) -> None:
    """The 404 body must be byte-identical to a genuinely missing PK's (#331).

    Under ``DEBUG=False`` (the default in both ``test``/``production``
    settings — see CLAUDE.md's settings-architecture notes) django-ninja's
    default 404 handler already hardcodes a bare ``{"detail": "Not Found"}``
    for *any* ``Http404``, so this parity would hold even without folding the
    filter into the queryset. ``DEBUG=True`` is what makes the two code paths
    actually observably different: ninja appends ``f": {exc}"`` to the
    message, and ``get_object_or_404`` vs. a second, bare ``raise Http404``
    carry different (or absent) exception text — this is the regression this
    test is meant to catch, and it only fires under this override.
    """
    author = make_user("scheduled_author_parity")
    voter = make_user("scheduled_voter_parity")
    suchar = Suchar.objects.create(
        text="Joke from the future",
        author=author,
        published_at=timezone.now() + timedelta(days=1),
    )

    client.force_login(voter)
    scheduled_response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )
    nonexistent_response = client.post(
        vote_url(99999),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert scheduled_response.status_code == HTTPStatus.NOT_FOUND
    assert nonexistent_response.status_code == HTTPStatus.NOT_FOUND
    assert scheduled_response.json() == nonexistent_response.json()


@pytest.mark.django_db
def test_vote_unpublished_suchar_dry_vote_returns_404(client: Client) -> None:
    """The dry-vote path is blocked the same way — including the
    ``is_overdried`` latch, which must never run for a rejected vote."""
    author = make_user("scheduled_author_dry")
    voter = make_user("scheduled_voter_dry")
    suchar = Suchar.objects.create(
        text="Joke from the future",
        author=author,
        published_at=timezone.now() + timedelta(days=1),
    )

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert not Vote.objects.filter(user=voter, suchar=suchar).exists()
    suchar.refresh_from_db()
    assert suchar.is_overdried is False


@pytest.mark.django_db
def test_author_voting_own_scheduled_suchar_returns_404(client: Client) -> None:
    """An author probing their own scheduled suchar's PK gets the same 404 —
    and, since the vote never happens, no #299 self-dry-vote wink toast."""
    author = make_user("scheduled_self_author")
    suchar = Suchar.objects.create(
        text="Joke from the future",
        author=author,
        published_at=timezone.now() + timedelta(days=1),
    )

    client.force_login(author)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert not Vote.objects.filter(user=author, suchar=suchar).exists()


@pytest.mark.django_db
def test_vote_suchar_published_a_moment_ago_returns_200(client: Client) -> None:
    """Boundary check on the safe side: a suchar published a moment ago is
    votable. Uses a small offset rather than an exact ``== timezone.now()``
    comparison, which would be flaky (the filter runs at whatever instant the
    request hits the DB, not at fixture-creation time)."""
    author = make_user("just_published_author")
    voter = make_user("just_published_voter")
    suchar = Suchar.objects.create(
        text="Joke from moments ago",
        author=author,
        published_at=timezone.now() - timedelta(seconds=2),
    )

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_vote_suchar_published_a_moment_from_now_returns_404(client: Client) -> None:
    """Boundary check on the blocked side, mirroring the test above."""
    author = make_user("almost_published_author")
    voter = make_user("almost_published_voter")
    suchar = Suchar.objects.create(
        text="Joke from moments in the future",
        author=author,
        published_at=timezone.now() + timedelta(seconds=2),
    )

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
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
    """Once a suchar has toasted its author, a later community funny vote must
    not re-fire it — the per-suchar ``mark_suchar_toast_sent`` latch holds."""
    author = make_user("rimshot_author_2")
    suchar = Suchar.objects.create(text="Joke", author=author)
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(make_user("rimshot_first"))
    _post_vote(client, suchar.pk, "funny")  # 0 -> 1: toasts and latches
    assert cache.get(toast_cache_key(author.pk)) is True
    cache.delete(toast_cache_key(author.pk))

    client.force_login(make_user("rimshot_second"))
    _post_vote(client, suchar.pk, "funny")

    assert cache.get(toast_cache_key(author.pk)) is None


@pytest.mark.django_db
def test_concurrent_first_funny_votes_do_not_both_miss_the_toast(
    client: Client,
) -> None:
    """Two near-simultaneous first community funny votes must still toast once
    (#334).

    ``community_funny`` is recounted with a fresh aggregate after every vote
    and is not locked. Two non-authors voting funny close together can each see
    the other's INSERT already committed, i.e. ``community_funny == 2``, so the
    old ``== 1`` predicate fired for neither. ``>= 1`` plus the atomic
    ``mark_suchar_toast_sent`` latch fires exactly once instead. A pre-existing
    funny vote created straight in the DB (never through the endpoint, so it
    never consumed the latch) stands in for the other racer.
    """
    author = make_user("rimshot_race_author")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(
        suchar=suchar,
        user=make_user("rimshot_race_a"),
        is_funny=True,
    )
    _reset_toast_cache(author.pk, suchar.pk)

    client.force_login(make_user("rimshot_race_b"))
    _post_vote(client, suchar.pk, "funny")  # community_funny == 2 at the check
    assert cache.get(toast_cache_key(author.pk)) is True

    # …and it stays a once-per-suchar event.
    cache.delete(toast_cache_key(author.pk))
    client.force_login(make_user("rimshot_race_c"))
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
    assert response.json()["is_overdried"] is True
    suchar.refresh_from_db()
    assert suchar.is_overdried is True
    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug="dry-master",
    ).exists()


@pytest.mark.django_db
def test_vote_response_is_overdried_false_for_a_normal_vote(client: Client) -> None:
    author = make_user("nd_author")
    suchar = Suchar.objects.create(text="Joke", author=author)
    voter = make_user("nd_voter")

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["is_overdried"] is False


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
    assert response.json()["is_overdried"] is True
    assert not Vote.objects.filter(user=funny_voter, suchar=suchar).exists()
    suchar.refresh_from_db()
    assert suchar.is_overdried is True
    assert UserAchievement.objects.filter(
        user=author,
        achievement__slug="dry-master",
    ).exists()


# ---------------------------------------------------------------------------
# vote_suchar — self dry-vote 😉 toast flag (issue #299)
# ---------------------------------------------------------------------------

SELF_DRY_MSGID = "Odwaga. Szacunek."


@pytest.mark.django_db
def test_author_self_dry_vote_sets_toast_flag(client: Client) -> None:
    author = make_user("selfdry_author")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(author)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["self_dry_vote_toast"] == gettext(SELF_DRY_MSGID)


@pytest.mark.django_db
def test_author_self_dry_vote_toast_replays_on_toggle_back_on(
    client: Client,
) -> None:
    """It is a wink, not a one-shot — every fresh self dry-vote re-fires it."""
    author = make_user("selfdry_replay_author")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(author)
    on = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )
    assert on.json()["self_dry_vote_toast"] == gettext(SELF_DRY_MSGID)

    off = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )
    assert off.json()["self_dry_vote_toast"] is None
    assert not Vote.objects.filter(user=author, suchar=suchar).exists()

    again = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )
    assert again.json()["self_dry_vote_toast"] == gettext(SELF_DRY_MSGID)


@pytest.mark.django_db
def test_author_self_dry_vote_after_funny_still_sets_toast(client: Client) -> None:
    """`Vote` allows `is_funny` and `is_dry` at once — an existing self funny
    vote must not swallow the wink when the author then adds a dry vote."""
    author = make_user("selfdry_afterfunny_author")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=author, is_funny=True)

    client.force_login(author)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["self_dry_vote_toast"] == gettext(SELF_DRY_MSGID)
    assert data["user_is_funny"] is True
    assert data["user_is_dry"] is True


@pytest.mark.django_db
def test_author_self_funny_vote_has_no_self_dry_vote_toast(client: Client) -> None:
    author = make_user("selffunny_author")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(author)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "funny"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["self_dry_vote_toast"] is None


@pytest.mark.django_db
def test_author_removing_self_dry_vote_has_no_toast(client: Client) -> None:
    author = make_user("selfdry_remove_author")
    suchar = Suchar.objects.create(text="Joke", author=author)
    Vote.objects.create(suchar=suchar, user=author, is_dry=True)

    client.force_login(author)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["self_dry_vote_toast"] is None
    assert not Vote.objects.filter(user=author, suchar=suchar).exists()


@pytest.mark.django_db
def test_non_author_dry_vote_has_no_self_dry_vote_toast(client: Client) -> None:
    author = make_user("selfdry_notauthor_author")
    voter = make_user("selfdry_notauthor_voter")
    suchar = Suchar.objects.create(text="Joke", author=author)

    client.force_login(voter)
    response = client.post(
        vote_url(suchar.pk),
        data=json.dumps({"vote_type": "dry"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["self_dry_vote_toast"] is None
