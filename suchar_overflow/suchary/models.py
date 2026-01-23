from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Suchar(models.Model):
    text = models.TextField(_("Suchar text"))
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="suchary",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(Tag, related_name="suchary", blank=True)

    def __str__(self):
        return f"Suchar by {self.author} at {self.created_at}"


class Vote(models.Model):
    UP = 1
    DOWN = -1
    VOTE_CHOICES = (
        (UP, "Up"),
        (DOWN, "Down"),
    )

    suchar = models.ForeignKey(Suchar, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="suchar_votes",
    )
    value = models.IntegerField(choices=VOTE_CHOICES)

    class Meta:
        unique_together = ("suchar", "user")

    def __str__(self):
        return f"{self.user} voted {self.value} for Suchar #{self.suchar.pk}"
