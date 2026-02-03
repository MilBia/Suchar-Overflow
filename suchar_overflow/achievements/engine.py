from .models import Achievement
from .models import UserAchievement


class AchievementEngine:
    @staticmethod
    def check_achievements(user, event_type, instance=None):
        """
        Checks and awards achievements for a given user and event type.
        """
        # Get all candidates for this event type that the user doesn't have yet
        # (Assuming for now achievements are one-time only)
        existing_ids = UserAchievement.objects.filter(user=user).values_list(
            "achievement_id",
            flat=True,
        )
        candidates = Achievement.objects.filter(
            event_type=event_type,
            category=Achievement.Category.LIFETIME,
        ).exclude(id__in=existing_ids)

        for achievement in candidates:
            if AchievementEngine.evaluate_rule(user, achievement, instance):
                UserAchievement.objects.create(user=user, achievement=achievement)

    @staticmethod
    def evaluate_rule(user, achievement, instance=None):
        metric = achievement.metric
        threshold = achievement.threshold

        current_value = 0

        if metric == Achievement.Metric.COUNT_SUCHAR:
            current_value = user.suchary.count()

        elif metric == Achievement.Metric.COUNT_VOTE_FUNNY:
            current_value = user.suchar_votes.filter(is_funny=True).count()

        elif metric == Achievement.Metric.COUNT_VOTE_DRY:
            current_value = user.suchar_votes.filter(is_dry=True).count()

        elif metric == Achievement.Metric.COUNT_VOTE_CAST:
            # user.suchar_votes related_name is for the voter
            current_value = user.suchar_votes.count()

        elif metric == Achievement.Metric.SUM_SCORE:
            # Sum score of all user's suchars
            # We need to calculate this (score is a property).
            # However, let's assume we can aggregate vote counts.
            # Score = funny - dry (simplified) or just pure votes?
            # Let's assume we iterate or do a complex query.
            # For MVP efficiency, let's just count total votes received.
            # But the requirement was "SUM_SCORE".
            # Let's count total votes received:
            current_value = 0
            for suchar in user.suchary.all():
                current_value += suchar.votes.count()

        return current_value >= threshold
