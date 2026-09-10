from typing import Literal

from django.db.models import Count
from django.db.models import Exists
from django.db.models import OuterRef

# django-ninja resolves endpoint parameter *and return* types via
# get_type_hints()/inspect.signature() at request-handling time, forcing
# eager resolution — same gotcha as View.as_view() in users/mixins.py; these
# imports must stay real, not TYPE_CHECKING-only.
from django.db.models import Q
from django.db.models import QuerySet
from django.http import HttpRequest  # noqa: TC002
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
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
    # #299: set only when the author casts a "dry" vote on their *own* suchar
    # — voting.js winks back with a "Odwaga. Szacunek." toast. Translated here
    # so it lands in the voter's active language; the voter *is* the author,
    # so this request's language is theirs.
    self_dry_vote_toast: str | None = None


class TagSchema(Schema):
    name: str
    slug: str


@router.get("/tags", response=list[TagSchema])
def list_tags(request: HttpRequest, q: str | None = None) -> QuerySet[Tag]:  # noqa: ARG001
    # Only suggest tags that already appear on at least one *published* suchar.
    # A tag added to a scheduled (not-yet-published) suchar would otherwise
    # surface in the create-form autocomplete immediately, letting a stranger
    # infer someone is drafting on a topic before it goes live (#389). This
    # endpoint is anonymous-reachable, so the filter is the fix rather than an
    # auth gate. `Exists` avoids the join fan-out / `DISTINCT` a `.filter(
    # suchary__...)` would need (cf. #241, #196). `order_by("name")` keeps the
    # 10-row slice stable between calls now that a join is involved.
    published_suchary = Suchar.objects.filter(
        tags=OuterRef("pk"),
        published_at__lte=timezone.now(),
    )
    tags = Tag.objects.filter(Exists(published_suchary))
    if q:
        # suchar_form.js sends the raw term the user is typing, which can carry
        # a leading `#` (badges render as `#tag`), optionally with a space after
        # it; tag names are stored without either (see SucharForm._save_tags),
        # so normalise before matching.
        q = q.strip().lstrip("#").strip()
    if q:
        tags = tags.filter(name__icontains=q)
    return tags.order_by("name")[:10]


@router.post("/{suchar_id}/vote", auth=django_auth, response=VoteResponse)
def vote_suchar(
    request: HttpRequest,
    suchar_id: int,
    payload: VoteSchema,
) -> dict[str, int | bool | str | None]:
    # select_related("author"): the freshly created Vote carries this instance in
    # its fields_cache, so check_vote_achievements' `instance.suchar.author`
    # resolves without an extra query on every first-time vote.
    # published_at__lte filter (#331, same convention as SucharListView):
    # folded into the queryset passed to get_object_or_404 rather than
    # fetched-then-checked with a separate `raise Http404`, so a scheduled
    # suchar is genuinely indistinguishable from a missing one — both raise
    # the exact same Http404 from the exact same call, instead of a second,
    # differently-worded raise a guesser could tell apart under DEBUG=True.
    suchar = get_object_or_404(
        Suchar.objects.filter(published_at__lte=timezone.now()).select_related(
            "author",
        ),
        pk=suchar_id,
    )
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
    # just switched `is_funny` on. `community_funny >= 1` (was `== 1`) plus
    # `mark_suchar_toast_sent` — a single-winner `cache.add` latch — is what
    # makes this exactly-once: two non-authors funny-voting near-simultaneously
    # could both read `community_funny == 2` (their own INSERT + the other's)
    # and an `== 1` test would then fire for neither (#334). With `>= 1` both
    # qualify on the count and the atomic latch picks one. Trade-off: after a
    # Redis flush a suchar that already has funny votes can fire one late
    # toast; acceptable for a best-effort UI-delight cue, and cheaper than a
    # `select_for_update` lock on every vote.
    added_funny = vote_type == "funny" and (created or vote.is_funny)
    if (
        added_funny
        and user.pk != suchar.author_id
        and counts["community_funny"] >= 1
        and mark_suchar_toast_sent(suchar.pk)
    ):
        set_pending_toast(suchar.author_id)

    # #299: author dry-voting their own suchar earns a wink. `added_dry`
    # mirrors `added_funny` — true for a fresh dry vote and for a toggle that
    # just switched `is_dry` on, false on removal. It replays on every fresh
    # self dry-vote (no latch) — it is pure UI delight, no achievement.
    added_dry = vote_type == "dry" and (created or vote.is_dry)
    self_dry_vote_toast = (
        _("Odwaga. Szacunek.") if added_dry and user.pk == suchar.author_id else None
    )

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
        "self_dry_vote_toast": self_dry_vote_toast,
    }
