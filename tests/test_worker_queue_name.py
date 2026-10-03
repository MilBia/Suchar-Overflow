"""``compose/base/django/worker`` listens on the queue ``settings.RQ_QUEUE_NAME`` names (#500)."""

import os
import stat
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

WORKER_SCRIPT = Path(__file__).resolve().parent.parent / "compose" / "base" / "django" / "worker"


@pytest.fixture
def worker_argv(tmp_path: Path) -> Callable[..., list[str]]:
    """Run the worker script with a fake ``python`` on PATH that only prints its arguments."""
    fake = tmp_path / "python"
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

    def run(**env: str) -> list[str]:
        base = {"PATH": f"{tmp_path}:{os.environ['PATH']}"}
        result = subprocess.run(  # noqa: S603
            ["bash", str(WORKER_SCRIPT)],  # noqa: S607
            env={**base, **env},
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.splitlines()

    return run


def test_worker_defaults_to_the_default_queue(worker_argv: Callable[..., list[str]]) -> None:
    assert worker_argv() == ["manage.py", "rqworker", "--with-scheduler", "default"]


def test_worker_reads_the_queue_name_from_the_environment(worker_argv: Callable[..., list[str]]) -> None:
    assert worker_argv(DJANGO_RQ_QUEUE_NAME="suchary")[-1] == "suchary"


def test_worker_treats_an_empty_name_as_default(worker_argv: Callable[..., list[str]]) -> None:
    assert worker_argv(DJANGO_RQ_QUEUE_NAME="")[-1] == "default"
