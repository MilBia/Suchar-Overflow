"""A responsive utility's name must match the breakpoint of the `@media` block it sits in (#508).

`.justify-content-lg-end` lived in a `min-width: 768px` block, so it applied from `md` while its name
said `lg`. Same class of bug as `.flex-lg-grow-0` (#503). `col-*` rules in `_layout.scss` have a base
rule outside `@media` (the mobile layout) and are not covered by this check.
"""

import re
from pathlib import Path

_SCSS = Path(__file__).resolve().parent.parent / "webpack/src/scss"
_BREAKPOINTS = {"sm": 576, "md": 768, "lg": 992, "xl": 1200, "xxl": 1400}
_MEDIA_RE = re.compile(r"@media\s*\(min-width:\s*(\d+)px\)\s*\{")
_CLASS_RE = re.compile(r"\.([A-Za-z][\w-]*?)-(sm|md|lg|xl|xxl)(?=[-\s,{:.>+~\[]|$)")


def _strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def _media_blocks(text: str) -> list[tuple[int, str]]:
    """Return (min-width px, block body) for every `@media (min-width: Npx)` block."""
    blocks = []
    for match in _MEDIA_RE.finditer(text):
        depth, pos = 1, match.end()
        while depth:
            char = text[pos]
            depth += (char == "{") - (char == "}")
            pos += 1
        blocks.append((int(match.group(1)), text[match.end() : pos - 1]))
    return blocks


def _selectors(body: str) -> list[str]:
    # Selector text is whatever precedes each `{`.
    return [chunk.rsplit("}", 1)[-1] for chunk in body.split("{")[:-1]]


def _block_mismatches(text: str, label: str) -> list[str]:
    found = []
    for min_width, body in _media_blocks(_strip_comments(text)):
        for selector in _selectors(body):
            for match in _CLASS_RE.finditer(selector):
                infix = match.group(2)
                if _BREAKPOINTS[infix] != min_width:
                    found.append(f"{label}: .{match.group(1)}-{infix} in min-width {min_width}px")
    return found


def _mismatches() -> list[str]:
    return [
        line
        for path in sorted(_SCSS.rglob("*.scss"))
        for line in _block_mismatches(path.read_text(encoding="utf-8"), str(path.relative_to(_SCSS)))
    ]


def test_responsive_class_infix_matches_media_breakpoint() -> None:
    assert _mismatches() == []


def test_checker_flags_a_mismatched_block() -> None:
    # Negative control for the real test: `-lg-` inside a 768px block must be reported.
    css = "@media (min-width: 768px) { .justify-content-lg-end { a: b } }"
    assert _block_mismatches(css, "x") == ["x: .justify-content-lg in min-width 768px"]


def test_checker_accepts_a_matching_block() -> None:
    assert _block_mismatches("@media (min-width: 768px) { .p-md-5 { a: b } }", "x") == []
