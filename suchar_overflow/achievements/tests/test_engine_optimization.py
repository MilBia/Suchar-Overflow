import datetime
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from suchar_overflow.achievements.engine import AchievementEngine
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

if TYPE_CHECKING:
    from suchar_overflow.users.models import User as UserType

User = get_user_model()


def make_achievement(
    slug: str,
    metric: Achievement.Metric,
    event_type: Achievement.EventType = Achievement.EventType.SUCHAR_POSTED,
    threshold: int = 1,
) -> Achievement:
    return Achievement.objects.create(
        slug=slug,
        name=slug,
        description="desc",
        icon_content="<svg/>",
        category=Achievement.Category.LIFETIME,
        event_type=event_type,
        metric=metric,
        threshold=threshold,
    )


def _capture_check(
    user: UserType,
    event_type: Achievement.EventType,
    instance: Suchar | Vote | None = None,
) -> list[dict[str, str]]:
    """Run check_achievements and return the queries it issued."""
    with CaptureQueriesContext(connection) as ctx:
        AchievementEngine.check_achievements(user, event_type, instance)
    return list(ctx.captured_queries)


@pytest.mark.django_db
class TestAchievementEngineOptimizations:
    def test_sum_score_n_plus_1_queries(self) -> None:
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


# ---------------------------------------------------------------------------
# Per-metric evaluation: one query per metric, not per candidate tier (#200)
# ---------------------------------------------------------------------------


def _select_queries(queries: list[dict[str, str]]) -> list[str]:
    return [q["sql"] for q in queries if q["sql"].lstrip().upper().startswith("SELECT")]


@pytest.mark.django_db
def test_query_count_independent_of_number_of_tiers() -> None:
    """Adding more unreachable tiers of the same metric must not add queries.

    Before #200 every candidate tier re-ran the metric's own ``.count()``, so
    the query count grew linearly with the number of unearned tiers.
    """
    user = make_user("tiers")
    Suchar.objects.create(text="joke", author=user)
    # Settle whatever the migration-seeded achievements award for this user, so
    # the two measurements below differ only by the extra candidate tiers.
    AchievementEngine.check_achievements(user, Achievement.EventType.SUCHAR_POSTED)

    # Thresholds far out of reach → no achievement is awarded, so the only
    # thing that can move the query count is the metric evaluation itself.
    for threshold in (100, 200, 300):
        make_achievement(
            f"suchar-tier-{threshold}",
            Achievement.Metric.COUNT_SUCHAR,
            threshold=threshold,
        )
    with_three_tiers = len(
        _capture_check(user, Achievement.EventType.SUCHAR_POSTED),
    )

    for threshold in (400, 500, 600):
        make_achievement(
            f"suchar-tier-{threshold}",
            Achievement.Metric.COUNT_SUCHAR,
            threshold=threshold,
        )
    with_six_tiers = len(_capture_check(user, Achievement.EventType.SUCHAR_POSTED))

    assert (
        UserAchievement.objects.filter(
            user=user,
            achievement__slug__startswith="suchar-tier-",
        ).count()
        == 0
    )
    assert with_six_tiers == with_three_tiers, (
        f"Query count grew with the number of tiers "
        f"({with_three_tiers} → {with_six_tiers}) — the metric is still "
        f"evaluated once per candidate."
    )


@pytest.mark.django_db
def test_metric_is_evaluated_once_per_metric_not_per_tier() -> None:
    """No SELECT is issued twice within a single check_achievements() call."""
    user = make_user("dupes")
    Suchar.objects.create(text="joke", author=user)
    AchievementEngine.check_achievements(user, Achievement.EventType.SUCHAR_POSTED)

    for threshold in (100, 200, 300, 400):
        make_achievement(
            f"suchar-tier-{threshold}",
            Achievement.Metric.COUNT_SUCHAR,
            threshold=threshold,
        )
        make_achievement(
            f"streak-tier-{threshold}",
            Achievement.Metric.STREAK_LOGIN,
            threshold=threshold,
        )

    selects = _select_queries(
        _capture_check(user, Achievement.EventType.SUCHAR_POSTED),
    )
    duplicated = {sql for sql in selects if selects.count(sql) > 1}
    assert not duplicated, f"Repeated identical SELECT(s): {duplicated}"


