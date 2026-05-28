from django.core.cache import cache
from django.db.models import Case
from django.db.models import Count
from django.db.models import F
from django.db.models import IntegerField
from django.db.models import Q
from django.db.models import Sum
from django.db.models import When
from django.db.models.functions import ExtractHour
from django.utils import timezone

from suchar_overflow.suchary.models import Suchar
from suchar_overflow.suchary.models import Vote

from .models import Achievement
from .models import UserAchievement


class AchievementRule:
    metric: "Achievement.Metric | None" = None

    @classmethod
    def evaluate(cls, user, threshold, instance=None):
        raise NotImplementedError


class SucharCountRule(AchievementRule):
    metric = Achievement.Metric.COUNT_SUCHAR

    @classmethod
    def evaluate(cls, user, threshold, instance=None):
        return user.suchary.count() >= threshold


class VoteFunnyCountRule(AchievementRule):
    metric = Achievement.Metric.COUNT_VOTE_FUNNY

    @classmethod
    def evaluate(cls, user, threshold, instance=None):
        return user.suchar_votes.filter(is_funny=True).count() >= threshold


class VoteDryCountRule(AchievementRule):
    metric = Achievement.Metric.COUNT_VOTE_DRY

    @classmethod
    def evaluate(cls, user, threshold, instance=None):
        return user.suchar_votes.filter(is_dry=True).count() >= threshold


class VoteCastCountRule(AchievementRule):
    metric = Achievement.Metric.COUNT_VOTE_CAST

    @classmethod
    def evaluate(cls, user, threshold, instance=None):
        return user.suchar_votes.count() >= threshold


class SumScoreRule(AchievementRule):
    metric = Achievement.Metric.SUM_SCORE

    @classmethod
    def evaluate(cls, user, threshold, instance=None):
        total_score = (
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
        return total_score >= threshold


class NightOwlRule(AchievementRule):
    metric = Achievement.Metric.NIGHT_OWL

    @classmethod
    def evaluate(cls, user, threshold, instance=None):
        if not (isinstance(instance, Suchar) and instance.author == user):
            return False
        hour = instance.created_at.astimezone(timezone.get_current_timezone()).hour
        max_night_hour = 4
        if not (0 <= hour <= max_night_hour):
            return False
        tz = timezone.get_current_timezone()
        night_count = (
            Suchar.objects.filter(author=user)
            .annotate(local_hour=ExtractHour("created_at", tzinfo=tz))
            .filter(local_hour__lte=max_night_hour)
            .count()
        )
        return night_count >= threshold


class PolarizerRule(AchievementRule):
    metric = Achievement.Metric.POLARIZER

    @classmethod
    def evaluate(cls, user, threshold, instance=None):
        return (
            Suchar.objects.filter(author=user)
            .annotate(
                funny_count=Count("votes", filter=Q(votes__is_funny=True)),
                dry_count=Count("votes", filter=Q(votes__is_dry=True)),
            )
            .filter(funny_count=F("dry_count"), funny_count__gte=threshold)
            .exists()
        )


class StreakLoginRule(AchievementRule):
    metric = Achievement.Metric.STREAK_LOGIN

    @classmethod
    def evaluate(cls, user, threshold, instance=None):
        # .dates() truncates to day in the DB and returns distinct date objects,
        # avoiding loading every suchar datetime into Python memory.
        dates = set(
            Suchar.objects.filter(author=user).dates("created_at", "day"),
        )

        if not dates:
            return False

        sorted_dates = sorted(dates, reverse=True)
        streak = 1
        for i in range(len(sorted_dates) - 1):
            if (sorted_dates[i] - sorted_dates[i + 1]).days == 1:
                streak += 1
                if streak >= threshold:
                    return True
            else:
                break

        return streak >= threshold


class AchievementEngine:
    _rules: "dict[str, type[AchievementRule]]" = {}

    @classmethod
    def register_rules(cls):
        if not cls._rules:
            for rule_cls in AchievementRule.__subclasses__():
                if rule_cls.metric:
                    cls._rules[rule_cls.metric] = rule_cls

    @staticmethod
    def check_achievements(user, event_type, instance=None):
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

        awarded = False
        for achievement in candidates:
            rule_cls = AchievementEngine._rules.get(achievement.metric)
            if rule_cls and rule_cls.evaluate(user, achievement.threshold, instance):
                UserAchievement.objects.create(user=user, achievement=achievement)
                awarded = True

        if awarded:
            cache.set(
                f"achievements_pending:{user.pk}",
                value=True,
                timeout=60 * 60 * 24 * 30,
            )
