from typing import TYPE_CHECKING

from django.core.cache import cache
from django.db.models import Case
from django.db.models import Count
from django.db.models import F
from django.db.models import IntegerField
from django.db.models import Max
from django.db.models import Q
from django.db.models import Sum
from django.db.models import When
from django.db.models.functions import ExtractHour
from django.utils import timezone

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

from .models import Achievement
from .models import UserAchievement

if TYPE_CHECKING:
    from suchar_overflow.users.models import User


class AchievementRule:
    """Base class for metric rules.

    A rule computes a single, *threshold-independent* value for a user
    (:meth:`compute_value`); ``evaluate`` only compares that value against a
    threshold. Keeping the two apart lets ``check_achievements`` compute the
    value once per metric and reuse it for every candidate tier of that
    metric, instead of re-running the same query for each tier (see #200).

    ``compute_value`` returns ``None`` when the rule cannot be satisfied at
    all for this call (e.g. Night Owl without a qualifying suchar instance) —
    that is not the same as the value ``0``, which would still satisfy a
    ``threshold`` of ``0``.

    Subclasses must stay *direct* subclasses of this class:
    ``AchievementEngine.register_rules`` discovers them via
    ``__subclasses__()``, which only sees one level.
    """

    metric: Achievement.Metric | None = None

    @classmethod
    def compute_value(
        cls,
        user: User,
        instance: Suchar | Vote | None = None,
    ) -> int | None:
        raise NotImplementedError

    @classmethod
    def evaluate(
        cls,
        user: User,
        threshold: int,
        instance: Suchar | Vote | None = None,
    ) -> bool:
        value = cls.compute_value(user, instance)
        return value is not None and value >= threshold


class SucharCountRule(AchievementRule):
    metric = Achievement.Metric.COUNT_SUCHAR

    @classmethod
    def compute_value(
        cls,
        user: User,
        instance: Suchar | Vote | None = None,  # noqa: ARG003
    ) -> int | None:
        return user.suchary.count()


class VoteFunnyCountRule(AchievementRule):
    metric = Achievement.Metric.COUNT_VOTE_FUNNY

    @classmethod
    def compute_value(
        cls,
        user: User,
        instance: Suchar | Vote | None = None,  # noqa: ARG003
    ) -> int | None:
        return user.suchar_votes.filter(is_funny=True).count()


class VoteDryCountRule(AchievementRule):
    metric = Achievement.Metric.COUNT_VOTE_DRY

    @classmethod
    def compute_value(
        cls,
        user: User,
        instance: Suchar | Vote | None = None,  # noqa: ARG003
    ) -> int | None:
        return user.suchar_votes.filter(is_dry=True).count()


class VoteCastCountRule(AchievementRule):
    metric = Achievement.Metric.COUNT_VOTE_CAST

    @classmethod
    def compute_value(
        cls,
        user: User,
        instance: Suchar | Vote | None = None,  # noqa: ARG003
    ) -> int | None:
        return user.suchar_votes.count()


class SumScoreRule(AchievementRule):
    metric = Achievement.Metric.SUM_SCORE

    @classmethod
    def compute_value(
        cls,
        user: User,
        instance: Suchar | Vote | None = None,  # noqa: ARG003
    ) -> int | None:
        return (
            Vote.objects.filter(suchar__author=user).aggregate(
                score=Sum(
                    Case(
                        When(is_funny=True, then=1),
                        When(is_dry=True, then=-1),
                        default=0,
                        output_field=IntegerField(),
                    ),
                ),
            )["score"]
            or 0
        )


class NightOwlRule(AchievementRule):
    metric = Achievement.Metric.NIGHT_OWL

    @classmethod
    def compute_value(
        cls,
        user: User,
        instance: Suchar | Vote | None = None,
    ) -> int | None:
        if not (isinstance(instance, Suchar) and instance.author == user):
            return None
        hour = instance.created_at.astimezone(timezone.get_current_timezone()).hour
        max_night_hour = 4
        if not (0 <= hour <= max_night_hour):
            return None
        tz = timezone.get_current_timezone()
        return (
            Suchar.objects.filter(author=user)
            .annotate(local_hour=ExtractHour("created_at", tzinfo=tz))
            .filter(local_hour__lte=max_night_hour)
            .count()
        )


class PolarizerRule(AchievementRule):
    metric = Achievement.Metric.POLARIZER

    @classmethod
    def compute_value(
        cls,
        user: User,
        instance: Suchar | Vote | None = None,  # noqa: ARG003
    ) -> int | None:
        # The highest vote count among perfectly split suchary: comparing it
        # against a threshold is equivalent to the previous per-threshold
        # ``.filter(funny_count__gte=threshold).exists()``, but no longer
        # depends on the threshold, so it runs once for the whole series.
        return (
            Suchar.objects.filter(author=user)
            .annotate(
                funny_count=Count("votes", filter=Q(votes__is_funny=True)),
                dry_count=Count("votes", filter=Q(votes__is_dry=True)),
            )
            .filter(funny_count=F("dry_count"))
            .aggregate(best=Max("funny_count"))["best"]
        )


class StreakLoginRule(AchievementRule):
    metric = Achievement.Metric.STREAK_LOGIN

    @classmethod
    def compute_value(
        cls,
        user: User,
        instance: Suchar | Vote | None = None,  # noqa: ARG003
    ) -> int | None:
        # .dates() truncates to day in the DB and returns distinct date objects,
        # avoiding loading every suchar datetime into Python memory.
        dates = set(
            Suchar.objects.filter(author=user).dates("created_at", "day"),
        )

        if not dates:
            return None

        sorted_dates = sorted(dates, reverse=True)
        streak = 1
        for i in range(len(sorted_dates) - 1):
            if (sorted_dates[i] - sorted_dates[i + 1]).days == 1:
                streak += 1
            else:
                break

        return streak


class AchievementEngine:
    _rules: dict[str, type[AchievementRule]] = {}

    @classmethod
    def register_rules(cls) -> None:
        if not cls._rules:
            for rule_cls in AchievementRule.__subclasses__():
                if rule_cls.metric:
                    cls._rules[rule_cls.metric] = rule_cls

    @staticmethod
    def check_achievements(
        user: User,
        event_type: Achievement.EventType,
        instance: Suchar | Vote | None = None,
    ) -> None:
        """
        Checks and awards achievements for a given user and event type.
        """
        AchievementEngine.register_rules()

        existing_ids = UserAchievement.objects.filter(user=user).values_list(
            "achievement_id",
            flat=True,
        )

        candidates = (
            Achievement.objects.filter(
                event_type=event_type,
            )
            .exclude(category=Achievement.Category.PERIODIC)
            .exclude(id__in=existing_ids)
        )

        # Metric values don't depend on the threshold, and nothing awarded in
        # this loop can change them, so each metric is computed at most once
        # per call and reused across every candidate tier of that metric
        # (#200). The memo is call-local on purpose — a longer-lived cache
        # would go stale the moment a new suchar or vote lands.
        computed: dict[str, int | None] = {}

        awarded = False
        for achievement in candidates:
            rule_cls = AchievementEngine._rules.get(achievement.metric)
            if rule_cls is None:
                continue
            if achievement.metric not in computed:
                computed[achievement.metric] = rule_cls.compute_value(user, instance)
            value = computed[achievement.metric]
            if value is not None and value >= achievement.threshold:
                UserAchievement.objects.create(user=user, achievement=achievement)
                awarded = True

        if awarded:
            cache.set(
                f"achievements_pending:{user.pk}",
                value=True,
                timeout=60 * 60 * 24 * 30,
            )
