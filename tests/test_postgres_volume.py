"""Guards for the PostgreSQL volume layout (#464).

The data volume is mounted on `/var/lib/postgresql` (the cluster lives in `<major>/docker`), which is
what lets a future `pg_upgrade --link` (#174) work inside one volume. Mounting a volume of the old
layout there would make the image initialise a new, empty cluster, so `volume-guard` refuses to start.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_GUARD = _ROOT / "compose" / "base" / "postgres" / "volume-guard"
_COMPOSE = {
    "docker-compose.local.yml": "suchar_overflow_local_postgres_cluster",
    "docker-compose.production.yml": "production_postgres_cluster",
}


@pytest.mark.parametrize(("name", "volume"), _COMPOSE.items())
def test_postgres_volume_is_mounted_on_the_parent_directory(name: str, volume: str) -> None:
    compose = yaml.safe_load((_ROOT / name).read_text(encoding="utf-8"))
    mounts = compose["services"]["postgres"]["volumes"]
    assert f"{volume}:/var/lib/postgresql" in mounts
    assert volume in compose["volumes"]
    # The old volume's name must not be reused: attached to the new mount it would start an empty cluster.
    assert not any(v.endswith("_postgres_data") for v in compose["volumes"])


def test_dockerfile_installs_the_guard_as_entrypoint() -> None:
    dockerfile = (_ROOT / "compose" / "base" / "postgres" / "Dockerfile").read_text(encoding="utf-8")
    assert "volume-guard" in dockerfile
    assert 'ENTRYPOINT ["volume-guard"]' in dockerfile
    assert 'CMD ["postgres"]' in dockerfile


@pytest.fixture
def guard_env(tmp_path: Path) -> dict[str, str]:
    """A fake volume root and a stub `docker-entrypoint.sh` that records its arguments."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "docker-entrypoint.sh"
    stub.write_text('#!/usr/bin/env bash\necho "started $*"\n', encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    root = tmp_path / "postgresql"
    root.mkdir()
    return {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "PG_VOLUME_ROOT": str(root),
        "PGDATA": str(root / "18" / "docker"),
    }


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [str(_GUARD), "postgres"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_guard_starts_on_a_fresh_volume(guard_env: dict[str, str]) -> None:
    result = _run(guard_env)
    assert result.returncode == 0
    assert result.stdout.strip() == "started postgres"


def test_guard_passes_arguments_to_the_image_entrypoint(guard_env: dict[str, str]) -> None:
    result = subprocess.run(  # noqa: S603
        [str(_GUARD), "postgres", "-c", "fsync=on"],
        env=guard_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout.strip() == "started postgres -c fsync=on"


def test_guard_without_pgdata_defers_to_the_image_entrypoint(guard_env: dict[str, str]) -> None:
    del guard_env["PGDATA"]
    (Path(guard_env["PG_VOLUME_ROOT"]) / "PG_VERSION").write_text("18\n", encoding="utf-8")
    result = _run(guard_env)
    assert result.returncode == 0
    assert result.stdout.strip() == "started postgres"


def test_guard_starts_on_an_existing_cluster(guard_env: dict[str, str]) -> None:
    pgdata = Path(guard_env["PGDATA"])
    pgdata.mkdir(parents=True)
    (pgdata / "PG_VERSION").write_text("18\n", encoding="utf-8")
    assert _run(guard_env).returncode == 0


def test_guard_refuses_cluster_files_in_the_volume_root(guard_env: dict[str, str]) -> None:
    (Path(guard_env["PG_VOLUME_ROOT"]) / "PG_VERSION").write_text("18\n", encoding="utf-8")
    result = _run(guard_env)
    assert result.returncode == 1
    assert "started" not in result.stdout
    assert "Migracja wolumenu PostgreSQL" in result.stderr
