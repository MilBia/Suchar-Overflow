#!/usr/bin/env python3
"""Detect a frozen `python:<tag>` base image (#445).

#431: astral's `uv:python3.14-bookworm-slim` tag silently stopped being rebuilt
and pinned the images to a leaking CPython 3.14.2. The Dockerfiles now take
Python from the official floating `python:3.14-slim-<debian>` tag (#437), which
docker-library could freeze the same way when it drops a Debian variant, and
Dependabot never proposes a bump for it. This script is the automated form of
the manual check CLAUDE.md used to describe; the `base-image-freshness`
workflow runs it weekly and opens an issue when it fails.

It needs the network (docker pull + endoflife.date), which is why it is not
part of `just test`; only its pure comparison logic is unit-tested there
(`tests/test_base_image_freshness.py`).

Exit codes: 0 fresh, 1 stale (the tag looks frozen), 2 the check itself could
not run (pull / inspect / API failure) — never a silent pass.
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "compose" / "production" / "django" / "Dockerfile"

# docker-library rebuilds every supported variant at least on each Debian point
# release and base-image security update, in practice every one to three weeks.
# Six weeks without a rebuild is well past that rhythm, yet short enough that a
# freeze is noticed long before it matters (#431 went unnoticed for months).
MAX_IMAGE_AGE = timedelta(days=42)
# A new 3.14.x usually lands in the official image within a day or two; a week
# of grace keeps the check quiet during a normal rollout.
RELEASE_GRACE = timedelta(days=7)

EOL_API = "https://endoflife.date/api/python/{cycle}.json"
HTTP_TIMEOUT = 30

EXIT_FRESH = 0
EXIT_STALE = 1
EXIT_ERROR = 2

_PYTHON_FROM_RE = re.compile(r"^FROM\s+python:(\S+)", re.MULTILINE)
_CYCLE_RE = re.compile(r"^(\d+\.\d+)")


class CheckError(Exception):
    """The freshness check could not be carried out."""


@dataclass(frozen=True)
class Verdict:
    stale: bool
    reasons: list[str]


def image_tag(dockerfile_text: str) -> str:
    """Return the single `python:` tag all FROM lines use, `@sha256` pin stripped."""
    tags = {tag.split("@", 1)[0] for tag in _PYTHON_FROM_RE.findall(dockerfile_text)}
    if len(tags) != 1:
        msg = f"expected exactly one python: base tag, found {sorted(tags)}"
        raise CheckError(msg)
    return tags.pop()


def release_cycle(tag: str) -> str:
    """`3.14-slim-trixie` -> `3.14`."""
    match = _CYCLE_RE.match(tag)
    if match is None:
        msg = f"cannot read a major.minor Python version from tag {tag!r}"
        raise CheckError(msg)
    return match.group(1)


def parse_version(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        msg = f"not a numeric version: {version!r}"
        raise CheckError(msg) from None


def evaluate(  # noqa: PLR0913
    *,
    created: datetime,
    python_version: str,
    latest: str,
    latest_release_date: datetime,
    now: datetime,
    max_age: timedelta = MAX_IMAGE_AGE,
    grace: timedelta = RELEASE_GRACE,
) -> Verdict:
    reasons: list[str] = []
    age = now - created
    if age > max_age:
        reasons.append(
            f"Obraz zbudowano {age.days} dni temu ({created:%Y-%m-%d}), "
            f"limit to {max_age.days} dni.",
        )
    if parse_version(python_version) < parse_version(latest):
        lag = now - latest_release_date
        if lag > grace:
            reasons.append(
                f"Obraz ma Pythona {python_version}, a {latest} jest dostępny "
                f"od {lag.days} dni ({latest_release_date:%Y-%m-%d}), "
                f"limit to {grace.days} dni.",
            )
    return Verdict(stale=bool(reasons), reasons=reasons)


def parse_timestamp(value: str) -> datetime:
    """Parse docker's RFC 3339 `Created` (nanoseconds) or an ISO date."""
    value = value.strip()
    # Python's fromisoformat takes at most microseconds.
    value = re.sub(r"(\.\d{6})\d+", r"\1", value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _run(*args: str) -> str:
    try:
        result = subprocess.run(  # noqa: S603
            args,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", "") or ""
        msg = f"`{' '.join(args)}` failed: {exc} {stderr.strip()}"
        raise CheckError(msg) from exc
    return result.stdout


def inspect_image(image: str) -> tuple[datetime, str]:
    _run("docker", "pull", "-q", image)
    raw = _run("docker", "image", "inspect", image)
    try:
        info = json.loads(raw)[0]
        created = parse_timestamp(info["Created"])
        env = dict(item.split("=", 1) for item in info["Config"]["Env"])
        python_version = env["PYTHON_VERSION"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        msg = f"unexpected `docker image inspect` output for {image}: {exc!r}"
        raise CheckError(msg) from exc
    return created, python_version


def fetch_latest(cycle: str) -> tuple[str, datetime]:
    url = EOL_API.format(cycle=cycle)
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:  # noqa: S310
            data = json.load(response)
        return data["latest"], parse_timestamp(data["latestReleaseDate"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        msg = f"cannot read {url}: {exc!r}"
        raise CheckError(msg) from exc


def build_report(  # noqa: PLR0913
    *,
    image: str,
    created: datetime,
    python_version: str,
    latest: str,
    latest_release_date: datetime,
    verdict: Verdict,
) -> str:
    status = "wygląda na **zamrożony**" if verdict.stale else "jest aktualny"
    lines = [
        f"Obraz bazowy `{image}` {status}.",
        "",
        f"- `Created`: {created:%Y-%m-%d %H:%M} UTC",
        f"- `PYTHON_VERSION`: {python_version}",
        (
            f"- najnowszy {release_cycle(image.split(':', 1)[1])}.x wg "
            f"endoflife.date: {latest} ({latest_release_date:%Y-%m-%d})"
        ),
    ]
    if verdict.stale:
        lines += ["", "Powody:", *(f"- {reason}" for reason in verdict.reasons)]
        lines += [
            "",
            (
                "Co zrobić: sprawdź, czy docker-library nadal buduje ten wariant "
                "Debiana. Jeśli nie, przenieś wszystkie trzy etapy `FROM python:` "
                "na kolejny codename naraz (jak w #437), a potem "
                "`just build --pull` i `just prod-build --pull`. Opis w "
                "CLAUDE.md (#431/#437/#445)."
            ),
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--report",
        type=Path,
        help="also write the markdown report to this file",
    )
    args = parser.parse_args(argv)

    def emit(text: str) -> None:
        sys.stdout.write(text)
        if args.report:
            args.report.write_text(text, encoding="utf-8")

    try:
        tag = image_tag(DOCKERFILE.read_text(encoding="utf-8"))
        image = f"python:{tag}"
        created, python_version = inspect_image(image)
        latest, latest_release_date = fetch_latest(release_cycle(tag))
        verdict = evaluate(
            created=created,
            python_version=python_version,
            latest=latest,
            latest_release_date=latest_release_date,
            now=datetime.now(tz=UTC),
        )
        report = build_report(
            image=image,
            created=created,
            python_version=python_version,
            latest=latest,
            latest_release_date=latest_release_date,
            verdict=verdict,
        )
    # Anything unexpected (an API field renamed, a version like "3.14.8rc1") is
    # "could not check" too: an uncaught traceback would exit 1, i.e. "stale",
    # and leave the workflow without a report for the issue.
    except Exception as exc:  # noqa: BLE001
        emit(
            "Nie udało się sprawdzić świeżości obrazu bazowego "
            f"(to nie jest wynik „aktualny”):\n\n```\n{exc!r}\n```\n",
        )
        return EXIT_ERROR

    emit(report)
    return EXIT_STALE if verdict.stale else EXIT_FRESH


if __name__ == "__main__":
    sys.exit(main())
