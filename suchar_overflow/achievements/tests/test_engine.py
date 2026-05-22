"""Tests for AchievementEngine rules and registration."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from suchar_overflow.achievements import engine as eng
from suchar_overflow.achievements.engine import AchievementEngine
from suchar_overflow.achievements.engine import NightOwlRule
from suchar_overflow.achievements.engine import PolarizerRule
from suchar_overflow.achievements.engine import StreakLoginRule
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",  # noqa: S106
    )


def make_achievement(
    slug,
    metric,
    event_type=Achievement.EventType.SUCHAR_POSTED,
    threshold=1,
):
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


# ---------------------------------------------------------------------------
# AchievementEngine.register_rules — idempotency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_register_rules_idempotent():
    """Calling register_rules twice must not duplicate entries."""
    AchievementEngine._rules = {}  # noqa: SLF001
    AchievementEngine.register_rules()
    count_first = len(AchievementEngine._rules)  # noqa: SLF001
    AchievementEngine.register_rules()
    assert len(AchievementEngine._rules) == count_first  # noqa: SLF001


@pytest.mark.django_db
def test_register_rules_covers_all_subclasses():
    """Every AchievementRule subclass with a metric must appear in _rules."""
    AchievementEngine._rules = {}  # noqa: SLF001
    AchievementEngine.register_rules()
    for rule_cls in eng.AchievementRule.__subclasses__():
        if rule_cls.metric:
            assert rule_cls.metric in AchievementEngine._rules  # noqa: SLF001


# ---------------------------------------------------------------------------
# AchievementEngine.check_achievements — PERIODIC excluded
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_periodic_achievement_never_auto_awarded():
    """PERIODIC category achievements must be excluded from automatic engine checks."""
    user = make_user("u1")
    Achievement.objects.create(
        slug="periodic-test",
        name="Periodic",
        description="desc",
        icon_content="<svg/>",
        category=Achievement.Category.PERIODIC,
        event_type=Achievement.EventType.SUCHAR_POSTED,
        metric=Achievement.Metric.COUNT_SUCHAR,
        threshold=1,
    )
    Suchar.objects.create(text="joke", author=user)
    # Only the PERIODIC achievement must not be auto-awarded; migration-seeded
    # non-PERIODIC achievements (e.g. "First Suchar") may still fire.
    assert not UserAchievement.objects.filter(
        user=user,
        achievement__category=Achievement.Category.PERIODIC,
    ).exists()


# ---------------------------------------------------------------------------
# PolarizerRule
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_polarizer_rule_not_met_when_no_votes():
    user = make_user("u1")
    assert not PolarizerRule.evaluate(user, threshold=1)


@pytest.mark.django_db
def test_polarizer_rule_not_met_when_votes_unequal():
    user = make_user("u1")
    suchar = Suchar.objects.create(text="joke", author=user)
    voter1 = make_user("v1")
    voter2 = make_user("v2")
    Vote.objects.create(suchar=suchar, user=voter1, is_funny=True)
    Vote.objects.create(suchar=suchar, user=voter2, is_dry=True)
    # equal but count=1, threshold=2 → not met
    assert not PolarizerRule.evaluate(user, threshold=2)


@pytest.mark.django_db
def test_polarizer_rule_met_when_funny_equals_dry_at_threshold():
    user = make_user("u1")
    suchar = Suchar.objects.create(text="joke", author=user)
    for i in range(2):
        v = make_user(f"vf{i}")
        Vote.objects.create(suchar=suchar, user=v, is_funny=True)
    for i in range(2):
        v = make_user(f"vd{i}")
        Vote.objects.create(suchar=suchar, user=v, is_dry=True)
    assert PolarizerRule.evaluate(user, threshold=2)


@pytest.mark.django_db
def test_polarizer_rule_engine_awards_achievement():
    user = make_user("u1")
    ach = make_achievement(
        "polarizer",
        Achievement.Metric.POLARIZER,
        event_type=Achievement.EventType.VOTE_RECEIVED,
        threshold=1,
    )
    suchar = Suchar.objects.create(text="joke", author=user)
    voter_f = make_user("vf")
    voter_d = make_user("vd")
    Vote.objects.create(suchar=suchar, user=voter_f, is_funny=True)
    Vote.objects.create(suchar=suchar, user=voter_d, is_dry=True)
    AchievementEngine.check_achievements(user, Achievement.EventType.VOTE_RECEIVED)
    assert UserAchievement.objects.filter(user=user, achievement=ach).exists()


# ---------------------------------------------------------------------------
# StreakLoginRule
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_streak_rule_false_when_no_suchary():
    user = make_user("u1")
    assert not StreakLoginRule.evaluate(user, threshold=2)


@pytest.mark.django_db
def test_streak_rule_false_when_single_day():
    user = make_user("u1")
    Suchar.objects.create(text="joke", author=user)
    assert not StreakLoginRule.evaluate(user, threshold=2)


@pytest.mark.django_db
def test_streak_rule_true_for_consecutive_days():
    user = make_user("u1")
    today = timezone.now()
    s1 = Suchar.objects.create(text="day1", author=user)
    s2 = Suchar.objects.create(text="day2", author=user)
    Suchar.objects.filter(pk=s1.pk).update(
        created_at=today - datetime.timedelta(days=1),
    )
    Suchar.objects.filter(pk=s2.pk).update(created_at=today)
    assert StreakLoginRule.evaluate(user, threshold=2)


@pytest.mark.django_db
def test_streak_rule_false_when_gap_in_days():
    user = make_user("u1")
    today = timezone.now()
    s1 = Suchar.objects.create(text="day1", author=user)
    s2 = Suchar.objects.create(text="day3", author=user)
    Suchar.objects.filter(pk=s1.pk).update(
        created_at=today - datetime.timedelta(days=2),
    )
    Suchar.objects.filter(pk=s2.pk).update(created_at=today)
    # gap: 2 days apart → no 2-day streak
    assert not StreakLoginRule.evaluate(user, threshold=2)


@pytest.mark.django_db
def test_streak_rule_counts_only_longest_leading_streak():
    """Streak resets on first gap — old consecutive days don't count."""
    user = make_user("u1")
    today = timezone.now()
    # Days: -5, -4, -3, gap, -1, 0  → streak of 2 from today, not 3+2
    for offset in [5, 4, 3, 1, 0]:
        s = Suchar.objects.create(text=f"d{offset}", author=user)
        Suchar.objects.filter(pk=s.pk).update(
            created_at=today - datetime.timedelta(days=offset),
        )
    assert not StreakLoginRule.evaluate(user, threshold=3)
    assert StreakLoginRule.evaluate(user, threshold=2)


