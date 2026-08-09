from datetime import date
from datetime import datetime
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar


def compute_period_range(
    period: str,
    reference_date: date,
) -> tuple[datetime, datetime, str]:
    """Compute the [start, end) datetime range and slug suffix for a period.

    ``period`` is ``"month"`` or ``"year"``; the range covers the calendar
    month/year that ``reference_date`` falls in.
    """
    if period == "month":
        start_date = reference_date.replace(day=1)
        end_date = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        suffix = "month"
    elif period == "year":
        start_date = reference_date.replace(month=1, day=1)
        end_date = start_date.replace(year=start_date.year + 1)
        suffix = "year"
    else:
        msg = f"Unknown period: {period!r}"
        raise ValueError(msg)

    current_tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        datetime.combine(start_date, datetime.min.time()),
        current_tz,
    )
    end_dt = timezone.make_aware(
        datetime.combine(end_date, datetime.min.time()),
        current_tz,
    )
    return start_dt, end_dt, suffix


def find_best_suchar(start_dt: datetime, end_dt: datetime) -> Suchar | None:
    """Return the Suchar with the most votes created within [start_dt, end_dt)."""
    return (
        Suchar.objects.filter(
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        )
        .annotate(vote_count=Count("votes"))
        .order_by("-vote_count")
        .first()
    )


def award_best_suchar(period: str) -> None:
    """Award the best-suchar achievement for the given period ('month' or 'year').

    Uses yesterday as the reference date so when called on the 1st of a new
    period the previous period is evaluated (same logic as the management command).
    """
    reference_date = timezone.now().date() - timedelta(days=1)
    start_dt, end_dt, suffix = compute_period_range(period, reference_date)

    best_suchar = find_best_suchar(start_dt, end_dt)
    if not best_suchar:
        return

    winner = best_suchar.author
    slug = f"best-suchar-{suffix}"

    try:
        achievement = Achievement.objects.get(slug=slug)
    except Achievement.DoesNotExist:
        return

    UserAchievement.objects.get_or_create(user=winner, achievement=achievement)