# ---------------------------------------------------------------------------
# Behaviour parity: same achievements awarded as a per-candidate evaluation
# ---------------------------------------------------------------------------


def _expected_awards(
    user: UserType,
    event_type: Achievement.EventType,
    instance: Suchar | Vote | None = None,
) -> set[str]:
    """Reference implementation: evaluate every candidate on its own.

    This mirrors the pre-#200 engine loop (one ``evaluate()`` call per
    candidate achievement) and is used to prove the grouped-by-metric engine
    awards exactly the same set.
    """
    AchievementEngine.register_rules()
    owned = UserAchievement.objects.filter(user=user).values_list(
        "achievement_id",
        flat=True,
    )
    candidates = (
        Achievement.objects.filter(event_type=event_type)
        .exclude(category=Achievement.Category.PERIODIC)
        .exclude(id__in=owned)
    )
    expected = set()
    for achievement in candidates:
        rule_cls = AchievementEngine._rules.get(achievement.metric)  # noqa: SLF001
        if rule_cls and rule_cls.evaluate(user, achievement.threshold, instance):
            expected.add(achievement.slug)
    return expected


def _build_multi_metric_scenario() -> tuple[UserType, Suchar]:
    """A user sitting mid-way through several tiered series at once."""
    user = make_user("multi")
    now = timezone.now()

    # Suchary on 3 consecutive days, two of them inside the night window.
    for offset, hour in ((2, 12), (1, 1), (0, 2), (0, 13)):
        suchar = Suchar.objects.create(text=f"joke {offset}-{hour}", author=user)
        Suchar.objects.filter(pk=suchar.pk).update(
            created_at=(now - datetime.timedelta(days=offset)).replace(
                hour=hour,
                minute=0,
                second=0,
                microsecond=0,
            ),
        )
    suchary = list(Suchar.objects.filter(author=user).order_by("created_at"))
    night_suchar = suchary[-2]
    night_suchar.refresh_from_db()

    # Votes received: 2 funny + 2 dry on one suchar (POLARIZER at 2),
    # plus extra funny votes elsewhere (SUM_SCORE).
    polarized = suchary[0]
    for i in range(2):
        Vote.objects.create(suchar=polarized, user=make_user(f"pf{i}"), is_funny=True)
        Vote.objects.create(suchar=polarized, user=make_user(f"pd{i}"), is_dry=True)
    for i in range(3):
        Vote.objects.create(suchar=suchary[1], user=make_user(f"f{i}"), is_funny=True)

    # Votes cast by the user: 2 funny + 1 dry.
    other = make_user("other")
    for i in range(3):
        foreign = Suchar.objects.create(text=f"other {i}", author=other)
        Vote.objects.create(
            suchar=foreign,
            user=user,
            is_funny=i < 2,  # noqa: PLR2004
            is_dry=i >= 2,  # noqa: PLR2004
        )

    # Tiered series straddling what the user has actually reached.
    tiers = {
        Achievement.Metric.COUNT_SUCHAR: (1, 2, 4, 5, 10),
        Achievement.Metric.NIGHT_OWL: (1, 2, 3),
        Achievement.Metric.STREAK_LOGIN: (2, 3, 4),
        Achievement.Metric.SUM_SCORE: (1, 3, 5, 20),
        Achievement.Metric.POLARIZER: (1, 2, 5),
        Achievement.Metric.COUNT_VOTE_FUNNY: (1, 2, 5),
        Achievement.Metric.COUNT_VOTE_DRY: (1, 2),
        Achievement.Metric.COUNT_VOTE_CAST: (1, 3, 5),
    }
    events = {
        Achievement.Metric.SUM_SCORE: Achievement.EventType.VOTE_RECEIVED,
        Achievement.Metric.POLARIZER: Achievement.EventType.VOTE_RECEIVED,
        Achievement.Metric.COUNT_VOTE_FUNNY: Achievement.EventType.VOTE_CAST,
        Achievement.Metric.COUNT_VOTE_DRY: Achievement.EventType.VOTE_CAST,
        Achievement.Metric.COUNT_VOTE_CAST: Achievement.EventType.VOTE_CAST,
    }
    for metric, thresholds in tiers.items():
        for threshold in thresholds:
            make_achievement(
                f"{metric.lower()}-{threshold}",
                metric,
                event_type=events.get(metric, Achievement.EventType.SUCHAR_POSTED),
                threshold=threshold,
            )
    # Wipe what the signals awarded while the scenario was being built, so the
    # explicit engine calls below see every tier as a fresh candidate.
    UserAchievement.objects.filter(user=user).delete()
    return user, night_suchar


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("event_type", "with_instance"),
    [
        (Achievement.EventType.SUCHAR_POSTED, True),
        (Achievement.EventType.SUCHAR_POSTED, False),
        (Achievement.EventType.VOTE_RECEIVED, False),
        (Achievement.EventType.VOTE_CAST, False),
    ],
)
def test_awarded_set_matches_per_candidate_evaluation(
    event_type: Achievement.EventType,
    with_instance: bool,  # noqa: FBT001
) -> None:
    """The grouped engine awards exactly what per-candidate evaluation would.

    Achievement has no Meta.ordering, so the order in which candidates come
    back from the DB is undefined both before and after #200 — the guarantee
    that matters (and that this asserts) is the awarded *set*.
    """
    user, night_suchar = _build_multi_metric_scenario()
    instance = night_suchar if with_instance else None

    expected = _expected_awards(user, event_type, instance)
    assert expected, "scenario should award something for this event type"

    AchievementEngine.check_achievements(user, event_type, instance)

    awarded = set(
        UserAchievement.objects.filter(user=user).values_list(
            "achievement__slug",
            flat=True,
        ),
    )
    assert awarded == expected