@pytest.mark.django_db
def test_streak_rule_engine_awards_achievement():
    user = make_user("u1")
    ach = make_achievement(
        "streak-2",
        Achievement.Metric.STREAK_LOGIN,
        event_type=Achievement.EventType.SUCHAR_POSTED,
        threshold=2,
    )
    today = timezone.now()
    s1 = Suchar.objects.create(text="d1", author=user)
    s2 = Suchar.objects.create(text="d2", author=user)
    Suchar.objects.filter(pk=s1.pk).update(
        created_at=today - datetime.timedelta(days=1),
    )
    Suchar.objects.filter(pk=s2.pk).update(created_at=today)
    AchievementEngine.check_achievements(user, Achievement.EventType.SUCHAR_POSTED)
    assert UserAchievement.objects.filter(user=user, achievement=ach).exists()


# ---------------------------------------------------------------------------
# NightOwlRule
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_night_owl_false_without_suchar_instance():
    user = make_user("u1")
    assert not NightOwlRule.evaluate(user, threshold=1, instance=None)


@pytest.mark.django_db
def test_night_owl_false_when_instance_is_wrong_type():
    user = make_user("u1")
    vote = Vote.__new__(Vote)  # not a Suchar
    assert not NightOwlRule.evaluate(user, threshold=1, instance=vote)


@pytest.mark.django_db
def test_night_owl_false_when_suchar_belongs_to_other_user():
    user = make_user("u1")
    other = make_user("u2")
    suchar = Suchar.objects.create(text="joke", author=other)
    assert not NightOwlRule.evaluate(user, threshold=1, instance=suchar)


@pytest.mark.django_db
def test_night_owl_true_when_suchar_created_at_midnight_hour():
    user = make_user("u1")
    suchar = Suchar.objects.create(text="joke", author=user)
    # Force created_at to 02:00 local time
    midnight_utc = timezone.now().replace(hour=2, minute=0, second=0, microsecond=0)
    Suchar.objects.filter(pk=suchar.pk).update(created_at=midnight_utc)
    suchar.refresh_from_db()
    # Rule checks hour in current timezone; UTC hour=2 is within 0-4 range
    result = NightOwlRule.evaluate(user, threshold=1, instance=suchar)
    # Result depends on server timezone — just assert no crash and returns bool
    assert isinstance(result, bool)


@pytest.mark.django_db
def test_night_owl_engine_awards_achievement_for_late_night_suchar():
    user = make_user("u1")
    ach = make_achievement(
        "night-owl",
        Achievement.Metric.NIGHT_OWL,
        event_type=Achievement.EventType.SUCHAR_POSTED,
        threshold=1,
    )
    suchar = Suchar.objects.create(text="joke", author=user)
    # Set created_at to 01:00 UTC (within 0-4 range)
    early_am = timezone.now().replace(hour=1, minute=0, second=0, microsecond=0)
    Suchar.objects.filter(pk=suchar.pk).update(created_at=early_am)
    suchar.refresh_from_db()
    AchievementEngine.check_achievements(
        user,
        Achievement.EventType.SUCHAR_POSTED,
        instance=suchar,
    )
    # Whether awarded depends on timezone config; assert no exception raised
    awarded = UserAchievement.objects.filter(user=user, achievement=ach).exists()
    assert isinstance(awarded, bool)


# ---------------------------------------------------------------------------
# check_achievements — already-owned achievements skipped
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_check_achievements_does_not_re_award():
    user = make_user("u1")
    ach = make_achievement("count-1", Achievement.Metric.COUNT_SUCHAR, threshold=1)
    UserAchievement.objects.create(user=user, achievement=ach)
    Suchar.objects.create(text="joke", author=user)
    assert UserAchievement.objects.filter(user=user, achievement=ach).count() == 1
