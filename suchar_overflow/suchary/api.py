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

from suchar_overflow.users.models import User

from .models import Suchar
from .models import Tag
from .models import Vote

router = Router()


class VoteSchema(Schema):
    vote_type: Literal["funny", "dry"]


class VoteResponse(Schema):
    funny_count: int
    dry_count: int
    user_is_funny: bool
    user_is_dry: bool


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

    vote, _ = Vote.objects.get_or_create(
        user=user,
        suchar=suchar,
    )

    if vote_type == "funny":
        vote.is_funny = not vote.is_funny
    elif vote_type == "dry":
        vote.is_dry = not vote.is_dry

    if not vote.is_funny and not vote.is_dry:
        vote.delete()
    else:
        vote.save()

    # Calculate counts using aggregation
    counts = suchar.votes.aggregate(
        funny=Count("pk", filter=Q(is_funny=True)),
        dry=Count("pk", filter=Q(is_dry=True)),
    )

    return {
        "funny_count": counts["funny"] or 0,
        "dry_count": counts["dry"] or 0,
        "user_is_funny": vote.is_funny
        if vote.pk
        # If deleted, object still has state but pk might be irrelevant
        else False,
        "user_is_dry": vote.is_dry if vote.pk else False,
    }