@pytest.mark.django_db
def test_repeated_calls_pick_up_new_data() -> None:
    """The per-metric memo must not leak between check_achievements() calls."""
    user = make_user("memo")
    bronze = make_achievement("memo-1", Achievement.Metric.COUNT_SUCHAR, threshold=1)
    silver = make_achievement("memo-2", Achievement.Metric.COUNT_SUCHAR, threshold=2)

    Suchar.objects.create(text="one", author=user)
    AchievementEngine.check_achievements(user, Achievement.EventType.SUCHAR_POSTED)
    assert UserAchievement.objects.filter(user=user, achievement=bronze).exists()
    assert not UserAchievement.objects.filter(user=user, achievement=silver).exists()

    Suchar.objects.create(text="two", author=user)
    AchievementEngine.check_achievements(user, Achievement.EventType.SUCHAR_POSTED)
    assert UserAchievement.objects.filter(user=user, achievement=silver).exists()


@pytest.mark.django_db
def test_metric_without_rule_is_skipped() -> None:
    """FRONTEND_EVENT has no engine rule — it must never be auto-awarded."""
    user = make_user("norule")
    ach = make_achievement(
        "frontend-only",
        Achievement.Metric.FRONTEND_EVENT,
        event_type=Achievement.EventType.SUCHAR_POSTED,
        threshold=1,
    )
    Suchar.objects.create(text="joke", author=user)
    AchievementEngine.check_achievements(user, Achievement.EventType.SUCHAR_POSTED)
    assert not UserAchievement.objects.filter(user=user, achievement=ach).exists()
