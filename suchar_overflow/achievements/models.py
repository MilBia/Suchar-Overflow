from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Achievement(models.Model):
    class Category(models.TextChoices):
        LIFETIME = "LIFETIME", _("Lifetime")
        PERIODIC = "PERIODIC", _("Periodic")
        STREAK = "STREAK", _("Streak")

    class EventType(models.TextChoices):
        SUCHAR_POSTED = "SUCHAR_POSTED", _("Suchar Posted")
        VOTE_RECEIVED = "VOTE_RECEIVED", _("Vote Received")
        VOTE_CAST = "VOTE_CAST", _("Vote Cast")

    class Metric(models.TextChoices):
        COUNT_SUCHAR = "COUNT_SUCHAR", _("Suchar Count")
        COUNT_VOTE_FUNNY = "COUNT_VOTE_FUNNY", _("Funny Vote Count")
        COUNT_VOTE_DRY = "COUNT_VOTE_DRY", _("Dry Vote Count")
        COUNT_VOTE_CAST = "COUNT_VOTE_CAST", _("Vote Cast Count")
        SUM_SCORE = "SUM_SCORE", _("Total Score")
        NIGHT_OWL = "NIGHT_OWL", _("Night Owl")
        STREAK_LOGIN = "STREAK_LOGIN", _("Login Streak")
        POLARIZER = "POLARIZER", _("Polarizer")

    class Tier(models.IntegerChoices):
        NONE = 0, _("None")
        BRONZE = 1, _("Bronze")
        SILVER = 2, _("Silver")
        GOLD = 3, _("Gold")
        PLATINUM = 4, _("Platinum")
        DIAMOND = 5, _("Diamond")

    name = models.CharField(_("Name"), max_length=100)
    slug = models.SlugField(_("Slug"), unique=True, max_length=100)
    description = models.TextField(_("Description"))

    # Visuals
    icon_content = models.TextField(_("Icon Content"), help_text=_("Raw SVG XML"))

    # Logic
    category = models.CharField(
        _("Category"),
        max_length=20,
        choices=Category.choices,
        default=Category.LIFETIME,
    )
    event_type = models.CharField(
        _("Event Type"),
        max_length=20,
        choices=EventType.choices,
        default=EventType.SUCHAR_POSTED,
    )
    metric = models.CharField(
        _("Metric"),
        max_length=20,
        choices=Metric.choices,
        default=Metric.COUNT_SUCHAR,
    )
    threshold = models.PositiveIntegerField(_("Threshold"), default=1)

    # Progression / Grouping
    theme = models.CharField(
        _("Theme"),
        max_length=100,
        blank=True,
        help_text=_("E.g. 'Christmas', 'Programming'. Leave blank for general."),
    )
    tier = models.IntegerField(
        _("Tier"),
        choices=Tier.choices,
        default=Tier.NONE,
        help_text=_("Difficulty/Rarity tier of the achievement"),
    )
    is_secret = models.BooleanField(
        _("Secret Achievement"),
        default=False,
        help_text=_("If checked, name and description are hidden until unlocked."),
    )

    class Meta:
        verbose_name = _("Achievement")
        verbose_name_plural = _("Achievements")

    def __str__(self):
        return self.name


class UserAchievement(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_achievements",
    )
    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name="awarded_to",
    )
    awarded_at = models.DateTimeField(auto_now_add=True)
    is_seen = models.BooleanField(_("Seen by user"), default=False)

    class Meta:
        verbose_name = _("User Achievement")
        verbose_name_plural = _("User Achievements")
        unique_together = ("user", "achievement")

    def __str__(self):
        return f"{self.user} - {self.achievement}"
