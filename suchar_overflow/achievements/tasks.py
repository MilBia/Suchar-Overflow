from datetime import timedelta

from celery import shared_task
from django.db.models import Count
from django.utils import timezone

from suchar_overflow.suchary.models import Suchar

from .models import Achievement
from .models import UserAchievement


@shared_task
def award_periodic_achievements_task():
    # Comedian of the month logic.
    # Get all PERIODIC achievements
    periodic_achievements = Achievement.objects.filter(
        category=Achievement.Category.PERIODIC,
    )

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    for achievement in periodic_achievements:
        if achievement.metric == Achievement.Metric.SUM_SCORE:
            # Monthly comedian -> best score in the last 30 days.
            # Identify the user with the most votes from suchars added last 30 days.
            authors_stats = (
                Suchar.objects.filter(created_at__gte=thirty_days_ago)
                .values("author")
                .annotate(
                    total_votes=Count("votes"),
                )
                .order_by("-total_votes")
            )

            if authors_stats:
                top_author_id = authors_stats[0]["author"]
                if top_author_id:
                    # Constraint unique_together guarantees 1 instance per user.
                    # As MVP: gets it once. Without unique_together: multiple times.
                    # We will stick to the models structure and grant it.
                    # Overriding get_or_create to grant the medal.
                    UserAchievement.objects.get_or_create(
                        user_id=top_author_id,
                        achievement=achievement,
                    )
