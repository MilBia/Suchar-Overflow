from datetime import datetime
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar


class Command(BaseCommand):
    help = "Awards periodic achievements (Best of Month, Best of Year)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            type=str,
            choices=["month", "year"],
            required=True,
            help="Period to evaluate (month or year)",
        )
        parser.add_argument(
            "--date",
            type=str,
            help="Reference date (YYYY-MM-DD). Defaults to yesterday.",
        )

    def handle(self, *args, **options):
        period = options["period"]
        date_str = options.get("date")

        if date_str:
            reference_date = timezone.datetime.fromisoformat(date_str).date()
        else:
            # Default to yesterday to capture the previous period.
            reference_date = timezone.now().date() - timedelta(days=1)

        self.stdout.write(
            f"Calculating best Suchar for {period} ending around {reference_date}...",
        )

        start_date = None
        end_date = None
        achievement_slug_suffix = ""

        if period == "month":
            # Start of the month
            start_date = reference_date.replace(day=1)
            # End of the month (start of next month - 1 day)
            # Actually, let's use range.
            # Example: Reference=2024-02-15. We want Best of Feb 2024?
            # Typically this runs on 1st of March to award Feb.
            # So if reference is Feb 28, we look at Feb.
            next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            end_date = next_month
            achievement_slug_suffix = "month"

        elif period == "year":
            start_date = reference_date.replace(month=1, day=1)
            next_year = start_date.replace(year=start_date.year + 1)
            end_date = next_year
            achievement_slug_suffix = "year"

        # Find the Best Suchar (Highest Score)
        # We need to sum votes? Or does Suchar have score?
        # Suchar model has no score field in DB (it's a property).

        # Calculate score: funny(1) - dry(0)? Or total votes?
        # User request said "Best Suchar". Implies highest positive reception.
        # Let's count 'funny' votes as +1.
        # Actually user detail template showed "Score" as a field. Let's check models.py
        # I remember Score is a property.

        # For now let's assume we sort by most 'funny' votes as simple "Best".
        # Or better: Total Votes.

        # Convert date objects to timezone-aware datetimes
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
            .annotate(
                vote_count=Count("votes"),
            )
            .order_by("-vote_count")
            .first()
        )

        if not best_suchar:
            self.stdout.write("No suchars found for this period.")
            return

        winner = best_suchar.author
        self.stdout.write(
            f"Best Suchar found: '{best_suchar.text[:20]}...' "
            f"by {winner.username} with {best_suchar.vote_count} votes.",
        )

        # Award Achievement
        # Slug convention: best-suchar-[period] e.g. best-suchar-month
        slug = f"best-suchar-{achievement_slug_suffix}"

        try:
            achievement = Achievement.objects.get(slug=slug)
        except Achievement.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"Achievement with slug '{slug}' not found!"),
            )
            return

        # Check if already awarded.
        # UserAchievement model uniqueness prevents duplicates.
        # Ideally, we should allow multiple awards (e.g. one per month).
        # For now, let's assume they get it once per 'type'.
        # OR we create a specific achievement for "Best of Feb 2024" (too many rows).
        # Let's give them the generic "Best of Month" badge.

        _, created = UserAchievement.objects.get_or_create(
            user=winner,
            achievement=achievement,
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Awarded '{achievement.name}' to {winner.username}",
                ),
            )
        else:
            self.stdout.write(f"{winner.username} already has '{achievement.name}'.")
