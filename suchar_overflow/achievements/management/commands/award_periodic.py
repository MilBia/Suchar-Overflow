from datetime import datetime
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from suchar_overflow.achievements.tasks import award_winners
from suchar_overflow.achievements.tasks import compute_period_range
from suchar_overflow.achievements.tasks import find_best_suchary


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

        best_suchary = find_best_suchary(start_dt, end_dt)

        if not best_suchary:
            self.stdout.write("No suchars found for this period.")
            return

        # vote_count comes from find_best_suchary's .annotate(vote_count=...) —
        # not a static attribute of Suchar, so django-stubs can't see it.
        vote_count = best_suchary[0].vote_count  # type: ignore[attr-defined]
        authors = sorted({s.author for s in best_suchary}, key=lambda u: u.username)

        if len(authors) > 1:
            usernames = ", ".join(author.username for author in authors)
            self.stdout.write(
                f"Tie detected: {len(authors)} authors tied with "
                f"{vote_count} votes: {usernames}.",
            )
        else:
            self.stdout.write(
                f"Best Suchar found: '{best_suchary[0].text[:20]}...' "
                f"by {authors[0].username} with {vote_count} votes.",
            )

        # Slug convention: best-suchar-[period] e.g. best-suchar-month,
        # plus best-suchar-[period]-tie when the winners are tied.
        results = award_winners(best_suchary, achievement_slug_suffix)

        if not results:
            self.stdout.write(
                self.style.ERROR(
                    f"Achievement with slug 'best-suchar-{achievement_slug_suffix}' "
                    "not found!",
                ),
            )
            return

        for slug, user, created in results:
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Awarded '{slug}' to {user.username}"),
                )
            else:
                self.stdout.write(f"{user.username} already has '{slug}'.")
