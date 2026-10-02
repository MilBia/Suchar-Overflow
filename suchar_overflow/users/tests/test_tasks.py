"""Email jobs (#461): they render in the language the requester had, and retry on SMTP errors."""

import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.core import mail
from django.utils import translation
from django.utils.translation import gettext
from rq import Retry

from suchar_overflow.conftest import make_user
from suchar_overflow.users.tasks import EMAIL_RETRY_INTERVALS
from suchar_overflow.users.tasks import enqueue_email
from suchar_overflow.users.tasks import send_activation_email
from suchar_overflow.users.tasks import send_email_change_notify_email
from suchar_overflow.users.tasks import send_email_change_verify_email

if TYPE_CHECKING:
    from collections.abc import Callable


def _translated(msgid: str, language: str) -> str:
    with translation.override(language):
        return gettext(msgid)


ACTIVATION_SUBJECT = "Confirm you have a sense of humor (Account Activation)"


def test_the_two_languages_really_differ() -> None:
    """Guards the tests below: with missing catalogs both subjects would be the msgid."""
    assert _translated(ACTIVATION_SUBJECT, "pl") != _translated(ACTIVATION_SUBJECT, "en")


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "other"), [("pl", "en"), ("en", "pl")])
def test_activation_email_uses_the_language_passed_to_the_job(language: str, other: str) -> None:
    user = make_user(f"mailer_{language}", email=f"mailer_{language}@example.com")
    # The worker runs in the default language, whatever the requester spoke.
    with translation.override(other):
        send_activation_email(user.pk, "example.com", str(uuid.uuid4()), "https", language=language)
        assert translation.get_language() == other
    assert mail.outbox[0].subject == _translated(ACTIVATION_SUBJECT, language)
    assert mail.outbox[0].subject != _translated(ACTIVATION_SUBJECT, other)
    assert mail.outbox[0].to == [f"mailer_{language}@example.com"]


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["pl", "en"])
def test_email_change_sends_both_mails_in_the_given_language(language: str) -> None:
    user = make_user(f"changer_{language}", email="old@example.com")
    send_email_change_verify_email(user.pk, "new@example.com", "https://v", language=language)
    send_email_change_notify_email(user.pk, "old@example.com", "new@example.com", "https://r", language=language)
    subjects = {msg.to[0]: msg.subject for msg in mail.outbox}
    assert subjects["new@example.com"] == _translated("Confirm it's you (Email Change)", language)
    assert subjects["old@example.com"] == _translated(
        "Someone wants to change your email address (We hope it's you)",
        language,
    )
    assert any("https://v" in msg.body for msg in mail.outbox)
    assert any("https://r" in msg.body for msg in mail.outbox)


@pytest.mark.django_db
def test_each_email_change_message_is_its_own_job() -> None:
    """A retry of the failed second send must not repeat the first (#461)."""
    user = make_user("onejob", email="old@example.com")
    send_email_change_verify_email(user.pk, "new@example.com", "https://v", language="en")
    assert [msg.to for msg in mail.outbox] == [["new@example.com"]]


@pytest.mark.django_db
def test_a_smtp_failure_propagates_so_rq_can_retry() -> None:
    user = make_user("flaky", email="flaky@example.com")
    with patch("suchar_overflow.users.tasks.send_mail", side_effect=OSError("smtp down")), pytest.raises(OSError):  # noqa: PT011
        send_activation_email(user.pk, "example.com", str(uuid.uuid4()), "https")


def test_enqueue_email_passes_language_and_retry_policy(rq_queue: MagicMock) -> None:
    with translation.override("en"):
        enqueue_email(send_activation_email, 7, "example.com", "token", "https")
    rq_queue.enqueue.assert_called_once()
    call = rq_queue.enqueue.call_args
    assert call.args == (send_activation_email, 7, "example.com", "token", "https")
    assert call.kwargs["language"] == "en"
    retry = call.kwargs["retry"]
    assert isinstance(retry, Retry)
    assert retry.max == len(EMAIL_RETRY_INTERVALS) == 3
    assert retry.intervals == [10, 60, 300]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "send",
    [
        lambda pk: send_activation_email(pk, "example.com", "t", "https"),
        lambda pk: send_email_change_verify_email(pk, "n@example.com", "https://v"),
        lambda pk: send_email_change_notify_email(pk, "o@example.com", "n@example.com", "https://r"),
    ],
)
def test_a_deleted_user_is_skipped_not_retried(send: Callable[[int], None], caplog: pytest.LogCaptureFixture) -> None:
    send(987654321)  # no exception: RQ would otherwise retry and then mail the admins
    assert mail.outbox == []
    assert "no longer exists" in caplog.text
