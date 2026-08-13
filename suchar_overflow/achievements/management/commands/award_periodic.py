from datetime import datetime
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.achievements.tasks import compute_period_range
from suchar_overflow.achievements.tasks import find_best_suchar


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
            reference_date = datetime.fromisoformat(date_str).date()
        else:
            # Default to yesterday to capture the previous period.
            reference_date = timezone.now().date() - timedelta(days=1)

        self.stdout.write(
            f"Calculating best Suchar for {period} ending around {reference_date}...",
        )

        start_dt, end_dt, achievement_slug_suffix = compute_period_range(
            period,
            reference_date,
        )

        best_suchar = find_best_suchar(start_dt, end_dt)

        if not best_suchar:
            self.stdout.write("No suchars found for this period.")
            return

        winner = best_suchar.author
        # vote_count comes from find_best_suchar's .annotate(vote_count=...) —
        # not a static attribute of Suchar, so django-stubs can't see it.
        vote_count = best_suchar.vote_count  # type: ignore[attr-defined]
        self.stdout.write(
            f"Best Suchar found: '{best_suchar.text[:20]}...' "
            f"by {winner.username} with {vote_count} votes.",
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
