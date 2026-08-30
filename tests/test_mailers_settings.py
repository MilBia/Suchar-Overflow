"""Regression guard for issue #227 — email config lives in MAILERS.

Django 6.x deprecated the flat ``EMAIL_*`` settings in favour of a
``DATABASES``/``CACHES``-style ``MAILERS`` mapping; the old names are removed
in Django 7.0 and every ``just test`` run used to print

    RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. ...
    RemovedInDjango70Warning: The EMAIL_TIMEOUT setting is deprecated. ...

Once ``MAILERS`` is defined, Django raises ``ImproperlyConfigured`` at startup
if any deprecated ``EMAIL_*`` name is *also* set, and makes those names raise
``AttributeError`` on access. These tests pin that the migrated config is
present, that no deprecated name leaked back in, and that sending mail is
warning-clean.
"""

import warnings

import pytest
from django.conf import settings
from django.core import mail
from django.core.mail import send_mail
from django.utils.deprecation import RemovedInDjango70Warning

# The names Django moved into MAILERS (mirrors django.conf.DEPRECATED_EMAIL_SETTINGS,
# copied here so the test does not import a name that itself disappears in 7.0).
DEPRECATED_EMAIL_SETTINGS = [
    "EMAIL_BACKEND",
    "EMAIL_FILE_PATH",
    "EMAIL_HOST",
    "EMAIL_HOST_PASSWORD",
    "EMAIL_HOST_USER",
    "EMAIL_PORT",
    "EMAIL_SSL_CERTFILE",
    "EMAIL_SSL_KEYFILE",
    "EMAIL_TIMEOUT",
    "EMAIL_USE_SSL",
    "EMAIL_USE_TLS",
]


def test_mailers_has_a_default_alias() -> None:
    assert hasattr(settings, "MAILERS")
    assert "default" in settings.MAILERS


@pytest.mark.parametrize("name", DEPRECATED_EMAIL_SETTINGS)
def test_deprecated_email_setting_is_unavailable(name: str) -> None:
    # With MAILERS defined, Django turns every deprecated EMAIL_* name into an
    # AttributeError instead of silently serving a global default — proof none
    # of them is still set anywhere in the settings chain.
    with pytest.raises(AttributeError):
        getattr(settings, name)


@pytest.mark.django_db
def test_send_mail_still_reaches_the_outbox_without_deprecation_warnings() -> None:
    mail.outbox.clear()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        send_mail(
            "subject",
            "body",
            settings.DEFAULT_FROM_EMAIL,
            ["someone@example.com"],
        )

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["someone@example.com"]

    mailers_warnings = [
        str(w.message)
        for w in caught
        if issubclass(w.category, RemovedInDjango70Warning)
    ]
    assert mailers_warnings == []
