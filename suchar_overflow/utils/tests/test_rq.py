"""RQ plumbing (#460): settings, healthcheck command, final-failure reporting."""

import logging
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from suchar_overflow.utils.rq_handlers import mail_admins_on_final_failure

if TYPE_CHECKING:
    from django.test import Client

SMTP_DOWN = "smtp down"
_CMD = "suchar_overflow.utils.management.commands.rq_healthcheck"


def test_queue_settings() -> None:
    assert list(settings.RQ_QUEUES) == [settings.RQ_QUEUE_NAME]
    assert "django_rq" in settings.INSTALLED_APPS
    queue = settings.RQ_QUEUES[settings.RQ_QUEUE_NAME]
    assert queue["URL"] == settings.REDIS_QUEUE_URL
    # Its own Redis database: flushing the cache must not delete the queue.
    assert settings.REDIS_QUEUE_URL != settings.REDIS_URL
    assert queue["DEFAULT_TIMEOUT"] <= 15 * 60


def test_admin_has_the_rq_dashboard(admin_client: Client) -> None:
    url = reverse("django_rq:home")
    assert url.startswith(f"/{settings.ADMIN_URL}django-rq/")
    # admin.site.urls must not shadow it with its catch-all 404.
    with patch("django_rq.stats_views.get_statistics", return_value={"queues": [], "schedulers": {}}):
        assert admin_client.get(url).status_code != HTTPStatus.NOT_FOUND


def test_dashboard_requires_staff(client: Client) -> None:
    assert client.get(reverse("django_rq:home")).status_code == HTTPStatus.FOUND


# --- rq_healthcheck ----------------------------------------------------------


def test_healthcheck_passes_when_every_queue_has_a_worker() -> None:
    with patch(f"{_CMD}.Worker") as worker:
        worker.count.return_value = 1
        call_command("rq_healthcheck")


def test_healthcheck_fails_when_a_queue_has_no_worker() -> None:
    with patch(f"{_CMD}.Worker") as worker:
        worker.count.return_value = 0
        with pytest.raises(CommandError, match=settings.RQ_QUEUE_NAME):
            call_command("rq_healthcheck")


def test_healthcheck_fails_when_redis_is_unreachable() -> None:
    with patch(f"{_CMD}.Worker") as worker:
        worker.count.side_effect = ConnectionError("down")
        with pytest.raises(CommandError, match="could not reach"):
            call_command("rq_healthcheck")


def _scheduler(age_seconds: float | None) -> MagicMock:
    scheduler = MagicMock()
    scheduler.last_heartbeat = None if age_seconds is None else timezone.now() - timedelta(seconds=age_seconds)
    return scheduler


def test_cron_healthcheck_passes_with_a_fresh_heartbeat() -> None:
    with patch(f"{_CMD}.CronScheduler") as cron:
        cron.all.return_value = [_scheduler(30)]
        call_command("rq_healthcheck", "--cron")


@pytest.mark.parametrize("schedulers", [[], [_scheduler(None)], [_scheduler(900)]])
def test_cron_healthcheck_fails_without_a_fresh_heartbeat(schedulers: list[MagicMock]) -> None:
    with patch(f"{_CMD}.CronScheduler") as cron:
        cron.all.return_value = schedulers
        with pytest.raises(CommandError, match="heartbeat"):
            call_command("rq_healthcheck", "--cron")


# --- final-failure handler -----------------------------------------------------


def _job(*, should_retry: bool) -> MagicMock:
    job = MagicMock(id="abc", func_name="suchar_overflow.users.tasks.send_activation_email")
    job.should_retry = should_retry
    return job


def test_exhausted_job_is_logged_to_the_django_logger(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="django.rq"):
        try:
            raise OSError(SMTP_DOWN)  # noqa: TRY301
        except OSError as exc:
            result = mail_admins_on_final_failure(_job(should_retry=False), type(exc), exc, exc.__traceback__)
    assert result is True
    assert "failed permanently" in caplog.text
    assert "smtp down" in caplog.text  # the traceback travels with the record
    assert logging.getLogger("django.rq").parent is logging.getLogger("django")


def test_attempt_with_retries_left_is_not_reported(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="django.rq"):
        result = mail_admins_on_final_failure(_job(should_retry=True), OSError, OSError("x"), None)
    assert result is True
    assert caplog.text == ""
