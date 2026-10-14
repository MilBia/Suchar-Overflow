"""Guard: Dependabot's dedicated tool groups are excluded from the catch-all groups (#526).

ruff, djLint and prettier bumps also need a hand-made commit (the hook rev in
`.pre-commit-config.yaml`), so they get their own group and their PR may stay red
for a while. Relying on group order to keep them out of the catch-all group stopped
working once, and a Django CVE bump went red with them. The exclusion has to be explicit.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

_DEPENDABOT = Path(__file__).resolve().parent.parent / ".github" / "dependabot.yml"

# ecosystem -> (dedicated group, its catch-all group, packages the dedicated group must hold).
# Renaming a group in dependabot.yml means updating this table too.
GROUP_PAIRS = {
    "uv": ("lint-tools", "python", {"ruff", "djlint"}),
    "npm": ("prettier", "js-dev", {"prettier"}),
}


def _matches(name: str, pattern: str) -> bool:
    """Dependabot patterns support `*` only (no `?` or `[...]`), so don't use fnmatch."""
    return re.fullmatch(".*".join(map(re.escape, pattern.split("*"))), name) is not None


def _groups(ecosystem: str) -> dict[str, Any]:
    config = yaml.safe_load(_DEPENDABOT.read_text(encoding="utf-8"))
    assert isinstance(config, dict), "dependabot.yml is empty or not a mapping"
    updates = [u for u in config.get("updates") or [] if u.get("package-ecosystem") == ecosystem]
    assert len(updates) == 1, f"expected exactly one {ecosystem} block in dependabot.yml, found {len(updates)}"
    return updates[0].get("groups") or {}


@pytest.mark.parametrize(("ecosystem", "pair"), GROUP_PAIRS.items(), ids=list(GROUP_PAIRS))
def test_tool_group_is_excluded_from_catch_all(ecosystem: str, pair: tuple[str, str, set[str]]) -> None:
    tool_group, catch_all, expected_tools = pair
    groups = {name: body or {} for name, body in _groups(ecosystem).items()}
    assert {tool_group, catch_all} <= groups.keys(), f"{ecosystem}: groups {tool_group!r}/{catch_all!r} missing"
    tool_patterns = groups[tool_group].get("patterns") or []
    unheld = sorted(t for t in expected_tools if not any(_matches(t, p) for p in tool_patterns))
    assert not unheld, f"{ecosystem}: {tool_group!r} must hold {unheld}"
    excludes = groups[catch_all].get("exclude-patterns") or []
    missing = sorted(t for t in expected_tools if not any(_matches(t, p) for p in excludes))
    assert not missing, f"{ecosystem}: {catch_all!r} must exclude {missing} (they have their own group)"
