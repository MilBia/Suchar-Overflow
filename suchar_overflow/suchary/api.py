from typing import Literal

from django.db.models import Count

# django-ninja resolves endpoint parameter *and return* types via
# get_type_hints()/inspect.signature() at request-handling time, forcing
# eager resolution — same gotcha as View.as_view() in users/mixins.py; these
# imports must stay real, not TYPE_CHECKING-only.
from django.db.models import Q
from django.db.models import QuerySet
from django.http import HttpRequest  # noqa: TC002
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja import Schema
from ninja.security import django_auth

from suchar_overflow.achievements.cache import mark_suchar_toast_sent
from suchar_overflow.achievements.cache import set_pending_toast
from suchar_overflow.users.models import User

from .models import Suchar
from .models import Tag
from .models import Vote
from .signals import vote_changed

router = Router()


class VoteSchema(Schema):
    vote_type: Literal["funny", "dry"]


class VoteResponse(Schema):
    funny_count: int
    dry_count: int
    user_is_funny: bool
    user_is_dry: bool
    # Latched by the achievement engine (#294); lets the frontend drop the
    # craquelure overlay on the card in place, without a reload (#295).
    is_overdried: bool


class TagSchema(Schema):
    name: str
    slug: str


@router.get("/tags", response=list[TagSchema])
def list_tags(request: HttpRequest, q: str | None = None) -> QuerySet[Tag]:  # noqa: ARG001
    tags = Tag.objects.all()
    if q:
        tags = tags.filter(name__icontains=q)
    return tags[:10]


@router.post("/{suchar_id}/vote", auth=django_auth, response=VoteResponse)
def vote_suchar(
    request: HttpRequest,
    suchar_id: int,
    payload: VoteSchema,
) -> dict[str, int | bool]:
    # select_related("author"): the freshly created Vote carries this instance in
    # its fields_cache, so check_vote_achievements' `instance.suchar.author`
    # resolves without an extra query on every first-time vote.
    suchar = get_object_or_404(Suchar.objects.select_related("author"), pk=suchar_id)
    user = request.user
    assert isinstance(user, User)  # django_auth already rejects anonymous requests
    vote_type = payload.vote_type

    # defaults=: set the flag on the row *before* the INSERT so the
    # post_save(created=True) signal the achievement engine listens on sees
    # the final state. Flipping it in a follow-up save() (as the toggle path
    # below still does) fires no signal, so the first funny/dry vote used to
    # be counted one vote late (#247).
    vote, created = Vote.objects.get_or_create(
        user=user,
        suchar=suchar,
        defaults={
            "is_funny": vote_type == "funny",
            "is_dry": vote_type == "dry",
        },
    )

    if not created:
        if vote_type == "funny":
            vote.is_funny = not vote.is_funny
        elif vote_type == "dry":
            vote.is_dry = not vote.is_dry

        if not vote.is_funny and not vote.is_dry:
            vote.delete()
        else:
            vote.save()

        # A toggle on an existing row saves with created=False (or deletes
        # it), so no post_save(created=True) fires. Re-evaluate vote
        # achievements on the final state now — this also lets removing an
        # opposing vote award a threshold it newly crosses, e.g. deleting a
        # dry vote raises the author's SUM_SCORE (#247).
        vote_changed.send(
            sender=Vote,
            voter=user,
            author=suchar.author,
            suchar=suchar,
        )

    # Calculate counts using aggregation. `community_funny` deliberately
    # excludes the author's own vote — it drives the first-funny-vote toast
    # below and must not be satisfied by a self-vote. It is one extra
    # `COUNT(...) FILTER (...)` on the same row scan, not another query.
    counts = suchar.votes.aggregate(
        funny=Count("pk", filter=Q(is_funny=True)),
        dry=Count("pk", filter=Q(is_dry=True)),
        community_funny=Count(
            "pk",
            filter=Q(is_funny=True) & ~Q(user_id=suchar.author_id),
        ),
    )

    # First funny vote from someone *other than the author* → send the author a
    # lightweight 🥁 toast over the existing SSE stream (issue #292).
    # `added_funny` is true for both a brand-new funny vote and a toggle that
    # just switched `is_funny` on; `community_funny == 1` pins it to the 0 → 1
    # transition among non-author votes (so the author self-voting first no
    # longer eats it). `mark_suchar_toast_sent` (last, and only reached once
    # the rest already qualifies) latches it to once per suchar.
    added_funny = vote_type == "funny" and (created or vote.is_funny)
    if (
        added_funny
        and user.pk != suchar.author_id
        and counts["community_funny"] == 1
        and mark_suchar_toast_sent(suchar.pk)
    ):
        set_pending_toast(suchar.author_id)

    return {
        "funny_count": counts["funny"] or 0,
        "dry_count": counts["dry"] or 0,
        "user_is_funny": vote.is_funny
        if vote.pk
        # If deleted, object still has state but pk might be irrelevant
        else False,
        "user_is_dry": vote.is_dry if vote.pk else False,
        # The vote signals mutate this same `suchar` instance in place when
        # they latch it, so this reflects the post-vote state (#294).
        "is_overdried": suchar.is_overdried,
    }
