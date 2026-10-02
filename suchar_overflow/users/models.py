import datetime
import hashlib
import secrets
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CharField
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    Default custom user model for Suchar Overflow.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

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


class AuthToken(models.Model):
    """API bearer token (``Authorization: Bearer <token>``, #459), one per user.

    Only the SHA-256 digest is stored, so a database leak (or an admin reading the
    row) yields no usable credential; the value exists in clear text once, right after
    ``issue()``. The token is 256 bits of randomness, so a plain unsalted digest is
    enough (there is nothing to brute-force) and lets ``authenticate`` find the row by
    an indexed equality lookup instead of comparing secrets in Python.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="token",
        verbose_name=_("User"),
    )
    token_hash = models.CharField(_("Token hash"), max_length=64, unique=True, editable=False)
    created = models.DateTimeField(_("Created"), auto_now_add=True)

    class Meta:
        verbose_name = _("API token")
        verbose_name_plural = _("API tokens")

    def __str__(self) -> str:
        user_name = self.user.username if "user" in self._state.fields_cache else f"User #{self.user_id}"
        return f"AuthToken({user_name})"

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @staticmethod
    def new_secret() -> str:
        return secrets.token_urlsafe(32)

    @classmethod
    def issue(cls, user: User) -> tuple[AuthToken, str]:
        """Create (or replace) ``user``'s token; returns it with the one-time clear text."""
        raw_token = cls.new_secret()
        token, _created = cls.objects.update_or_create(
            user=user,
            defaults={"token_hash": cls.hash_token(raw_token), "created": timezone.now()},
        )
        return token, raw_token


class ActivationToken(models.Model):
    EXPIRY_HOURS = 72

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="activation_token",
        verbose_name=_("User"),
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Activation Token")
        verbose_name_plural = _("Activation Tokens")

    def __str__(self) -> str:
        user_name = self.user.username if "user" in self._state.fields_cache else f"User #{self.user_id}"
        return f"ActivationToken({user_name})"

    def is_valid(self) -> bool:
        return timezone.now() < self.created_at + datetime.timedelta(
            hours=self.EXPIRY_HOURS,
        )


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

    def __str__(self) -> str:
        user_name = self.user.username if "user" in self._state.fields_cache else f"User #{self.user_id}"
        return f"{user_name}: {self.old_email} -> {self.new_email} ({self.status})"
