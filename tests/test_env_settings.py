"""Env-var conventions of ``config/settings/base.py`` (#453).

* ``DATABASES`` comes from ``DATABASE_URL`` when it is present (even empty — the
  production image's build-time ``compilemessages`` sets it to ``""``), otherwise
  from ``POSTGRES_*``, URL-encoded like the entrypoint does (#356). This is what
  lets ``docker compose exec django python manage.py …`` work without
  ``/entrypoint`` (the #404 workaround it replaces).
* ``ADMINS`` / ``MANAGERS`` come from ``DJANGO_ADMINS``.
* ``DJANGO_STATIC_ROOT`` overrides ``STATIC_ROOT``.
* ``.envs/.secrets`` is loaded when it exists; the OS environment wins.
* ``REDIS_URL`` has no default.

Each case imports a throwaway copy of ``base.py`` (``tests/settings_loader.py``),
so the live settings and ``os.environ`` are never touched.
"""

import warnings

# Real import (not TYPE_CHECKING-guarded): kept plain to match every other test
# module; only referenced in annotations.
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

import pytest
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import mail_admins
from django.utils.deprecation import RemovedInDjango70Warning

from tests.settings_loader import MINIMAL_ENV
from tests.settings_loader import load_base_settings

if TYPE_CHECKING:
    from pytest_django.fixtures import Settings as SettingsWrapper

_POSTGRES_ENV = {
    "POSTGRES_HOST": "postgres",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "suchar_overflow",
    "POSTGRES_USER": "suchar_overflow",
    "POSTGRES_PASSWORD": "suchar_overflow",
}
_REDIS_ONLY = {"REDIS_URL": MINIMAL_ENV["REDIS_URL"]}


# DATABASES
# ------------------------------------------------------------------------------


def test_dsn_is_built_from_postgres_vars_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_base_settings(monkeypatch, tmp_path, {**_REDIS_ONLY, **_POSTGRES_ENV})
    db = settings.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert db["HOST"] == "postgres"
    assert db["PORT"] == 5432
    assert db["NAME"] == "suchar_overflow"
    assert db["USER"] == "suchar_overflow"
    assert db["PASSWORD"] == _POSTGRES_ENV["POSTGRES_PASSWORD"]
    # base.py's own CONN_MAX_AGE (#430) still applies to the assembled DSN.
    assert db["CONN_MAX_AGE"] == 0


def test_dsn_survives_special_characters_in_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Every URL delimiter that would break an unencoded DSN.
    password = "p@ss:w/o#r?d%&=+ "  # noqa: S105
    settings = load_base_settings(
        monkeypatch,
        tmp_path,
        {
            **_REDIS_ONLY,
            **_POSTGRES_ENV,
            "POSTGRES_USER": "us@er:x",
            "POSTGRES_PASSWORD": password,
            "POSTGRES_DB": "db/name#1",
        },
    )
    db = settings.DATABASES["default"]
    assert db["USER"] == "us@er:x"
    assert db["PASSWORD"] == password
    assert db["NAME"] == "db/name#1"
    assert db["HOST"] == "postgres"
    assert db["PORT"] == 5432


def test_postgres_user_defaults_like_the_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = {**_REDIS_ONLY, **_POSTGRES_ENV}
    del environment["POSTGRES_USER"]
    settings = load_base_settings(monkeypatch, tmp_path, environment)
    assert settings.DATABASES["default"]["USER"] == "postgres"


