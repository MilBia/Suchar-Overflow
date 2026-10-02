"""Email jobs run by the RQ worker (#461); the views queue them with ``enqueue_email``.

The worker has no request, so it runs in ``LANGUAGE_CODE``: each job carries the
requester's language and renders inside ``translation.override``. Jobs take only a
primary key and serialisable values, never a model instance.
"""

from typing import TYPE_CHECKING

import django_rq
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.translation import gettext as _
from rq import Retry

from suchar_overflow.users.models import User

if TYPE_CHECKING:
    from collections.abc import Callable

#: Seconds before the 1st, 2nd and 3rd retry of a failed send (a flaky SMTP server).
EMAIL_RETRY_INTERVALS = [10, 60, 300]


def enqueue_email(task: Callable[..., None], *args: object) -> None:
    """Queue ``task(*args, language=<active language>)`` with retries (#461).

    ``enqueue`` talks to Redis synchronously, so async views call this through
    ``sync_to_async``. Queue it only after every row the task reads is saved.
    """
    django_rq.get_queue(settings.RQ_QUEUE_NAME).enqueue(
        task,
        *args,
        language=translation.get_language(),
        retry=Retry(max=len(EMAIL_RETRY_INTERVALS), interval=EMAIL_RETRY_INTERVALS),
    )


def send_activation_email(
    user_pk: int,
    domain: str,
    token: str,
    protocol: str,
    language: str | None = None,
) -> None:
    user = User.objects.get(pk=user_pk)
    with translation.override(language):
        mail_subject = _("Confirm you have a sense of humor (Account Activation)")
        message = render_to_string(
            "registration/activation_email.txt",
            {
                "user": user,
                "domain": domain,
                "token": token,
                "protocol": protocol,
            },
        )
    send_mail(mail_subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])


def send_email_change_emails(  # noqa: PLR0913, PLR0917
    user_pk: int,
    old_email: str,
    new_email: str,
    verify_link: str,
    revoke_link: str,
    language: str | None = None,
) -> None:
    user = User.objects.get(pk=user_pk)

    with translation.override(language):
        mail_subject_new = _("Confirm it's you (Email Change)")
        message_new = render_to_string(
            "users/email_verify_email.txt",
            {
                "user": user,
                "verify_link": verify_link,
                "new_email": new_email,
            },
        )
        mail_subject_old = _(
            "Someone wants to change your email address (We hope it's you)",
        )
        message_old = render_to_string(
            "users/email_notify_old_email.txt",
            {
                "user": user,
                "revoke_link": revoke_link,
                "new_email": new_email,
            },
        )
    send_mail(mail_subject_new, message_new, settings.DEFAULT_FROM_EMAIL, [new_email])
    send_mail(mail_subject_old, message_old, settings.DEFAULT_FROM_EMAIL, [old_email])
