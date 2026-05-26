from django.conf import settings
from django.db import models
from django.utils import timezone
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
    published_at = models.DateTimeField(
        _("Publication Date"),
        default=timezone.now,
        db_index=True,
    )
    tags = models.ManyToManyField(Tag, related_name="suchary", blank=True)

    def __str__(self):
        author_name = (
            self.author.username
            if "author" in self._state.fields_cache
            else f"User #{self.author_id}"
        )
        return f"Suchar by {author_name} at {self.published_at}"

    @property
    def is_published(self):
        return self.published_at <= timezone.now()


class Vote(models.Model):
    suchar = models.ForeignKey(Suchar, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="suchar_votes",
    )
    is_funny = models.BooleanField(default=False)
    is_dry = models.BooleanField(default=False)

    class Meta:
        unique_together = ("suchar", "user")

    def __str__(self):
        user_name = (
            self.user.username
            if "user" in self._state.fields_cache
            else f"User #{self.user_id}"
        )
        return (
            f"{user_name} voted on Suchar #{self.suchar_id} "
            f"(Funny: {self.is_funny}, Dry: {self.is_dry})"
        )
