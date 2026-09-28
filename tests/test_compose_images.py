"""Static guards for the compose layout and image references (#456).

- Every image is named with its registry (`docker.io/...`, `ghcr.io/...`):
  podman does not assume Docker Hub for a short name the way Docker does.
- The stateful services report their health, and django waits for it
  (`condition: service_healthy`) instead of only for the containers to start.
- Redis persists to a volume, since the RQ queue (#460) will live in it.
- Production passes the optional `.envs/.secrets` before its own env files.

Only the files are read here; that the stack actually comes up healthy is
checked by hand (`just up` + `docker compose ps`).
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_COMPOSE_FILES = (
    _ROOT / "docker-compose.local.yml",
    _ROOT / "docker-compose.production.yml",
)
_DOCKERFILES = sorted((_ROOT / "compose").rglob("Dockerfile"))

# `FROM [--platform=...] <image> [AS <stage>]`
_FROM_RE = re.compile(r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", re.MULTILINE | re.IGNORECASE)


def _is_fully_qualified(image: str) -> bool:
    # A registry host is the first path component and contains a dot (or is
    # localhost / has a port); `python:3.14` or `library/python` has none.
    first, sep, _rest = image.partition("/")
    return bool(sep) and ("." in first or ":" in first or first == "localhost")


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_dockerfiles_are_found() -> None:
    names = {path.relative_to(_ROOT).as_posix() for path in _DOCKERFILES}
    assert {
        "compose/local/django/Dockerfile",
        "compose/production/django/Dockerfile",
        "compose/base/postgres/Dockerfile",
        "compose/production/traefik/Dockerfile",
        "compose/production/nginx/Dockerfile",
    } <= names


@pytest.mark.parametrize("dockerfile", _DOCKERFILES, ids=lambda p: p.relative_to(_ROOT).as_posix())
def test_dockerfile_base_images_name_their_registry(dockerfile: Path) -> None:
    stages: set[str] = set()
    for image, stage in _FROM_RE.findall(dockerfile.read_text(encoding="utf-8")):
        # `FROM python AS python-build-stage` builds on an earlier stage, not an image.
        if image not in stages:
            assert _is_fully_qualified(image), f"{dockerfile}: FROM {image} has no registry"
        if stage:
            stages.add(stage)


@pytest.mark.parametrize("compose_file", _COMPOSE_FILES, ids=lambda p: p.name)
def test_pulled_compose_images_name_their_registry(compose_file: Path) -> None:
    for name, service in _load(compose_file)["services"].items():
        # A built service's `image:` is only the local tag the build produces.
        if "build" not in service:
            assert _is_fully_qualified(service["image"]), f"{compose_file.name}: {name} image {service['image']}"


@pytest.mark.parametrize("compose_file", _COMPOSE_FILES, ids=lambda p: p.name)
def test_django_waits_for_healthy_backing_services(compose_file: Path) -> None:
    services = _load(compose_file)["services"]
    depends_on = services["django"]["depends_on"]
    assert isinstance(depends_on, dict), "use the long depends_on form with a condition"
    for dependency, spec in depends_on.items():
        assert "healthcheck" in services[dependency], f"{dependency} has no healthcheck"
        # .get: leaves room for `restart: true` / `required:` next to the condition.
        assert spec.get("condition") == "service_healthy", dependency


@pytest.mark.parametrize("compose_file", _COMPOSE_FILES, ids=lambda p: p.name)
def test_postgres_healthcheck_targets_the_configured_database(compose_file: Path) -> None:
    test = _load(compose_file)["services"]["postgres"]["healthcheck"]["test"]
    # `$$` so compose leaves the variables to the container's shell, which has
    # them from the env file; without -d pg_isready probes a DB named after the user.
    # -h 127.0.0.1 because the temporary server the image runs during initdb on a
    # fresh volume listens on the Unix socket only (`listen_addresses=''`): a socket
    # probe reports "accepting connections" before the real server is up.
    assert test == ["CMD-SHELL", "pg_isready -h 127.0.0.1 -d $${POSTGRES_DB} -U $${POSTGRES_USER}"]


@pytest.mark.parametrize("compose_file", _COMPOSE_FILES, ids=lambda p: p.name)
def test_postgres_builds_from_the_shared_base(compose_file: Path) -> None:
    build = _load(compose_file)["services"]["postgres"]["build"]
    assert build["dockerfile"] == "./compose/base/postgres/Dockerfile"


@pytest.mark.parametrize("compose_file", _COMPOSE_FILES, ids=lambda p: p.name)
def test_redis_persists_to_a_named_volume(compose_file: Path) -> None:
    config = _load(compose_file)
    redis = config["services"]["redis"]
    assert redis["command"] == "--save 60 1 --loglevel warning"
    volume, _, target = redis["volumes"][0].partition(":")
    assert target == "/data"
    assert volume in config["volumes"]
    assert redis["healthcheck"]["test"] == ["CMD", "redis-cli", "ping"]


def test_production_django_reads_optional_secrets_first() -> None:
    # .envs/.secrets is optional, and a later env_file overrides an earlier one, so
    # it comes first: .envs/.production/.django wins over it, as the OS environment
    # does over the file in base.py.
    env_files = _load(_ROOT / "docker-compose.production.yml")["services"]["django"]["env_file"]
    assert env_files[0] == {"path": "./.envs/.secrets", "required": False}
    assert "./.envs/.production/.django" in env_files[1:]
