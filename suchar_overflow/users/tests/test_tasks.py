"""Email jobs (#461): they render in the language the requester had, and retry on SMTP errors."""

import uuid
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
from suchar_overflow.users.tasks import send_email_change_emails


@pytest.mark.django_db
def test_activation_email_uses_the_language_passed_to_the_job() -> None:
    user = make_user("mailer", email="mailer@example.com")
    with translation.override("pl"):
        expected_pl = gettext("Confirm you have a sense of humor (Account Activation)")
    # The worker runs in the default language, whatever the requester spoke.
    with translation.override("en"):
        send_activation_email(user.pk, "example.com", str(uuid.uuid4()), "https", language="pl")
        assert translation.get_language() == "en"
    assert mail.outbox[0].subject == expected_pl
    assert mail.outbox[0].to == ["mailer@example.com"]


@pytest.mark.django_db
def test_activation_email_in_english_when_asked() -> None:
    user = make_user("mailer_en", email="mailer_en@example.com")
    send_activation_email(user.pk, "example.com", str(uuid.uuid4()), "https", language="en")
    assert mail.outbox[0].subject == "Confirm you have a sense of humor (Account Activation)"


@pytest.mark.django_db
def test_email_change_sends_both_mails_in_the_given_language() -> None:
    user = make_user("changer", email="old@example.com")
    send_email_change_emails(user.pk, "old@example.com", "new@example.com", "https://v", "https://r", language="en")
    subjects = {msg.to[0]: msg.subject for msg in mail.outbox}
    assert subjects["new@example.com"] == "Confirm it's you (Email Change)"
    assert subjects["old@example.com"] == "Someone wants to change your email address (We hope it's you)"
    assert any("https://v" in msg.body for msg in mail.outbox)
    assert any("https://r" in msg.body for msg in mail.outbox)


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
