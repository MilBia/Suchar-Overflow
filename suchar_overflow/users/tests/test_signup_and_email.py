"""
Tests for user signup, account activation, and email-change flows.
"""

import datetime
import uuid
from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from suchar_overflow.users.models import ActivationToken
from suchar_overflow.users.models import EmailChangeRequest

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_user(username, email=None, password="password", *, is_active=True):  # noqa: S107
    return User.objects.create_user(
        username=username,
        email=email or f"{username}@example.com",
        password=password,
        is_active=is_active,
    )


@pytest.fixture(autouse=True)
def sync_rq(monkeypatch):
    """Run RQ jobs synchronously so emails land in mail.outbox during tests."""
    monkeypatch.setattr(
        "django_rq.enqueue",
        lambda func, *args, **kwargs: func(*args, **kwargs),
    )


# ---------------------------------------------------------------------------
# SignupView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_signup_get_renders_form(client):
    response = client.get(reverse("users:signup"))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_signup_creates_inactive_user(client):
    response = client.post(
        reverse("users:signup"),
        {
            "username": "newuser",
            "email": "newuser@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    assert response.status_code == HTTPStatus.FOUND
    user = User.objects.get(username="newuser")
    assert not user.is_active


@pytest.mark.django_db
def test_signup_creates_activation_token(client):
    client.post(
        reverse("users:signup"),
        {
            "username": "newuser",
            "email": "newuser@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    user = User.objects.get(username="newuser")
    assert ActivationToken.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_signup_sends_activation_email(client):
    client.post(
        reverse("users:signup"),
        {
            "username": "newuser",
            "email": "newuser@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    assert len(mail.outbox) == 1
    assert "newuser@example.com" in mail.outbox[0].to


@pytest.mark.django_db
def test_signup_redirects_to_done_page(client):
    response = client.post(
        reverse("users:signup"),
        {
            "username": "newuser",
            "email": "newuser@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    assert response.status_code == HTTPStatus.FOUND
    assert response["Location"] == reverse("users:signup_done")


@pytest.mark.django_db
def test_signup_duplicate_username_shows_error(client):
    make_user("existing")
    response = client.post(
        reverse("users:signup"),
        {
            "username": "existing",
            "email": "other@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    assert response.status_code == HTTPStatus.OK
    assert User.objects.filter(username="existing").count() == 1


@pytest.mark.django_db
def test_signup_duplicate_email_shows_error(client):
    make_user("existing", email="taken@example.com")
    response = client.post(
        reverse("users:signup"),
        {
            "username": "newuser",
            "email": "taken@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    assert response.status_code == HTTPStatus.OK
    assert not User.objects.filter(username="newuser").exists()


# ---------------------------------------------------------------------------
# ActivateAccountView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_activate_valid_token_activates_user(client):
    user = make_user("inactive", is_active=False)
    token = ActivationToken.objects.create(user=user)

    response = client.get(
        reverse("users:activate", kwargs={"token": token.token}),
    )

    assert response.status_code == HTTPStatus.OK
    user.refresh_from_db()
    assert user.is_active


@pytest.mark.django_db
def test_activate_valid_token_is_deleted_after_use(client):
    user = make_user("inactive", is_active=False)
    token = ActivationToken.objects.create(user=user)

    client.get(reverse("users:activate", kwargs={"token": token.token}))

    assert not ActivationToken.objects.filter(pk=token.pk).exists()


@pytest.mark.django_db
def test_activate_invalid_token_does_not_activate(client):
    user = make_user("inactive", is_active=False)

    response = client.get(
        reverse("users:activate", kwargs={"token": uuid.uuid4()}),
    )

    assert response.status_code == HTTPStatus.OK
    user.refresh_from_db()
    assert not user.is_active


@pytest.mark.django_db
def test_activate_expired_token_does_not_activate(client):
    user = make_user("inactive", is_active=False)
    token = ActivationToken.objects.create(user=user)
    # Backdate beyond the 72-hour expiry window.
    ActivationToken.objects.filter(pk=token.pk).update(
        created_at=timezone.now() - datetime.timedelta(hours=73),
    )

    response = client.get(
        reverse("users:activate", kwargs={"token": token.token}),
    )

    assert response.status_code == HTTPStatus.OK
    user.refresh_from_db()
    assert not user.is_active
    # Expired token must be cleaned up.
    assert not ActivationToken.objects.filter(pk=token.pk).exists()


# ---------------------------------------------------------------------------
# EmailChangeInitiateView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_email_change_initiate_requires_login(client):
    response = client.get(reverse("users:email_change_initiate"))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_email_change_initiate_get_renders_form(client):
    user = make_user("user1")
    client.force_login(user)
    response = client.get(reverse("users:email_change_initiate"))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_email_change_creates_request_and_sends_emails(client):
    user = make_user("user1", email="old@example.com")
    client.force_login(user)

    response = client.post(
        reverse("users:email_change_initiate"),
        {"email": "new@example.com"},
    )

    assert response.status_code == HTTPStatus.FOUND
    assert EmailChangeRequest.objects.filter(
        user=user,
        new_email="new@example.com",
    ).exists()
    # Two emails: one to new address (verify), one to old (revoke notification).
    assert len(mail.outbox) == 2  # noqa: PLR2004
    recipients = {msg.to[0] for msg in mail.outbox}
    assert "new@example.com" in recipients
    assert "old@example.com" in recipients


@pytest.mark.django_db
def test_email_change_rejects_already_taken_email(client):
    make_user("other", email="taken@example.com")
    user = make_user("user1", email="mine@example.com")
    client.force_login(user)

    response = client.post(
        reverse("users:email_change_initiate"),
        {"email": "taken@example.com"},
    )

    assert response.status_code == HTTPStatus.OK
    assert not EmailChangeRequest.objects.filter(user=user).exists()


# ---------------------------------------------------------------------------
# EmailChangeConfirmView (verification link)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_email_change_confirm_success(client):
    user = make_user("user1", email="old@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
    )
    client.force_login(user)

    response = client.get(
        reverse(
            "users:email_change_verify",
            kwargs={"token": str(email_req.verification_token)},
        ),
    )

    assert response.status_code == HTTPStatus.OK
    user.refresh_from_db()
    assert user.email == "new@example.com"
    email_req.refresh_from_db()
    assert email_req.status == EmailChangeRequest.Status.VERIFIED


@pytest.mark.django_db
def test_email_change_confirm_expired_token(client):
    user = make_user("user1", email="old@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
    )
    EmailChangeRequest.objects.filter(pk=email_req.pk).update(
        created_at=timezone.now() - datetime.timedelta(hours=25),
    )
    client.force_login(user)

    response = client.get(
        reverse(
            "users:email_change_verify",
            kwargs={"token": str(email_req.verification_token)},
        ),
    )

    assert response.status_code == HTTPStatus.OK
    user.refresh_from_db()
    assert user.email == "old@example.com"
    email_req.refresh_from_db()
    assert email_req.status == EmailChangeRequest.Status.REVOKED


@pytest.mark.django_db
def test_email_change_confirm_already_used_token(client):
    user = make_user("user1", email="old@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
        status=EmailChangeRequest.Status.VERIFIED,
    )
    client.force_login(user)

    response = client.get(
        reverse(
            "users:email_change_verify",
            kwargs={"token": str(email_req.verification_token)},
        ),
    )

    assert response.status_code == HTTPStatus.OK
    user.refresh_from_db()
    assert user.email == "old@example.com"


@pytest.mark.django_db
def test_email_change_confirm_invalid_token(client):
    user = make_user("user1")
    client.force_login(user)

    response = client.get(
        reverse("users:email_change_verify", kwargs={"token": str(uuid.uuid4())}),
    )
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_email_change_confirm_rejects_duplicate_email(client):
    """If the new email is taken by the time the link is clicked, it should fail."""
    user = make_user("user1", email="old@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
    )
    make_user("other", email="new@example.com")
    client.force_login(user)

    response = client.get(
        reverse(
            "users:email_change_verify",
            kwargs={"token": str(email_req.verification_token)},
        ),
    )

    assert response.status_code == HTTPStatus.OK
    user.refresh_from_db()
    assert user.email == "old@example.com"


# ---------------------------------------------------------------------------
# EmailChangeRevokeView (revocation link)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_email_change_revoke_pending_cancels(client):
    user = make_user("user1", email="old@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
        status=EmailChangeRequest.Status.PENDING,
    )
    client.force_login(user)

    response = client.get(
        reverse(
            "users:email_change_revoke",
            kwargs={"token": str(email_req.revocation_token)},
        ),
    )

    assert response.status_code == HTTPStatus.OK
    email_req.refresh_from_db()
    assert email_req.status == EmailChangeRequest.Status.REVOKED
    user.refresh_from_db()
    assert user.email == "old@example.com"


@pytest.mark.django_db
def test_email_change_revoke_verified_undoes_change(client):
    """Revoking a VERIFIED request should revert the email back to old_email."""
    user = make_user("user1", email="new@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
        status=EmailChangeRequest.Status.VERIFIED,
    )
    client.force_login(user)

    response = client.get(
        reverse(
            "users:email_change_revoke",
            kwargs={"token": str(email_req.revocation_token)},
        ),
    )

    assert response.status_code == HTTPStatus.OK
    user.refresh_from_db()
    assert user.email == "old@example.com"
    email_req.refresh_from_db()
    assert email_req.status == EmailChangeRequest.Status.REVOKED


@pytest.mark.django_db
def test_email_change_revoke_invalid_token_is_graceful(client):
    user = make_user("user1")
    client.force_login(user)

    response = client.get(
        reverse("users:email_change_revoke", kwargs={"token": str(uuid.uuid4())}),
    )
    assert response.status_code == HTTPStatus.OK
