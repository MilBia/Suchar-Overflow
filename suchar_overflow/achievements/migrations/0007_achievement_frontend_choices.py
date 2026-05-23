from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0006_achievements_expansion_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="achievement",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("SUCHAR_POSTED", "Suchar Posted"),
                    ("VOTE_RECEIVED", "Vote Received"),
                    ("VOTE_CAST", "Vote Cast"),
                    ("FRONTEND", "Frontend"),
                ],
                default="SUCHAR_POSTED",
                max_length=20,
                verbose_name="Event Type",
            ),
        ),
        migrations.AlterField(
            model_name="achievement",
            name="metric",
            field=models.CharField(
                choices=[
                    ("COUNT_SUCHAR", "Suchar Count"),
                    ("COUNT_VOTE_FUNNY", "Funny Vote Count"),
                    ("COUNT_VOTE_DRY", "Dry Vote Count"),
                    ("COUNT_VOTE_CAST", "Vote Cast Count"),
                    ("SUM_SCORE", "Total Score"),
                    ("NIGHT_OWL", "Night Owl"),
                    ("STREAK_LOGIN", "Login Streak"),
                    ("POLARIZER", "Polarizer"),
                    ("FRONTEND_EVENT", "Frontend Event"),
                ],
                default="COUNT_SUCHAR",
                max_length=20,
                verbose_name="Metric",
            ),
        ),
    ]
