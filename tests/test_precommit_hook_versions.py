"""Guard: pre-commit hook revs match the tool pins in pyproject.toml (#451).

pre-commit runs on the host from `.pre-commit-config.yaml` revs, while the
container (and anyone running `ruff`/`djlint` directly) uses the versions
pinned in the `dev` dependency group. When the two drift, the same file is
formatted differently depending on where the tool ran. django-upgrade's
--target-version is checked against the Django minor the same way, and the
prettier hook pin against package.json. Parsed as text so no YAML dependency
is needed.
"""

import json
import re
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_PRECOMMIT = _ROOT / ".pre-commit-config.yaml"
_PYPROJECT = _ROOT / "pyproject.toml"

# pyproject package name -> hook repo URL in .pre-commit-config.yaml.
HOOK_REPOS = {
    "ruff": "https://github.com/astral-sh/ruff-pre-commit",
    "djlint": "https://github.com/Riverside-Healthcare/djLint",
}


def _hook_rev(config: str, repo: str) -> str:
    match = re.search(
        rf"-\s+repo:\s+{re.escape(repo)}\s*\n\s+rev:\s+['\"]?v?([^'\"\s]+)",
        config,
    )
    assert match, f"no rev found for {repo} in .pre-commit-config.yaml"
    return match.group(1)


def _dev_pin(package: str) -> str:
    pyproject = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    for requirement in pyproject["dependency-groups"]["dev"]:
        name, sep, version = requirement.partition("==")
        if name.strip().lower() == package:
            assert sep, f"{package} is not pinned with == in pyproject.toml"
            return version.strip()
    pytest.fail(f"{package} missing from [dependency-groups].dev")


@pytest.mark.parametrize("package", sorted(HOOK_REPOS))
def test_precommit_hook_rev_matches_pyproject_pin(package: str) -> None:
    # .dockerignore keeps the config out of the image; the local/CI container
    # sees it through the bind mount.
    if not _PRECOMMIT.exists():
        pytest.skip(".pre-commit-config.yaml not present (image without bind mount)")
    config = _PRECOMMIT.read_text(encoding="utf-8")
    assert _hook_rev(config, HOOK_REPOS[package]) == _dev_pin(package), (
        f"{package}: bump the hook rev in .pre-commit-config.yaml and the pin in pyproject.toml together"
    )


def _django_minor() -> str:
    pyproject = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    for requirement in pyproject["project"]["dependencies"]:
        match = re.fullmatch(r"django\s*>=\s*(\d+\.\d+)\b.*", requirement.strip())
        if match:
            return match.group(1)
    pytest.fail("no `django>=X.Y` requirement in [project.dependencies]")


def test_django_upgrade_targets_the_pinned_django_minor() -> None:
    # A stale --target-version makes django-upgrade silently skip the rewrites
    # for the Django minor the project actually runs (#451 found it on 6.0).
    if not _PRECOMMIT.exists():
        pytest.skip(".pre-commit-config.yaml not present (image without bind mount)")
    config = _PRECOMMIT.read_text(encoding="utf-8")
    match = re.search(r"['\"]--target-version['\"],\s*['\"]([\d.]+)['\"]", config)
    assert match, "no django-upgrade --target-version in .pre-commit-config.yaml"
    assert match.group(1) == _django_minor()


def test_prettier_hook_pin_matches_package_json() -> None:
    # The hook installs prettier itself (additional_dependencies); the same
    # exact version in package.json is what lets Dependabot's npm ecosystem
    # notice a new release, so a bump has to move both pins together.
    package_json = _ROOT / "package.json"
    if not _PRECOMMIT.exists() or not package_json.exists():
        pytest.skip("pre-commit config or package.json not present (image without bind mount)")
    config = _PRECOMMIT.read_text(encoding="utf-8")
    match = re.search(r"additional_dependencies:\s*\[\s*['\"]prettier@([^'\"]+)['\"]", config)
    assert match, "no prettier@<version> in the prettier hook's additional_dependencies"
    dev_deps = json.loads(package_json.read_text(encoding="utf-8"))["devDependencies"]
    assert dev_deps.get("prettier") == match.group(1), (
        "prettier: bump the hook's additional_dependencies and package.json devDependencies together"
    )
