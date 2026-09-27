"""Regression guards for the Django images' Python base (#431, #437).

CPython 3.14.0-3.14.4 shipped an incremental cycle collector that was reverted
in 3.14.5. Every Django ASGI request leaves its request graph (request, session,
messages storage, resolver match, ...) in a reference cycle that only the cycle
collector frees, and the incremental collector fell behind that rate: under
sustained load the uvicorn worker's RSS grew without bound (measured 135 ->
270 MB over 8 rounds on 3.14.2 with `config.settings.production`, flat ~101 MB
on 3.14.7 with the same load).

The image stayed on 3.14.2 because astral's `uv:python3.14-bookworm-slim` tag
stopped being rebuilt; the Dockerfiles now take Python from the official
`python:3.14-slim-<debian>` image instead (trixie since #437). The runtime tests
run in the local/CI image only, so they catch a stale cached base image or a
switch back to a frozen tag there. The production image is not covered and
needs `just prod-build --pull`.
"""

import re
import sys
from pathlib import Path

import pytest

_FIRST_FIXED = (3, 14, 5)

_COMPOSE_DIR = Path(__file__).resolve().parent.parent / "compose"
DOCKERFILES = (
    _COMPOSE_DIR / "local" / "django" / "Dockerfile",
    _COMPOSE_DIR / "production" / "django" / "Dockerfile",
)
_OS_RELEASE = Path("/etc/os-release")

_PYTHON_FROM_RE = re.compile(r"^FROM\s+(python:\S+)", re.MULTILINE)


def _python_base_images() -> list[str]:
    images: list[str] = []
    for dockerfile in DOCKERFILES:
        images += _PYTHON_FROM_RE.findall(dockerfile.read_text(encoding="utf-8"))
    return images


def test_python_is_not_an_incremental_gc_release() -> None:
    # pyproject pins requires-python to 3.14.x. (3.15 prereleases had it too and
    # got the same revert, but no 3.15 interpreter can run this project.)
    assert sys.version_info[:3] >= _FIRST_FIXED, (
        f"Python {sys.version.split()[0]} has the incremental GC reverted in "
        "3.14.5 (#431); rebuild the image with a fresh base: `just build --pull`"
    )


def test_all_django_image_stages_share_one_python_base() -> None:
    # The production build stage compiles the venv (C extensions, bytecode) that
    # the run stage executes; different Debian releases would mean different
    # glibc versions between them (#437). The local image uses the same tag so
    # the unit/E2E suites run on what production ships.
    images = _python_base_images()
    # local: 1 alias stage; production: build + run stage.
    assert len(images) == 3, images
    assert len(set(images)) == 1, f"Python base images differ: {images}"


def _os_release() -> dict[str, str]:
    if not _OS_RELEASE.exists():
        return {}
    fields: dict[str, str] = {}
    for line in _OS_RELEASE.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key] = value.strip('"')
    return fields


def test_image_runs_the_debian_release_its_dockerfile_names() -> None:
    # A plain `just build` reuses a cached base, so switching the tag's Debian
    # release (bookworm -> trixie in #437) does not reach an existing image
    # until `just build --pull`. Only meaningful inside the Django image; any
    # other Linux host has an os-release too, just not a Debian one.
    os_release = _os_release()
    if os_release.get("ID") != "debian":
        pytest.skip("not running in the Debian-based Django image")
    codename = os_release.get("VERSION_CODENAME")
    assert codename, "/etc/os-release has no VERSION_CODENAME"
    # Drop a digest pin (`python:3.14-slim-trixie@sha256:...`) before taking the
    # tag's trailing `-<codename>`.
    tag = _python_base_images()[0].split("@", 1)[0]
    expected = tag.rsplit("-", 1)[-1]
    assert codename == expected, (
        f"image runs Debian {codename}, Dockerfile names {expected}; rebuild with a fresh base: `just build --pull`"
    )
