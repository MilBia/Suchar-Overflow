from copy import copy
from datetime import datetime
from datetime import time
from datetime import timedelta
from typing import TYPE_CHECKING
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Count
from django.db.models import Q
from django.db.models import prefetch_related_objects
from django.db.models.functions import TruncDay
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from suchar_overflow.suchary.models import Suchar

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from django.http import HttpRequest
    from django.http import HttpResponse

    from suchar_overflow.users.models import User as UserModel

User = get_user_model()

LEADERBOARD_CACHE_KEY = "leaderboard:context"
LEADERBOARD_CACHE_TTL = 60 * 5


def _fetch_daily_counts_map(start_date: date, end_date: date) -> dict[date, int]:
    # Raw datetime bounds (not created_at__date__gte/lte): the __date lookup
    # wraps the column in DATE(...), which can't use a plain B-tree index on
    # created_at. A half-open [start, end) range on the bare column can.
    range_start = timezone.make_aware(datetime.combine(start_date, time.min))
    range_end = timezone.make_aware(
        datetime.combine(end_date + timedelta(days=1), time.min),
    )
    db_data = (
        Suchar.objects.filter(
            created_at__gte=range_start,
            created_at__lt=range_end,
        )
        .annotate(date=TruncDay("created_at"))
        .values("date")
        .annotate(count=Count("id"))
    )
    counts_map: dict[date, int] = {}
    for entry in db_data:
        d = entry["date"].date() if hasattr(entry["date"], "date") else entry["date"]
        counts_map[d] = entry["count"]
    return counts_map


def get_daily_activity_data(
    start_of_today: datetime,
    now: datetime,
    days: int,
    counts_map: dict[date, int] | None = None,
) -> dict[str, list]:
    start_date = (start_of_today - timedelta(days=days)).date()
    end_date = now.date()
    if counts_map is None:
        counts_map = _fetch_daily_counts_map(start_date, end_date)

    labels: list[str] = []
    values: list[int] = []
    curr = start_date
    last_month = None
    last_year = None
    first = True

    while curr <= end_date:
        values.append(counts_map.get(curr, 0))
        day_str = str(curr.day)
        month_str = curr.strftime("%b")
        year_str = curr.strftime("%Y")

        if first:
            labels.append(f"{day_str} {month_str} {year_str}")
            first = False
        elif curr.year != last_year:
            labels.append(f"{day_str} {month_str} {year_str}")
        elif curr.month != last_month:
            labels.append(f"{day_str} {month_str}")
        else:
            labels.append(day_str)

        last_month = curr.month
        last_year = curr.year
        curr += timedelta(days=1)
    return {"labels": labels, "values": values}


def get_all_time_activity_data(
    start_of_today: datetime,
    now: datetime,
) -> dict[str, list]:
    db_data = (
        Suchar.objects.annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(count=Count("id"))
    )
    counts_map: dict[date, int] = {}
    for entry in db_data:
        m = entry["month"].date() if hasattr(entry["month"], "date") else entry["month"]
        m_start = m.replace(day=1)
        counts_map[m_start] = entry["count"]

    twelve_months_ago = (start_of_today - timedelta(days=365)).date().replace(day=1)
    start_date = min(counts_map, default=twelve_months_ago)
    start_date = min(start_date, twelve_months_ago)
    end_date = now.date().replace(day=1)

    labels: list[str] = []
    values: list[int] = []
    curr = start_date
    last_year = None
    first = True

    while curr <= end_date:
        values.append(counts_map.get(curr, 0))
        month_str = curr.strftime("%b")
        year_str = curr.strftime("%Y")

        if first:
            labels.append(f"{month_str} {year_str}")
            first = False
        elif curr.year != last_year:
            labels.append(f"{month_str} {year_str}")
        else:
            labels.append(month_str)

        last_year = curr.year
        december = 12
        if curr.month == december:
            curr = curr.replace(year=curr.year + 1, month=1)
        else:
            curr = curr.replace(month=curr.month + 1)
    return {"labels": labels, "values": values}


def _ranked_top_n(
    items: Sequence[Suchar | UserModel],
    order_field: str,
    limit: int = 10,
) -> list[Suchar | UserModel]:
    """Drop zero scores and return the top `limit` by `order_field` desc,
    each labeled with its dense rank (`.rank`, issue #229 — ties share a
    rank, the next distinct value follows with no gap).

    Sort ties break by ascending pk — deterministic regardless of the order
    the DB happened to return `items` in (which, without an explicit
    secondary ORDER BY, is not guaranteed stable across query plans). That
    tie-break only orders same-score items relative to each other — it does
    not affect their (shared) rank number.

    Returns shallow copies, not the original objects: `_build_context` ranks
    the same underlying `authors`/`all_suchary` list three times (once per
    metric), and each item's rank differs per metric, so mutating the
    originals in place would let the last call's ranks leak into the lists
    already returned by earlier calls.
    """
    filtered = [item for item in items if getattr(item, order_field) != 0]
    filtered.sort(key=lambda item: (-getattr(item, order_field), item.pk))
    top = filtered[:limit]

    ranked: list[Suchar | UserModel] = []
    rank = 0
    previous_value = None
    for item in top:
        value = getattr(item, order_field)
        if value != previous_value:
            rank += 1
            previous_value = value
        ranked_item = copy(item)
        ranked_item.rank = rank  # type: ignore[union-attr]
        ranked.append(ranked_item)
    return ranked


