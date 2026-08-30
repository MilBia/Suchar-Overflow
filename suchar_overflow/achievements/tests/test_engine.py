"""Tests for AchievementEngine rules and registration."""

import datetime
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from suchar_overflow.achievements import engine as eng
from suchar_overflow.achievements.engine import AchievementEngine
from suchar_overflow.achievements.engine import NightOwlRule
from suchar_overflow.achievements.engine import PolarizerRule
from suchar_overflow.achievements.engine import StreakLoginRule
from suchar_overflow.achievements.engine import VoteDryCountRule
from suchar_overflow.achievements.models import Achievement
from suchar_overflow.achievements.models import UserAchievement
from suchar_overflow.conftest import make_user
from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

if TYPE_CHECKING:
    from suchar_overflow.users.models import User


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


# ---------------------------------------------------------------------------
# AchievementEngine.register_rules — idempotency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_register_rules_idempotent() -> None:
    """Calling register_rules twice must not duplicate entries."""
    AchievementEngine._rules = {}  # noqa: SLF001
    AchievementEngine.register_rules()
    count_first = len(AchievementEngine._rules)  # noqa: SLF001
    AchievementEngine.register_rules()
    assert len(AchievementEngine._rules) == count_first  # noqa: SLF001


@pytest.mark.django_db
def test_register_rules_covers_all_subclasses() -> None:
    """Every AchievementRule subclass with a metric must appear in _rules."""
    AchievementEngine._rules = {}  # noqa: SLF001
    AchievementEngine.register_rules()
    for rule_cls in eng._all_subclasses(eng.AchievementRule):  # noqa: SLF001
        if rule_cls.metric:
            assert rule_cls.metric in AchievementEngine._rules  # noqa: SLF001


def test_register_rules_discovers_indirect_subclasses() -> None:
    """A rule nested under an intermediate base class must still be registered.

    ``register_rules`` walks the whole subclass tree, so grouping shared code
    in an abstract base (``metric = None``) doesn't orphan the concrete rules
    below it (#246). The classes are local so weakref-based ``__subclasses__()``
    drops them after GC; the sentinel metric is a plain string, not a real
    ``Achievement.Metric``, so it can't shadow a production rule even if it
    lingered. ``_rules`` is saved and restored regardless.
    """

    class _IntermediateBase(eng.AchievementRule):
        metric = None

    class _ConcreteIndirectRule(_IntermediateBase):
        metric = "test-indirect-metric"  # type: ignore[assignment]

        @classmethod
        def compute_value(
            cls,
            user: object,  # noqa: ARG003
            instance: object = None,  # noqa: ARG003
        ) -> int:
            return 0

    saved = AchievementEngine._rules  # noqa: SLF001
    AchievementEngine._rules = {}  # noqa: SLF001
    try:
        AchievementEngine.register_rules()
        assert (
            AchievementEngine._rules.get("test-indirect-metric")  # noqa: SLF001
            is _ConcreteIndirectRule
        )
    finally:
        AchievementEngine._rules = saved  # noqa: SLF001


def test_overriding_evaluate_on_a_rule_is_rejected() -> None:
    """The engine only calls compute_value(); an overridden evaluate() would be
    silently ignored, so defining one must fail at class-creation time."""
    with pytest.raises(TypeError, match="compute_value"):

        class BadRule(eng.AchievementRule):
            metric = Achievement.Metric.COUNT_SUCHAR

            @classmethod
            def evaluate(cls, *args: object, **kwargs: object) -> bool:  # noqa: ARG003
                return False


# ---------------------------------------------------------------------------
# AchievementEngine.check_achievements — PERIODIC excluded
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_periodic_achievement_never_auto_awarded() -> None:
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
def test_polarizer_rule_not_met_when_no_votes() -> None:
    user = make_user("u1")
    assert not PolarizerRule.evaluate(user, threshold=1)


@pytest.mark.django_db
def test_polarizer_rule_not_met_when_votes_unequal() -> None:
    user = make_user("u1")
    suchar = Suchar.objects.create(text="joke", author=user)
    voter1 = make_user("v1")
    voter2 = make_user("v2")
    Vote.objects.create(suchar=suchar, user=voter1, is_funny=True)
    Vote.objects.create(suchar=suchar, user=voter2, is_dry=True)
    # equal but count=1, threshold=2 → not met
    assert not PolarizerRule.evaluate(user, threshold=2)


@pytest.mark.django_db
def test_polarizer_rule_met_when_funny_equals_dry_at_threshold() -> None:
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
def test_polarizer_rule_engine_awards_achievement() -> None:
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
def test_streak_rule_false_when_no_suchary() -> None:
    user = make_user("u1")
    assert not StreakLoginRule.evaluate(user, threshold=2)


