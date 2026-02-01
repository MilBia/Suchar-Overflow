from typing import Literal

from django.db.models import Count
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja import Schema
from ninja.security import django_auth

from .models import Suchar
from .models import Vote

router = Router()


class VoteSchema(Schema):
    vote_type: Literal["funny", "dry"]


class VoteResponse(Schema):
    funny_count: int
    dry_count: int
    user_is_funny: bool
    user_is_dry: bool


@router.post("/{suchar_id}/vote", auth=django_auth, response=VoteResponse)
def vote_suchar(request, suchar_id: int, payload: VoteSchema):
    suchar = get_object_or_404(Suchar, pk=suchar_id)
    user = request.user
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