class LeaderboardView(View):
    template_name = "stats/leaderboard.html"

    async def get(self, request: HttpRequest) -> HttpResponse:
        context = await sync_to_async(self._get_cached_context)()
        return await sync_to_async(render)(request, self.template_name, context)

    def _get_cached_context(self) -> dict[str, Any]:
        context = cache.get_or_set(
            LEADERBOARD_CACHE_KEY,
            self._build_context,
            LEADERBOARD_CACHE_TTL,
        )
        # _build_context (the default factory passed above) never returns None.
        assert context is not None
        return context

    def _build_context(self) -> dict[str, Any]:
        now = timezone.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # select_related("author") only — no prefetch_related("tags") here.
        # Tags are prefetched further down, scoped to only the ~30 suchary
        # that actually end up rendered, not the whole materialized queryset.
        suchary = Suchar.objects.select_related("author")

        suchar_count = Count("suchary", distinct=True)
        total_score = Count("suchary__votes")
        funny_score = Count("suchary__votes", filter=Q(suchary__votes__is_funny=True))
        dry_score = Count("suchary__votes", filter=Q(suchary__votes__is_dry=True))

        # filter(suchary__isnull=False): a user with no suchary can never have a
        # nonzero total/funny/dry score, so exclude them before materializing —
        # otherwise a cache miss would pull every registered user into memory.
        # defer("password"): this queryset is cached whole (see LEADERBOARD_CACHE_KEY
        # below) — password hashes have no business sitting in the cache backend.
        authors = list(
            User.objects.filter(suchary__isnull=False)
            .defer("password")
            .annotate(
                total_score=total_score,
                funny_score=funny_score,
                dry_score=dry_score,
                suchar_count=suchar_count,
            ),
        )
        top_authors_overall = _ranked_top_n(authors, "total_score")
        top_authors_funny = _ranked_top_n(authors, "funny_score")
        top_authors_dry = _ranked_top_n(authors, "dry_score")

        score = Count("votes")
        funny_count = Count("votes", filter=Q(votes__is_funny=True))
        dry_count = Count("votes", filter=Q(votes__is_dry=True))

        # filter(votes__isnull=False): same reasoning as authors above — a
        # suchar with no votes can never have a nonzero score/funny/dry count.
        all_suchary = list(
            suchary.filter(votes__isnull=False).annotate(
                score=score,
                funny_count=funny_count,
                dry_count=dry_count,
            ),
        )
        top_suchars_overall = _ranked_top_n(all_suchary, "score")
        top_suchars_funny = _ranked_top_n(all_suchary, "funny_count")
        top_suchars_dry = _ranked_top_n(all_suchary, "dry_count")

        # Scoped prefetch: only the suchary that actually get rendered (the
        # union of the three top-10 lists). `_ranked_top_n` (#229) returns a
        # fresh shallow copy per call — so the same suchar can appear as a
        # *different* Python object in each of the three lists — no pk-based
        # dedup here: `prefetch_related_objects` fetches by pk once regardless
        # of duplicates, but assigns the cache only to the exact instances it
        # is given, so deduping by pk would silently starve the dropped
        # duplicates of their prefetch cache. The template must read tags via
        # `tags.all.0`, not `tags.first`: `.first()` clones the manager's
        # queryset via `order_by("pk")`, which drops this prefetch cache and
        # re-hits the DB every time.
        rendered_suchary = [*top_suchars_overall, *top_suchars_funny, *top_suchars_dry]
        prefetch_related_objects(rendered_suchary, "tags")

        widest_days = 90
        widest_start_date = (start_of_today - timedelta(days=widest_days)).date()
        counts_map = _fetch_daily_counts_map(widest_start_date, now.date())
        chart_datasets = {
            "7": get_daily_activity_data(start_of_today, now, 7, counts_map=counts_map),
            "30": get_daily_activity_data(
                start_of_today,
                now,
                30,
                counts_map=counts_map,
            ),
            "90": get_daily_activity_data(
                start_of_today,
                now,
                widest_days,
                counts_map=counts_map,
            ),
            "all": get_all_time_activity_data(start_of_today, now),
        }

        return {
            "top_authors_overall": top_authors_overall,
            "top_authors_funny": top_authors_funny,
            "top_authors_dry": top_authors_dry,
            "top_suchars_overall": top_suchars_overall,
            "top_suchars_funny": top_suchars_funny,
            "top_suchars_dry": top_suchars_dry,
            "chart_datasets": chart_datasets,
        }
