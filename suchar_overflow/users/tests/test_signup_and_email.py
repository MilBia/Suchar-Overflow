"""
Tests for user signup, account activation, and email-change flows.
"""

import datetime
import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from suchar_overflow.conftest import make_user
from suchar_overflow.conftest import run_enqueued_jobs
from suchar_overflow.users.models import ActivationToken
from suchar_overflow.users.models import EmailChangeRequest
from suchar_overflow.users.tasks import send_activation_email
from suchar_overflow.users.tasks import send_email_change_notify_email
from suchar_overflow.users.tasks import send_email_change_verify_email

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from django.test import Client

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# SignupView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_signup_get_renders_form(client: Client) -> None:
    response = client.get(reverse("users:signup"))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_signup_creates_inactive_user(client: Client) -> None:
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
def test_signup_creates_activation_token(client: Client) -> None:
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


@pytest.mark.django_db(transaction=True)
def test_signup_enqueues_activation_email(client: Client, rq_queue: MagicMock) -> None:
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
    token = ActivationToken.objects.get(user=user)
    # Queued, not sent in the request: the SMTP server is the worker's problem (#461).
    assert mail.outbox == []
    rq_queue.enqueue.assert_called_once()
    task, *args = rq_queue.enqueue.call_args.args
    assert task is send_activation_email
    assert args == [user.pk, "testserver", str(token.token), "http"]
    assert rq_queue.enqueue.call_args.kwargs["language"] == "pl"
    assert rq_queue.enqueue.call_args.kwargs["retry"].max == 3
    assert rq_queue.enqueue.call_args.kwargs["retry"].intervals == [10, 60, 300]
    run_enqueued_jobs(rq_queue)
    assert "newuser@example.com" in mail.outbox[0].to


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("language", ["en", "pl"])
def test_signup_passes_the_requesters_language_to_the_job(
    client: Client,
    rq_queue: MagicMock,
    language: str,
) -> None:
    """``sync_to_async`` must carry the request's active language into ``enqueue_email``;
    the worker has no request, so this is the only place it can come from (#461)."""
    client.post(
        reverse("users:signup"),
        {
            "username": "polyglot",
            "email": "polyglot@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
        headers={"Accept-Language": language},
    )
    assert rq_queue.enqueue.call_args.kwargs["language"] == language


@pytest.mark.django_db(transaction=True)
def test_signup_with_unreachable_queue_leaves_no_stranded_account(client: Client, rq_queue: MagicMock) -> None:
    rq_queue.enqueue.side_effect = ConnectionError("redis down")
    client.raise_request_exception = False
    response = client.post(
        reverse("users:signup"),
        {
            "username": "stranded",
            "email": "stranded@example.com",
            "password1": "Str0ngP@ssword!",
            "password2": "Str0ngP@ssword!",
        },
    )
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    # The username/email stay free, so the visitor can simply try again.
    assert not User.objects.filter(username="stranded").exists()


@pytest.mark.django_db(transaction=True)
def test_email_change_with_unreachable_queue_drops_the_request(client: Client, rq_queue: MagicMock) -> None:
    rq_queue.enqueue.side_effect = ConnectionError("redis down")
    client.raise_request_exception = False
    user = make_user("user1", email="old@example.com")
    client.force_login(user)
    response = client.post(reverse("users:email_change_initiate"), {"email": "new@example.com"})
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert not EmailChangeRequest.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_signup_redirects_to_done_page(client: Client) -> None:
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
def test_signup_duplicate_username_shows_error(client: Client) -> None:
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
def test_signup_duplicate_email_shows_error(client: Client) -> None:
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
def test_activate_valid_token_activates_user(client: Client) -> None:
    user = make_user("inactive", is_active=False)
    token = ActivationToken.objects.create(user=user)

    response = client.get(
        reverse("users:activate", kwargs={"token": token.token}),
    )

    assert response.status_code == HTTPStatus.OK
    user.refresh_from_db()
    assert user.is_active


@pytest.mark.django_db
def test_activate_valid_token_is_deleted_after_use(client: Client) -> None:
    user = make_user("inactive", is_active=False)
    token = ActivationToken.objects.create(user=user)

    client.get(reverse("users:activate", kwargs={"token": token.token}))

    assert not ActivationToken.objects.filter(pk=token.pk).exists()


@pytest.mark.django_db
def test_activate_invalid_token_does_not_activate(client: Client) -> None:
    user = make_user("inactive", is_active=False)

    response = client.get(
        reverse("users:activate", kwargs={"token": uuid.uuid4()}),
    )

    assert response.status_code == HTTPStatus.OK
    user.refresh_from_db()
    assert not user.is_active


@pytest.mark.django_db
def test_activate_expired_token_does_not_activate(client: Client) -> None:
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
def test_email_change_initiate_requires_login(client: Client) -> None:
    response = client.get(reverse("users:email_change_initiate"))
    assert response.status_code == HTTPStatus.FOUND
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_email_change_initiate_get_renders_form(client: Client) -> None:
    user = make_user("user1")
    client.force_login(user)
    response = client.get(reverse("users:email_change_initiate"))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db(transaction=True)
def test_email_change_creates_request_and_enqueues_emails(client: Client, rq_queue: MagicMock) -> None:
    user = make_user("user1", email="old@example.com")
    client.force_login(user)

    response = client.post(
        reverse("users:email_change_initiate"),
        {"email": "new@example.com"},
        # English, so the language assertion below cannot pass on the default alone.
        headers={"Accept-Language": "en"},
    )

    assert response.status_code == HTTPStatus.FOUND
    assert EmailChangeRequest.objects.filter(
        user=user,
        new_email="new@example.com",
    ).exists()
    assert mail.outbox == []
    # One job per message: a retry of one must not re-send the other.
    assert [call.args[0] for call in rq_queue.enqueue.call_args_list] == [
        send_email_change_verify_email,
        send_email_change_notify_email,
    ]
    assert {call.kwargs["language"] for call in rq_queue.enqueue.call_args_list} == {"en"}
    run_enqueued_jobs(rq_queue)
    # Two emails: one to new address (verify), one to old (revoke notification).
    assert len(mail.outbox) == 2
    recipients = {msg.to[0] for msg in mail.outbox}
    assert "new@example.com" in recipients
    assert "old@example.com" in recipients


@pytest.mark.django_db
def test_email_change_rejects_already_taken_email(client: Client) -> None:
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
def test_email_change_confirm_success(client: Client) -> None:
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
def test_email_change_confirm_expired_token(client: Client) -> None:
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
def test_email_change_confirm_already_used_token(client: Client) -> None:
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
def test_email_change_confirm_invalid_token(client: Client) -> None:
    user = make_user("user1")
    client.force_login(user)

    response = client.get(
        reverse("users:email_change_verify", kwargs={"token": str(uuid.uuid4())}),
    )
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_email_change_confirm_rejects_duplicate_email(client: Client) -> None:
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


@pytest.mark.django_db
def test_email_change_confirm_handles_unique_email_race(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two pending requests confirming the same address race ``User.email``'s
    unique constraint (#333).

    The ``aexists()`` pre-check can pass for both; the loser's ``asave()`` then
    raises ``IntegrityError``. The view must catch it and render the existing
    "email already taken" page instead of a 500, leaving this request PENDING
    so the pre-check branch and the race branch behave identically.
    """
    user = make_user("racer", email="old@example.com")
    email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new@example.com",
        old_email="old@example.com",
    )
    client.force_login(user)

    async def _raise_integrity_error(*_args: object, **_kwargs: object) -> None:
        # Stand-in for Postgres rejecting the duplicate User.email on the
        # losing request's UPDATE.
        raise IntegrityError

    monkeypatch.setattr(User, "asave", _raise_integrity_error)

    response = client.get(
        reverse(
            "users:email_change_verify",
            kwargs={"token": str(email_req.verification_token)},
        ),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.context["error"] == gettext("Email already taken.")
    user.refresh_from_db()
    assert user.email == "old@example.com"
    email_req.refresh_from_db()
    assert email_req.status == EmailChangeRequest.Status.PENDING


# ---------------------------------------------------------------------------
# EmailChangeRevokeView (revocation link)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_email_change_revoke_pending_cancels(client: Client) -> None:
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
def test_email_change_revoke_verified_undoes_change(client: Client) -> None:
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
def test_email_change_revoke_invalid_token_is_graceful(client: Client) -> None:
    user = make_user("user1")
    client.force_login(user)

    response = client.get(
        reverse("users:email_change_revoke", kwargs={"token": str(uuid.uuid4())}),
    )
    assert response.status_code == HTTPStatus.OK
