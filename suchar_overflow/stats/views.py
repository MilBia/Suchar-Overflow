import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models import Q
from django.db.models.functions import TruncDay
from django.utils import timezone
from django.views.generic import TemplateView

from suchar_overflow.suchary.models import Suchar

User = get_user_model()


class LeaderboardView(TemplateView):
    template_name = "stats/leaderboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Top Authors
        # Subquery to get the text of the highest scored suchar for the author
        # Score is now number of funny votes

        # We need to compute score per suchar first to find the best one
        # This is tricky with subqueries on related managers.
        # Simpler approach for best_joke text: Get the suchar with most funny votes.

        # Note: OuterRef("pk") refers to the User.
        # We want to find the Suchar by this user that has the max funny votes.
        # It's hard to order by a count in a subquery without extensive raw SQL
        # or complex annotations in Django versions.
        # However, we can try to annotate the subquery.

        # Let's simplify: We just want total score for the user.
        # best_joke text is nice to have.

        # For top_authors:
        # total_score = Count of all funny votes on all their suchars

        # 1. Top Authors (Overall) - Sorted by Total Votes
        top_authors_overall = (
            User.objects.annotate(
                total_score=Count("suchary__votes"),
                funny_score=Count(
                    "suchary__votes",
                    filter=Q(suchary__votes__is_funny=True),
                ),
                dry_score=Count(
                    "suchary__votes",
                    filter=Q(suchary__votes__is_dry=True),
                ),
                suchar_count=Count("suchary", distinct=True),
            )
            .exclude(total_score=0)
            .order_by("-total_score")[:10]
        )

        # 2. Top Authors (Funny) - Sorted by Funny Score
        top_authors_funny = (
            User.objects.annotate(
                funny_score=Count(
                    "suchary__votes",
                    filter=Q(suchary__votes__is_funny=True),
                ),
                suchar_count=Count("suchary", distinct=True),
            )
            .exclude(funny_score=0)
            .order_by("-funny_score")[:10]
        )

        # 3. Top Authors (Dry) - Sorted by Dry Score
        top_authors_dry = (
            User.objects.annotate(
                dry_score=Count(
                    "suchary__votes",
                    filter=Q(suchary__votes__is_dry=True),
                ),
                suchar_count=Count("suchary", distinct=True),
            )
            .exclude(dry_score=0)
            .order_by("-dry_score")[:10]
        )

        # 4. Top Suchars (Overall)
        top_suchars_overall = (
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .annotate(
                score=Count("votes"),
                funny_count=Count("votes", filter=Q(votes__is_funny=True)),
                dry_count=Count("votes", filter=Q(votes__is_dry=True)),
            )
            .exclude(score=0)
            .order_by("-score")[:10]
        )

        # 5. Top Suchars (Funny)
        top_suchars_funny = (
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .annotate(
                funny_count=Count("votes", filter=Q(votes__is_funny=True)),
                score=Count("votes"),  # Needed for display consistency if used
            )
            .exclude(funny_count=0)
            .order_by("-funny_count")[:10]
        )

        # 6. Top Suchars (Dry)
        top_suchars_dry = (
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .annotate(
                dry_count=Count("votes", filter=Q(votes__is_dry=True)),
                score=Count("votes"),
            )
            .exclude(dry_count=0)
            .order_by("-dry_count")[:10]
        )

        # Activity Chart Data (Last 30 days)
        last_30_days = timezone.now() - timedelta(days=30)
        activity_data = (
            Suchar.objects.filter(created_at__gte=last_30_days)
            .annotate(date=TruncDay("created_at"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        chart_labels = [entry["date"].strftime("%Y-%m-%d") for entry in activity_data]
        chart_values = [entry["count"] for entry in activity_data]

        context["top_authors_overall"] = top_authors_overall
        context["top_authors_funny"] = top_authors_funny
        context["top_authors_dry"] = top_authors_dry

        context["top_suchars_overall"] = top_suchars_overall
        context["top_suchars_funny"] = top_suchars_funny
        context["top_suchars_dry"] = top_suchars_dry

        context["chart_labels"] = json.dumps(chart_labels)
        context["chart_values"] = json.dumps(chart_values)

        return context
