import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CharField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    Default custom user model for Suchar Overflow.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    # First and last name do not cover name patterns around the globe
    name = CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    email = models.EmailField(_("email address"), unique=True)

    @property
    def display_name(self) -> str:
        """Return name if set, otherwise username."""
        return self.name if self.name else self.username

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"username": self.username})


class EmailChangeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        VERIFIED = "verified", _("Verified")
        REVOKED = "revoked", _("Revoked")

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="email_change_requests",
    )
    new_email = models.EmailField()
    old_email = models.EmailField(blank=True, null=True)  # noqa: DJ001
    verification_token = models.UUIDField(default=uuid.uuid4, unique=True)
    revocation_token = models.UUIDField(default=uuid.uuid4, unique=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Email Change Request")
        verbose_name_plural = _("Email Change Requests")

    def __str__(self):
        return (
            f"{self.user.username}: {self.old_email} -> {self.new_email} "
            f"({self.status})"
        )
