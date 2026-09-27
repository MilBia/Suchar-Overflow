"""Unit tests for the frozen base image check (#445).

The script itself needs the network and runs weekly in
`.github/workflows/base-image-freshness.yml`; here only its pure logic and its
"never silently pass" error path are exercised.
"""

import importlib.util
import sys
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_base_image_freshness.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_base_image_freshness", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve the module through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


freshness = _load()

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _pinned_clock_no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    # main() judges the stubbed Created/release dates against "now"; a real
    # clock would turn fresh stubs stale once they age past MAX_IMAGE_AGE.
    monkeypatch.setattr(freshness, "_now", lambda: NOW)
    monkeypatch.setattr(freshness, "RETRY_DELAY", timedelta(0))


def _evaluate(
    *,
    created_days_ago: int = 3,
    python_version: str = "3.14.7",
    latest: str = "3.14.7",
    released_days_ago: int = 50,
) -> tuple[bool, list[str]]:
    verdict = freshness.evaluate(
        created=NOW - timedelta(days=created_days_ago),
        python_version=python_version,
        latest=latest,
        latest_release_date=NOW - timedelta(days=released_days_ago),
        now=NOW,
    )
    return verdict.stale, verdict.reasons


def test_fresh_image_passes() -> None:
    assert _evaluate() == (False, [])


def test_old_image_is_stale() -> None:
    stale, reasons = _evaluate(created_days_ago=43)
    assert stale
    assert len(reasons) == 1


def test_image_just_within_age_limit_passes() -> None:
    assert not _evaluate(created_days_ago=42)[0]


def test_python_behind_latest_past_grace_is_stale() -> None:
    stale, reasons = _evaluate(python_version="3.14.6", released_days_ago=8)
    assert stale
    assert "3.14.6" in reasons[0]


def test_python_behind_latest_within_grace_passes() -> None:
    assert not _evaluate(python_version="3.14.6", released_days_ago=6)[0]


def test_both_reasons_reported() -> None:
    _, reasons = _evaluate(created_days_ago=100, python_version="3.14.2")
    assert len(reasons) == 2


def test_versions_compare_numerically() -> None:
    assert freshness.parse_version("3.14.10") > freshness.parse_version("3.14.9")
    assert not _evaluate(python_version="3.14.10", latest="3.14.9")[0]


def test_image_tag_strips_digest_pin() -> None:
    text = "FROM python:3.14-slim-trixie@sha256:abc AS build\nFROM python:3.14-slim-trixie AS run\n"
    assert freshness.image_tag(text) == "3.14-slim-trixie"


def test_image_tag_rejects_mismatched_stages() -> None:
    text = "FROM python:3.14-slim-trixie\nFROM python:3.14-slim-bookworm\n"
    with pytest.raises(freshness.CheckError):
        freshness.image_tag(text)


def test_image_tag_rejects_missing_python_stage() -> None:
    with pytest.raises(freshness.CheckError):
        freshness.image_tag("FROM debian:trixie\n")


def test_repo_dockerfile_tag() -> None:
    text = freshness.DOCKERFILE.read_text(encoding="utf-8")
    # The codename is test_python_runtime.py's business; a Debian move (#437)
    # shouldn't have to touch this test as well.
    assert freshness.release_cycle(freshness.image_tag(text)) == "3.14"


def test_parse_timestamp_handles_docker_nanoseconds() -> None:
    parsed = freshness.parse_timestamp("2026-09-19T01:03:24.123456789Z")
    assert parsed == datetime(2026, 9, 19, 1, 3, 24, 123456, tzinfo=UTC)
    assert freshness.parse_timestamp("2026-08-05").tzinfo is UTC


def test_check_failure_is_not_a_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken_run(*args: str) -> str:
        msg = f"{args} failed"
        raise freshness.CheckError(msg)

    monkeypatch.setattr(freshness, "_run", broken_run)
    report = tmp_path / "report.md"
    assert freshness.main(["--report", str(report)]) == freshness.EXIT_ERROR
    assert "Nie udało się" in capsys.readouterr().out
    assert "Nie udało się" in report.read_text(encoding="utf-8")


def _fresh_image(_image: str) -> tuple[datetime, str]:
    return datetime(2026, 9, 19, tzinfo=UTC), "3.14.7"


def _latest(_cycle: str) -> tuple[str, datetime]:
    return "3.14.7", datetime(2026, 8, 5, tzinfo=UTC)


def test_unexpected_error_is_not_a_pass_either(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Not a CheckError: without main()'s catch-all it would escape as a
    # traceback, exit 1 ("stale") and leave no report for the issue step.
    def broken_fetch(_cycle: str) -> tuple[str, datetime]:
        msg = "unexpected"
        raise RuntimeError(msg)

    monkeypatch.setattr(freshness, "inspect_image", _fresh_image)
    monkeypatch.setattr(freshness, "fetch_latest", broken_fetch)
    report = tmp_path / "report.md"
    assert freshness.main(["--report", str(report)]) == freshness.EXIT_ERROR
    text = report.read_text(encoding="utf-8")
    assert "Nie udało się" in text
    assert "RuntimeError" in text


def test_unparsable_python_version_is_not_a_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # evaluate() raises CheckError for a pre-release it can't compare; it must
    # run inside main()'s try, not after it.
    monkeypatch.setattr(
        freshness,
        "inspect_image",
        lambda _image: (datetime(2026, 9, 19, tzinfo=UTC), "3.14.8rc1"),
    )
    monkeypatch.setattr(freshness, "fetch_latest", _latest)
    report = tmp_path / "report.md"
    assert freshness.main(["--report", str(report)]) == freshness.EXIT_ERROR
    assert "Nie udało się" in report.read_text(encoding="utf-8")


def test_transient_failure_is_retried_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def flaky_fetch(cycle: str) -> tuple[str, datetime]:
        calls.append(cycle)
        if len(calls) == 1:
            msg = "blip"
            raise freshness.CheckError(msg)
        return _latest(cycle)

    monkeypatch.setattr(freshness, "inspect_image", _fresh_image)
    monkeypatch.setattr(freshness, "fetch_latest", flaky_fetch)
    assert freshness.main([]) == freshness.EXIT_FRESH
    assert calls == ["3.14", "3.14"]


def test_persistent_failure_gives_up_after_the_retry() -> None:
    calls: list[str] = []

    def broken(arg: str) -> str:
        calls.append(arg)
        msg = "down"
        raise freshness.CheckError(msg)

    with pytest.raises(freshness.CheckError):
        freshness.with_retry(broken, "x")
    assert len(calls) == freshness.ATTEMPTS


def test_max_age_zero_forces_a_stale_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    # The workflow's force_stale input: exercises the issue path on a fresh image.
    monkeypatch.setattr(freshness, "inspect_image", _fresh_image)
    monkeypatch.setattr(freshness, "fetch_latest", _latest)
    assert freshness.main([]) == freshness.EXIT_FRESH
    assert freshness.main(["--max-age-days", "0"]) == freshness.EXIT_STALE


def test_stale_result_exits_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        freshness,
        "inspect_image",
        lambda _image: (datetime(2020, 1, 1, tzinfo=UTC), "3.14.2"),
    )
    monkeypatch.setattr(
        freshness,
        "fetch_latest",
        lambda _cycle: ("3.14.7", datetime(2026, 8, 5, tzinfo=UTC)),
    )
    assert freshness.main([]) == freshness.EXIT_STALE