@pytest.mark.django_db
def test_streak_rule_false_when_single_day() -> None:
    user = make_user("u1")
    Suchar.objects.create(text="joke", author=user)
    assert not StreakLoginRule.evaluate(user, threshold=2)


@pytest.mark.django_db
def test_streak_rule_true_for_consecutive_days() -> None:
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
def test_streak_rule_false_when_gap_in_days() -> None:
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
def test_streak_rule_counts_only_longest_leading_streak() -> None:
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
def test_streak_rule_engine_awards_achievement() -> None:
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

# Helpers used across NightOwl tests: TIME_ZONE=UTC so UTC hour == local hour.


def _make_night_suchar(user: User, hour: int = 2) -> Suchar:
    """Create a Suchar at the given UTC hour (within 0-4 = night window)."""
    suchar = Suchar.objects.create(text=f"night joke h{hour}", author=user)
    ts = timezone.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    Suchar.objects.filter(pk=suchar.pk).update(created_at=ts)
    suchar.refresh_from_db()
    return suchar


def _make_day_suchar(user: User) -> Suchar:
    """Create a Suchar at 12:00 UTC (outside night window)."""
    suchar = Suchar.objects.create(text="day joke", author=user)
    ts = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
    Suchar.objects.filter(pk=suchar.pk).update(created_at=ts)
    suchar.refresh_from_db()
    return suchar


@pytest.mark.django_db
def test_night_owl_false_without_suchar_instance() -> None:
    user = make_user("u1")
    assert not NightOwlRule.evaluate(user, threshold=1, instance=None)


@pytest.mark.django_db
def test_night_owl_false_when_instance_is_wrong_type() -> None:
    user = make_user("u1")
    vote = Vote.__new__(Vote)  # not a Suchar
    assert not NightOwlRule.evaluate(user, threshold=1, instance=vote)


@pytest.mark.django_db
def test_night_owl_false_when_suchar_belongs_to_other_user() -> None:
    user = make_user("u1")
    other = make_user("u2")
    suchar = _make_night_suchar(other)
    assert not NightOwlRule.evaluate(user, threshold=1, instance=suchar)


@pytest.mark.django_db
def test_night_owl_false_when_suchar_is_daytime() -> None:
    """Daytime suchar must never satisfy Night Owl."""
    user = make_user("u1")
    suchar = _make_day_suchar(user)
    assert not NightOwlRule.evaluate(user, threshold=1, instance=suchar)


@pytest.mark.django_db
def test_night_owl_true_for_first_night_suchar_at_threshold_1() -> None:
    """First night suchar must satisfy Bronze (threshold=1)."""
    user = make_user("u1")
    suchar = _make_night_suchar(user)
    assert NightOwlRule.evaluate(user, threshold=1, instance=suchar)


@pytest.mark.django_db
def test_night_owl_false_when_threshold_not_yet_met() -> None:
    """One night suchar must NOT satisfy Silver threshold=2."""
    user = make_user("u1")
    suchar = _make_night_suchar(user)
    assert not NightOwlRule.evaluate(user, threshold=2, instance=suchar)


@pytest.mark.django_db
def test_night_owl_true_when_threshold_met_after_accumulation() -> None:
    """Two accumulated night suchary must satisfy threshold=2."""
    user = make_user("u1")
    _make_night_suchar(user, hour=1)
    suchar2 = _make_night_suchar(user, hour=2)
    assert NightOwlRule.evaluate(user, threshold=2, instance=suchar2)


@pytest.mark.django_db
def test_night_owl_daytime_suchary_do_not_count_toward_threshold() -> None:
    """Daytime suchary must not increment the night owl counter."""
    user = make_user("u1")
    _make_day_suchar(user)
    _make_day_suchar(user)
    suchar_night = _make_night_suchar(user)
    # 2 day + 1 night = only 1 night suchar → threshold 2 not met
    assert not NightOwlRule.evaluate(user, threshold=2, instance=suchar_night)


@pytest.mark.django_db
def test_night_owl_engine_awards_only_bronze_on_first_night_post() -> None:
    """With 1 night suchar, only Bronze (threshold=1) must be awarded;
    Silver (threshold=2) must NOT be awarded."""
    user = make_user("u1")
    bronze = make_achievement(
        "night-owl-bronze",
        Achievement.Metric.NIGHT_OWL,
        event_type=Achievement.EventType.SUCHAR_POSTED,
        threshold=1,
    )
    silver = make_achievement(
        "night-owl-silver",
        Achievement.Metric.NIGHT_OWL,
        event_type=Achievement.EventType.SUCHAR_POSTED,
        threshold=2,
    )
    suchar = _make_night_suchar(user)
    AchievementEngine.check_achievements(
        user,
        Achievement.EventType.SUCHAR_POSTED,
        instance=suchar,
    )
    assert UserAchievement.objects.filter(user=user, achievement=bronze).exists()
    assert not UserAchievement.objects.filter(user=user, achievement=silver).exists()


