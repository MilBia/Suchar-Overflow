from typing import Literal

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja import Schema
from ninja.security import django_auth

from .models import Suchar
from .models import Vote

router = Router()


class VoteSchema(Schema):
    value: Literal[1, -1]


class VoteResponse(Schema):
    new_score: int
    user_vote: int  # 1, -1, or 0 (none)


@router.post("/{suchar_id}/vote", auth=django_auth, response=VoteResponse)
def vote_suchar(request, suchar_id: int, payload: VoteSchema):
    suchar = get_object_or_404(Suchar, pk=suchar_id)
    user = request.user
    value = payload.value

    vote, created = Vote.objects.get_or_create(
        user=user,
        suchar=suchar,
        defaults={"value": value},
    )

    current_vote = value

    if not created:
        if vote.value == value:
            # Toggle off
            vote.delete()
            current_vote = 0
        else:
            # Change vote
            vote.value = value
            vote.save()
            current_vote = value

    # Calculate score using aggregation
    new_score = suchar.votes.aggregate(total=Sum("value"))["total"] or 0

    return {"new_score": new_score, "user_vote": current_vote}
