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
from pathlib import Path

import pytest
from django.conf import settings
from django.core import mail
from django.core.mail import send_mail
from django.utils.deprecation import RemovedInDjango70Warning

from tests.settings_loader import MINIMAL_ENV
from tests.settings_loader import load_base_settings

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

    mailers_warnings = [str(w.message) for w in caught if issubclass(w.category, RemovedInDjango70Warning)]
    assert mailers_warnings == []


# DJANGO_EMAIL_* with the legacy EMAIL_* fallback (#453)
# ------------------------------------------------------------------------------
# MAILERS is built once, in base.py; each case imports a throwaway copy of it
# (tests/settings_loader.py) under a fake environment.


def _mailer_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **environment: str) -> dict[str, object]:
    settings_module = load_base_settings(monkeypatch, tmp_path, {**MINIMAL_ENV, **environment})
    return settings_module.MAILERS["default"]["OPTIONS"]


def test_mailer_defaults_are_smtp_to_localhost(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert _mailer_options(monkeypatch, tmp_path) == {
        "host": "localhost",
        "port": 25,
        "username": "",
        "password": "",
        "use_tls": False,
        "use_ssl": False,
        "timeout": 5,
    }


_FULL_EMAIL_ENV = {
    "HOST": "smtp.example.com",
    "PORT": "587",
    "HOST_USER": "mailer",
    "HOST_PASSWORD": "s3cret",
    "USE_TLS": "True",
    "USE_SSL": "False",
    "TIMEOUT": "10",
}
_FULL_EMAIL_OPTIONS = {
    "host": "smtp.example.com",
    "port": 587,
    "username": "mailer",
    "password": "s3cret",
    "use_tls": True,
    "use_ssl": False,
    "timeout": 10,
}


def test_mailer_reads_django_email_vars(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = {f"DJANGO_EMAIL_{key}": value for key, value in _FULL_EMAIL_ENV.items()}
    assert _mailer_options(monkeypatch, tmp_path, **environment) == _FULL_EMAIL_OPTIONS


def test_mailer_falls_back_to_legacy_email_vars(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Pre-#453 production env files use the unprefixed names; they keep working
    # for one release (CHANGELOG.md).
    environment = {f"EMAIL_{key}": value for key, value in _FULL_EMAIL_ENV.items()}
    assert _mailer_options(monkeypatch, tmp_path, **environment) == _FULL_EMAIL_OPTIONS


def test_django_email_var_wins_over_legacy_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    options = _mailer_options(
        monkeypatch,
        tmp_path,
        DJANGO_EMAIL_HOST="new.example.com",
        EMAIL_HOST="old.example.com",
        EMAIL_PORT="2525",
    )
    assert options["host"] == "new.example.com"
    # Names are resolved one by one: a legacy PORT still fills in.
    assert options["port"] == 2525


def test_empty_email_var_counts_as_unset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # A blank line left behind while renaming EMAIL_* to DJANGO_EMAIL_* must
    # neither crash the settings import (int("")) nor shadow the legacy value.
    options = _mailer_options(
        monkeypatch,
        tmp_path,
        DJANGO_EMAIL_HOST="",
        EMAIL_HOST="smtp.old.example.com",
        DJANGO_EMAIL_PORT="",
        DJANGO_EMAIL_TIMEOUT="",
        EMAIL_USE_TLS="",
    )
    assert options["host"] == "smtp.old.example.com"
    assert options["port"] == 25
    assert options["timeout"] == 5
    assert options["use_tls"] is False


@pytest.mark.parametrize("backend", [None, ""])
def test_unset_or_empty_email_backend_is_smtp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    backend: str | None,
) -> None:
    # An empty DJANGO_EMAIL_BACKEND= would import as BACKEND "" and only fail at
    # send time (InvalidMailer) — for mail_admins, silently.
    environment = {**MINIMAL_ENV} if backend is None else {**MINIMAL_ENV, "DJANGO_EMAIL_BACKEND": backend}
    settings_module = load_base_settings(monkeypatch, tmp_path, environment)
    assert settings_module.MAILERS["default"]["BACKEND"] == "django.core.mail.backends.smtp.EmailBackend"


def test_email_backend_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    backend = "django.core.mail.backends.console.EmailBackend"
    settings_module = load_base_settings(monkeypatch, tmp_path, {**MINIMAL_ENV, "DJANGO_EMAIL_BACKEND": backend})
    assert settings_module.MAILERS["default"]["BACKEND"] == backend


def test_local_env_file_points_mail_at_mailpit() -> None:
    # local.py no longer carries a MAILERS of its own (#453); the mailpit
    # host/port are data in .envs/.local/.django.
    env_file = Path(__file__).resolve().parent.parent / ".envs" / ".local" / ".django"
    lines = env_file.read_text().splitlines()
    assert "DJANGO_EMAIL_HOST=mailpit" in lines
    assert "DJANGO_EMAIL_PORT=1025" in lines