@pytest.mark.django_db
def test_night_owl_engine_awards_bronze_and_silver_after_two_night_posts() -> None:
    """After 2 night suchary both Bronze (threshold=1) and Silver (threshold=2)
    must be awarded."""
    user = make_user("u1")
    bronze = make_achievement(
        "night-owl-bronze",
        Achievement.Metric.NIGHT_OWL,
        event_type=Achievement.EventType.SUCHAR_POSTED,
        threshold=1,
    )
    silver = make_achievement(
        "night-owl-silver",
        Achievement.Metric.NIGHT_OWL,
        event_type=Achievement.EventType.SUCHAR_POSTED,
        threshold=2,
    )
    # First night post — awards only bronze
    s1 = _make_night_suchar(user, hour=1)
    AchievementEngine.check_achievements(
        user,
        Achievement.EventType.SUCHAR_POSTED,
        instance=s1,
    )
    # Second night post — now both bronze and silver conditions are met
    s2 = _make_night_suchar(user, hour=2)
    AchievementEngine.check_achievements(
        user,
        Achievement.EventType.SUCHAR_POSTED,
        instance=s2,
    )
    assert UserAchievement.objects.filter(user=user, achievement=bronze).exists()
    assert UserAchievement.objects.filter(user=user, achievement=silver).exists()


# ---------------------------------------------------------------------------
# VoteDryCountRule
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vote_dry_count_rule_false_when_no_votes_cast() -> None:
    user = make_user("u1")
    assert not VoteDryCountRule.evaluate(user, threshold=1)


@pytest.mark.django_db
def test_vote_dry_count_rule_true_when_user_casts_dry_vote() -> None:
    """Casting 1 dry vote must satisfy threshold=1."""
    voter = make_user("voter")
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_dry=True)
    assert VoteDryCountRule.evaluate(voter, threshold=1)


@pytest.mark.django_db
def test_vote_dry_count_rule_funny_vote_does_not_count() -> None:
    """Casting only funny votes must NOT satisfy the dry vote threshold."""
    voter = make_user("voter")
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_funny=True)
    assert not VoteDryCountRule.evaluate(voter, threshold=1)


@pytest.mark.django_db
def test_vote_dry_count_rule_receiving_dry_votes_does_not_count() -> None:
    """A user whose own suchary received dry votes must NOT earn the rule
    unless they themselves also cast dry votes."""
    author = make_user("author")
    voter = make_user("voter")
    suchar = Suchar.objects.create(text="joke", author=author)
    # author's suchar receives a dry vote — author should NOT earn the rule
    Vote.objects.create(suchar=suchar, user=voter, is_dry=True)
    assert not VoteDryCountRule.evaluate(author, threshold=1)


@pytest.mark.django_db
def test_vote_dry_count_rule_threshold_not_met() -> None:
    voter = make_user("voter")
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)
    Vote.objects.create(suchar=suchar, user=voter, is_dry=True)
    assert not VoteDryCountRule.evaluate(voter, threshold=2)


@pytest.mark.django_db
def test_vote_dry_count_engine_awards_achievement_to_voter() -> None:
    """Casting a dry vote must award a COUNT_VOTE_DRY achievement to the voter,
    not to the suchar author."""
    voter = make_user("voter")
    author = make_user("author")
    suchar = Suchar.objects.create(text="joke", author=author)
    ach = make_achievement(
        "grzybiarz-bronze",
        Achievement.Metric.COUNT_VOTE_DRY,
        event_type=Achievement.EventType.VOTE_CAST,
        threshold=1,
    )
    Vote.objects.create(suchar=suchar, user=voter, is_dry=True)
    assert UserAchievement.objects.filter(user=voter, achievement=ach).exists()
    assert not UserAchievement.objects.filter(user=author, achievement=ach).exists()


# ---------------------------------------------------------------------------
# check_achievements — already-owned achievements skipped
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_check_achievements_does_not_re_award() -> None:
    user = make_user("u1")
    ach = make_achievement("count-1", Achievement.Metric.COUNT_SUCHAR, threshold=1)
    UserAchievement.objects.create(user=user, achievement=ach)
    Suchar.objects.create(text="joke", author=user)
    assert UserAchievement.objects.filter(user=user, achievement=ach).count() == 1
