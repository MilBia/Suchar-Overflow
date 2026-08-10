from datetime import timedelta

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models import Min
from django.db.models import Q
from django.db.models.functions import TruncDay
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from suchar_overflow.suchary.models import Suchar

User = get_user_model()


def get_daily_activity_data(start_of_today, now, days):
    start_date = (start_of_today - timedelta(days=days)).date()
    end_date = now.date()
    db_data = (
        Suchar.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        .annotate(date=TruncDay("created_at"))
        .values("date")
        .annotate(count=Count("id"))
    )
    counts_map = {}
    for entry in db_data:
        d = entry["date"].date() if hasattr(entry["date"], "date") else entry["date"]
        counts_map[d] = entry["count"]

    labels = []
    values = []
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


def get_all_time_activity_data(start_of_today, now):
    earliest = Suchar.objects.aggregate(min_date=Min("created_at"))
    min_date = earliest.get("min_date")
    twelve_months_ago = (start_of_today - timedelta(days=365)).date().replace(day=1)
    if min_date:
        start_date = min(min_date.date().replace(day=1), twelve_months_ago)
    else:
        start_date = twelve_months_ago
    end_date = now.date().replace(day=1)

    db_data = (
        Suchar.objects.annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(count=Count("id"))
    )
    counts_map = {}
    for entry in db_data:
        m = entry["month"].date() if hasattr(entry["month"], "date") else entry["month"]
        m_start = m.replace(day=1)
        counts_map[m_start] = entry["count"]

    labels = []
    values = []
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


def _top_n(queryset, annotate_kwargs, order_field, limit=10):
    """Annotate, drop zero scores, and return the top `limit` by `order_field` desc."""
    return list(
        queryset.annotate(**annotate_kwargs)
        .exclude(**{order_field: 0})
        .order_by(f"-{order_field}")[:limit],
    )


class LeaderboardView(View):
    template_name = "stats/leaderboard.html"

    async def get(self, request, *args, **kwargs):
        context = await sync_to_async(self._build_context)()
        return await sync_to_async(render)(request, self.template_name, context)

    def _build_context(self):
        now = timezone.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        suchary = Suchar.objects.select_related("author").prefetch_related("tags")

        # Each tab's card only ever renders the fields it annotates here — the
        # "overall" card is the only one showing a funny/dry breakdown
        # alongside its primary metric, so only its queryset needs all three.
        suchar_count = Count("suchary", distinct=True)
        total_score = Count("suchary__votes")
        funny_score = Count("suchary__votes", filter=Q(suchary__votes__is_funny=True))
        dry_score = Count("suchary__votes", filter=Q(suchary__votes__is_dry=True))

        top_authors_overall = _top_n(
            User.objects,
            {
                "total_score": total_score,
                "funny_score": funny_score,
                "dry_score": dry_score,
                "suchar_count": suchar_count,
            },
            "total_score",
        )
        top_authors_funny = _top_n(
            User.objects,
            {"funny_score": funny_score, "suchar_count": suchar_count},
            "funny_score",
        )
        top_authors_dry = _top_n(
            User.objects,
            {"dry_score": dry_score, "suchar_count": suchar_count},
            "dry_score",
        )

        score = Count("votes")
        funny_count = Count("votes", filter=Q(votes__is_funny=True))
        dry_count = Count("votes", filter=Q(votes__is_dry=True))

        top_suchars_overall = _top_n(
            suchary,
            {"score": score, "funny_count": funny_count, "dry_count": dry_count},
            "score",
        )
        top_suchars_funny = _top_n(suchary, {"funny_count": funny_count}, "funny_count")
        top_suchars_dry = _top_n(suchary, {"dry_count": dry_count}, "dry_count")

        chart_datasets = {
            "7": get_daily_activity_data(start_of_today, now, 7),
            "30": get_daily_activity_data(start_of_today, now, 30),
            "90": get_daily_activity_data(start_of_today, now, 90),
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
