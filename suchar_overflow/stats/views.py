import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models import Sum
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

        best_suchar_subquery = (
            Suchar.objects.filter(author=OuterRef("pk"))
            .annotate(score=Sum("votes__value"))
            .order_by("-score")
            .values("text")[:1]
        )

        top_authors = (
            User.objects.annotate(
                total_score=Sum("suchary__votes__value"),
                suchar_count=Count("suchary"),
                best_joke=Subquery(best_suchar_subquery),
            )
            .exclude(total_score=None)
            .order_by("-total_score")[:10]
        )

        # Top Suchars
        top_suchars = (
            Suchar.objects.select_related("author")
            .prefetch_related("tags")
            .annotate(
                score=Sum("votes__value"),
            )
            .exclude(score=None)
            .order_by("-score")[:10]
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

        context["top_authors"] = top_authors
        context["top_suchars"] = top_suchars
        context["chart_labels"] = json.dumps(chart_labels)
        context["chart_values"] = json.dumps(chart_values)

        return context
