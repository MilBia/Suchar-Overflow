import datetime

import pytest
from django.utils import timezone

from suchar_overflow.achievements.models import Achievement


@pytest.fixture
def periodic_achievements(db: None) -> None:  # noqa: ARG001
    Achievement.objects.get_or_create(
        slug="best-suchar-month",
        defaults={
            "name": "Comedian of the Month",
            "category": "PERIODIC",
            "metric": "SUM_SCORE",
            "threshold": 0,
            "icon_content": "<svg></svg>",
        },
    )
    Achievement.objects.get_or_create(
        slug="best-suchar-year",
        defaults={
            "name": "Legend of the Year",
            "category": "PERIODIC",
            "metric": "SUM_SCORE",
            "threshold": 0,
            "icon_content": "<svg></svg>",
        },
    )
    Achievement.objects.get_or_create(
        slug="best-suchar-month-tie",
        defaults={
            "name": "Tie of the Month",
            "category": "PERIODIC",
            "metric": "SUM_SCORE",
            "threshold": 0,
            "icon_content": "<svg></svg>",
            "is_secret": True,
        },
    )
    Achievement.objects.get_or_create(
        slug="best-suchar-year-tie",
        defaults={
            "name": "Tie of the Year",
            "category": "PERIODIC",
            "metric": "SUM_SCORE",
            "threshold": 0,
            "icon_content": "<svg></svg>",
            "is_secret": True,
        },
    )


def last_month_mid() -> datetime.datetime:
    """Return a timezone-aware datetime in the middle of the previous calendar month."""
    today = timezone.now().date()
    first_of_this_month = today.replace(day=1)
    last_month = first_of_this_month - datetime.timedelta(days=1)
    mid = last_month.replace(day=min(15, last_month.day))
    return timezone.make_aware(
        datetime.datetime(mid.year, mid.month, mid.day, 12, 0, 0),  # noqa: DTZ001
    )


def last_month_end() -> str:
    """Return a YYYY-MM-DD string for the last day of the previous calendar month."""
    today = timezone.now().date()
    first_of_this_month = today.replace(day=1)
    last_day = first_of_this_month - datetime.timedelta(days=1)
    return last_day.strftime("%Y-%m-%d")


def last_year_mid() -> datetime.datetime:
    """Return a timezone-aware datetime in the middle of the previous calendar year."""
    last_year = timezone.now().year - 1
    return timezone.make_aware(datetime.datetime(last_year, 6, 15, 12, 0, 0))  # noqa: DTZ001


def last_year_end() -> str:
    """Return the last day of the previous calendar year as YYYY-MM-DD."""
    last_year = timezone.now().year - 1
    return f"{last_year}-12-31"


def freeze_to_first_of_current_month() -> datetime.datetime:
    """Return a datetime pinned to the 1st of the current month (noon UTC).

    When the task uses ``timezone.now() - timedelta(days=1)``, yesterday falls
    in the previous month — which is what the monthly scheduler triggers on.
    """
    today = timezone.now().date()
    first = today.replace(day=1)
    return timezone.make_aware(
        datetime.datetime(first.year, first.month, first.day, 12, 0, 0),  # noqa: DTZ001
    )
