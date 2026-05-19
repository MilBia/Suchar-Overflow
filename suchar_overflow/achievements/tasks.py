from datetime import datetime
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar


def award_best_suchar(period: str) -> None:
    """Award the best-suchar achievement for the given period ('month' or 'year').

    Uses yesterday as the reference date so when called on the 1st of a new
    period the previous period is evaluated (same logic as the management command).
    """
    reference_date = timezone.now().date() - timedelta(days=1)

    if period == "month":
        start_date = reference_date.replace(day=1)
        next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = next_month
        achievement_slug_suffix = "month"
    elif period == "year":
        start_date = reference_date.replace(month=1, day=1)
        end_date = start_date.replace(year=start_date.year + 1)
        achievement_slug_suffix = "year"
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

    best_suchar = (
        Suchar.objects.filter(
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        )
        .annotate(vote_count=Count("votes"))
        .order_by("-vote_count")
        .first()
    )

    if not best_suchar:
        return

    winner = best_suchar.author
    slug = f"best-suchar-{achievement_slug_suffix}"

    try:
        achievement = Achievement.objects.get(slug=slug)
    except Achievement.DoesNotExist:
        return

    UserAchievement.objects.get_or_create(user=winner, achievement=achievement)
