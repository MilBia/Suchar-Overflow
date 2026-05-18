from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import gettext as _


def send_activation_email(user_pk, domain, token, protocol):
    from suchar_overflow.users.models import User  # noqa: PLC0415

    user = User.objects.get(pk=user_pk)
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


def send_email_change_emails(user_pk, old_email, new_email, verify_link, revoke_link):
    from suchar_overflow.users.models import User  # noqa: PLC0415

    user = User.objects.get(pk=user_pk)

    mail_subject_new = _("Confirm it's you (Email Change)")
    message_new = render_to_string(
        "users/email_verify_email.txt",
        {
            "user": user,
            "verify_link": verify_link,
            "new_email": new_email,
        },
    )
    send_mail(mail_subject_new, message_new, settings.DEFAULT_FROM_EMAIL, [new_email])

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
    send_mail(mail_subject_old, message_old, settings.DEFAULT_FROM_EMAIL, [old_email])
