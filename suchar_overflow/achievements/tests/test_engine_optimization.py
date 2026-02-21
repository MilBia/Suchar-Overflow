import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from suchar_overflow.achievements.engine import AchievementEngine
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.achievements.tasks import award_periodic_achievements_task
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()


@pytest.mark.django_db
class TestAchievementEngineOptimizations:
    def test_sum_score_n_plus_1_queries(self):
        # Create User
        user = User.objects.create_user(
            username="testuser",
            email="1@a.com",
            password="123",  # noqa: S106
        )
        other_user = User.objects.create_user(
            username="otheruser",
            email="2@a.com",
            password="123",  # noqa: S106
        )

        # Create achievement checking metric SUM_SCORE
        Achievement.objects.create(
            name="Score 10",
            slug="score-10",
            description="Got exactly sum score 10",
            icon_content="",
            category=Achievement.Category.LIFETIME,
            event_type=Achievement.EventType.VOTE_RECEIVED,
            metric=Achievement.Metric.SUM_SCORE,
            threshold=10,
        )

        # Create many suchars and votes to trigger N+1 if present
        for i in range(20):
            s = Suchar.objects.create(text=f"Suchar {i}", author=user)
            Vote.objects.create(
                suchar=s,
                user=other_user,
                is_funny=True,
            )  # this gives +1 score

        with CaptureQueriesContext(connection) as ctx:
            AchievementEngine.check_achievements(
                user,
                Achievement.EventType.VOTE_RECEIVED,
            )

        max_queries = 15
        assert len(ctx.captured_queries) < max_queries, (
            f"Zbyt wiele zapytań ({len(ctx.captured_queries)}), N+1 wciąż występuje!"
        )
        assert UserAchievement.objects.filter(
            user=user,
            achievement__metric=Achievement.Metric.SUM_SCORE,
        ).exists()

    def test_periodic_task(self):
        user1 = User.objects.create_user(
            username="u1",
            email="u1@a.com",
            password="123",  # noqa: S106
        )
        user2 = User.objects.create_user(
            username="u2",
            email="u2@a.com",
            password="123",  # noqa: S106
        )

        Achievement.objects.create(
            name="Comedian of Month",
            slug="comedian-month",
            description="Best score",
            icon_content="",
            category=Achievement.Category.PERIODIC,
            event_type=Achievement.EventType.SUCHAR_POSTED,
            metric=Achievement.Metric.SUM_SCORE,
            threshold=0,
        )

        # u1 gets 5 votes, u2 gets 1 vote
        s1 = Suchar.objects.create(text="U1s", author=user1)
        s2 = Suchar.objects.create(text="U2s", author=user2)

        for i in range(5):
            u_voter = User.objects.create_user(
                username=f"v{i}",
                email=f"v{i}@a.com",
                password="123",  # noqa: S106
            )
            Vote.objects.create(suchar=s1, user=u_voter, is_funny=True)
            if i == 0:
                Vote.objects.create(suchar=s2, user=u_voter, is_funny=True)

        # Run Celery task
        award_periodic_achievements_task()

        assert UserAchievement.objects.filter(
            user=user1,
            achievement__slug="comedian-month",
        ).exists()
        assert not UserAchievement.objects.filter(
            user=user2,
            achievement__slug="comedian-month",
        ).exists()
