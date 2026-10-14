"""Guard: Dependabot's dedicated tool groups are excluded from the catch-all groups (#526).

ruff, djLint and prettier bumps also need a hand-made commit (the hook rev in
`.pre-commit-config.yaml`), so they get their own group and their PR may stay red
for a while. Relying on group order to keep them out of the catch-all group stopped
working once, and a Django CVE bump went red with them. The exclusion has to be explicit.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

_DEPENDABOT = Path(__file__).resolve().parent.parent / ".github" / "dependabot.yml"

# ecosystem -> (dedicated group, its catch-all group)
GROUP_PAIRS = {
    "uv": ("lint-tools", "python"),
    "npm": ("prettier", "js-dev"),
}


def _groups(ecosystem: str) -> dict[str, Any]:
    config = yaml.safe_load(_DEPENDABOT.read_text(encoding="utf-8"))
    updates = [u for u in config["updates"] if u["package-ecosystem"] == ecosystem]
    assert len(updates) == 1, f"expected exactly one {ecosystem} block in dependabot.yml, found {len(updates)}"
    return updates[0].get("groups", {})


@pytest.mark.parametrize(("ecosystem", "pair"), GROUP_PAIRS.items(), ids=list(GROUP_PAIRS))
def test_tool_group_is_excluded_from_catch_all(ecosystem: str, pair: tuple[str, str]) -> None:
    tool_group, catch_all = pair
    groups = _groups(ecosystem)
    assert {tool_group, catch_all} <= groups.keys(), f"{ecosystem}: groups {tool_group!r}/{catch_all!r} missing"
    tools = set(groups[tool_group].get("patterns", []))
    assert tools, f"{ecosystem}: group {tool_group!r} has no patterns, so the check would pass vacuously"
    excluded = set(groups[catch_all].get("exclude-patterns", []))
    missing = sorted(tools - excluded)
    assert not missing, f"{catch_all} must exclude {missing} (they have their own group)"
