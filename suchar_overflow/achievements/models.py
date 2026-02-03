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
