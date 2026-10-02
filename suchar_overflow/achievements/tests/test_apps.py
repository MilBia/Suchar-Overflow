import sys
from pathlib import Path

from django.apps import apps


def test_ready_registers_signals_and_starts_no_scheduler() -> None:
    """Since #462 the periodic jobs live in the `cron` service: a web process starts none."""
    config = apps.get_app_config("achievements")
    assert not hasattr(config, "_start_scheduler")
    assert "apscheduler" not in sys.modules


def test_apscheduler_is_not_a_dependency() -> None:
    root = Path(__file__).resolve().parents[3]
    assert "apscheduler" not in (root / "pyproject.toml").read_text()
