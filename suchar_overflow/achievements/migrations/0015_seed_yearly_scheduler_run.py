from django.db import migrations
from django.utils import timezone

# Seeds a SchedulerRun marker for the new "award-best-suchar-year" job (#168)
# so the first automatic catch-up on deploy doesn't retroactively evaluate
# the previous complete year (award_periodic never wrote this marker, since
# it calls award_winners directly rather than award_best_suchar) — the first
# automatic yearly award instead lands at the next real cron fire.
JOB_ID = "award-best-suchar-year"


def seed_scheduler_run(apps, schema_editor):
    SchedulerRun = apps.get_model("achievements", "SchedulerRun")
    SchedulerRun.objects.update_or_create(
        job_id=JOB_ID,
        defaults={"ran_at": timezone.now()},
    )


def remove_scheduler_run(apps, schema_editor):
    SchedulerRun = apps.get_model("achievements", "SchedulerRun")
    SchedulerRun.objects.filter(job_id=JOB_ID).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("achievements", "0014_best_suchar_tie_achievements_data"),
    ]

    operations = [
        migrations.RunPython(seed_scheduler_run, remove_scheduler_run),
    ]