def test_database_url_takes_precedence_over_postgres_vars(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_base_settings(
        monkeypatch,
        tmp_path,
        {
            **_POSTGRES_ENV,
            "REDIS_URL": MINIMAL_ENV["REDIS_URL"],
            "DATABASE_URL": "postgres://other:secret@dbhost:6543/otherdb",
        },
    )
    db = settings.DATABASES["default"]
    assert db["HOST"] == "dbhost"
    assert db["PORT"] == 6543
    assert db["NAME"] == "otherdb"
    assert db["USER"] == "other"


def test_database_url_alone_needs_no_postgres_vars(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # CI's mypy job passes only DATABASE_URL=sqlite:///:memory: (#453).
    settings = load_base_settings(
        monkeypatch,
        tmp_path,
        {**_REDIS_ONLY, "DATABASE_URL": "sqlite:///:memory:"},
    )
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"


# An empty URL parses to an engine-less config; environ warns, and nothing
# connects at build time anyway.
@pytest.mark.filterwarnings("ignore:Engine not recognized from url")
def test_empty_database_url_still_skips_postgres_vars(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # compose/production/django/Dockerfile runs compilemessages with
    # DATABASE_URL="" and no POSTGRES_* at build time.
    load_base_settings(monkeypatch, tmp_path, {"DATABASE_URL": "", "REDIS_URL": ""})


def test_missing_database_config_names_the_missing_variable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(ImproperlyConfigured, match="POSTGRES_"):
        load_base_settings(monkeypatch, tmp_path, _REDIS_ONLY)


# REDIS_URL
# ------------------------------------------------------------------------------


def test_redis_url_has_no_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(ImproperlyConfigured, match="REDIS_URL"):
        load_base_settings(monkeypatch, tmp_path, {"DATABASE_URL": MINIMAL_ENV["DATABASE_URL"]})


# REDIS_QUEUE_URL / RQ_QUEUES (#460)
# ------------------------------------------------------------------------------


def test_queue_url_defaults_to_database_1_of_redis_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env = {**MINIMAL_ENV, "REDIS_URL": "redis://:s3cret@cache.example:6380/0"}
    env.pop("REDIS_QUEUE_URL", None)
    settings = load_base_settings(monkeypatch, tmp_path, env)
    # Same host, port and credentials; only the database differs, so a cache flush spares the queue.
    assert settings.REDIS_QUEUE_URL == "redis://:s3cret@cache.example:6380/1"
    assert settings.RQ_QUEUES["default"]["URL"] == settings.REDIS_QUEUE_URL
    assert "SSL_CERT_REQS" not in settings.RQ_QUEUES["default"]


def test_explicit_queue_url_wins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_base_settings(monkeypatch, tmp_path, {**MINIMAL_ENV, "REDIS_QUEUE_URL": "redis://queue:6379/5"})
    assert settings.REDIS_QUEUE_URL == "redis://queue:6379/5"
    assert settings.RQ_QUEUES["default"]["URL"] == "redis://queue:6379/5"


def test_tls_queue_url_does_not_verify_certificates_like_the_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_base_settings(monkeypatch, tmp_path, {**MINIMAL_ENV, "REDIS_URL": "rediss://cache.example:6380/0"})
    assert settings.REDIS_QUEUE_URL == "rediss://cache.example:6380/1"
    assert settings.RQ_QUEUES["default"]["SSL_CERT_REQS"] is None


# ADMINS / MANAGERS
# ------------------------------------------------------------------------------


def test_admins_default_to_nobody(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_base_settings(monkeypatch, tmp_path, MINIMAL_ENV)
    assert settings.ADMINS == []
    assert settings.MANAGERS == []


def test_admins_come_from_django_admins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_base_settings(
        monkeypatch,
        tmp_path,
        {**MINIMAL_ENV, "DJANGO_ADMINS": "Jan Kowalski <jan@example.com>,ops@example.com"},
    )
    assert settings.ADMINS == ["Jan Kowalski <jan@example.com>", "ops@example.com"]
    assert settings.MANAGERS == settings.ADMINS


@pytest.mark.parametrize(
    "raw",
    [
        "Jan Kowalski <jan@example.com>,ops@example.com",
        # The natural hand-written form, with a space after the comma.
        "Jan Kowalski <jan@example.com>, ops@example.com",
        # A trailing ", " used to leave a " " entry that made every send raise.
        "Jan Kowalski <jan@example.com>, ops@example.com, ",
        "  Jan Kowalski <jan@example.com> ,, ops@example.com ,",
    ],
)
def test_admins_from_env_are_what_mail_admins_expects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: SettingsWrapper,
    raw: str,
) -> None:
    """Django 6.x wants plain address strings (``(name, address)`` pairs are
    deprecated); a ``Name <mail>`` string is delivered as-is, warning-free.
    Whitespace around entries and blank entries are dropped."""
    loaded = load_base_settings(monkeypatch, tmp_path, {**MINIMAL_ENV, "DJANGO_ADMINS": raw})
    assert loaded.ADMINS == ["Jan Kowalski <jan@example.com>", "ops@example.com"]
    settings.ADMINS = loaded.ADMINS
    mail.outbox.clear()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mail_admins("subject", "body")

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["Jan Kowalski <jan@example.com>", "ops@example.com"]
    assert [w for w in caught if issubclass(w.category, RemovedInDjango70Warning)] == []


# STATIC_ROOT
# ------------------------------------------------------------------------------


def test_static_root_defaults_under_base_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_base_settings(monkeypatch, tmp_path, MINIMAL_ENV)
    assert str(tmp_path / "staticfiles") == settings.STATIC_ROOT


def test_static_root_is_overridable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_base_settings(
        monkeypatch,
        tmp_path,
        {**MINIMAL_ENV, "DJANGO_STATIC_ROOT": "/srv/static"},
    )
    assert settings.STATIC_ROOT == "/srv/static"


# .envs/.secrets
# ------------------------------------------------------------------------------


def test_secrets_file_is_loaded_when_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_base_settings(
        monkeypatch,
        tmp_path,
        MINIMAL_ENV,
        secrets="DJANGO_ADMINS=secret-admin@example.com\nFEEDBACK_URL=https://example.com/feedback\n",
    )
    assert settings.ADMINS == ["secret-admin@example.com"]
    assert settings.FEEDBACK_URL == "https://example.com/feedback"


def test_secrets_file_can_supply_required_variables(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Loaded before anything else is read, so even REDIS_URL may live there.
    settings = load_base_settings(
        monkeypatch,
        tmp_path,
        {"DATABASE_URL": MINIMAL_ENV["DATABASE_URL"]},
        secrets="REDIS_URL=redis://from-secrets:6379/1\n",
    )
    assert settings.REDIS_URL == "redis://from-secrets:6379/1"


def test_os_environment_wins_over_secrets_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_base_settings(
        monkeypatch,
        tmp_path,
        {**MINIMAL_ENV, "DJANGO_ADMINS": "from-env@example.com"},
        secrets="DJANGO_ADMINS=from-secrets@example.com\n",
    )
    assert settings.ADMINS == ["from-env@example.com"]


def test_missing_secrets_file_is_fine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_base_settings(monkeypatch, tmp_path, MINIMAL_ENV)
    assert not settings.SECRETS_ENV_FILE.exists()
    assert settings.ADMINS == []


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({}, True),
        ({"DJANGO_API_ENABLE_DOCS": "False"}, False),
        ({"API_ENABLE_DOCS": "False"}, False),  # legacy name, one release
        ({"DJANGO_API_ENABLE_DOCS": "True", "API_ENABLE_DOCS": "False"}, True),  # prefixed wins
    ],
)
def test_api_enable_docs_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    environment: dict[str, str],
    expected: bool,  # noqa: FBT001
) -> None:
    module = load_base_settings(monkeypatch, tmp_path, {**MINIMAL_ENV, **environment})
    assert module.API_ENABLE_DOCS is expected
