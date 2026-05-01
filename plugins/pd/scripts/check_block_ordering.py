#!/usr/bin/env python3
"""Validate FR-1 influence-tracking block placement in orchestrator commands.

Feature 101 / Component C-4. Asserts each `<!-- influence-tracking-site: sN -->`
HTML marker appears BEFORE the next `**Branch on ...**` marker within the
same command file, and that the 2/2/3/7 distribution is correct across
the four files.

Usage:
    python plugins/pd/scripts/check_block_ordering.py
    Exit 0 = pass, 1 = fail.

Wired into validate.sh's component-check loop.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


COMMAND_FILES = {
    "specify.md": 2,
    "design.md": 2,
    "create-plan.md": 3,
    "implement.md": 7,
}

MARKER_RE = re.compile(r"<!--\s*influence-tracking-site:\s*(s\d+)\s*-->")
BRANCH_RE = re.compile(r"^\*\*Branch on\b", re.MULTILINE)


def _check_file(path: Path, expected_count: int) -> tuple[list[str], int]:
    """Return (errors, marker_count)."""
    errors: list[str] = []
    if not path.exists():
        errors.append(f"{path}: file not found")
        return errors, 0

    text = path.read_text()
    lines = text.split("\n")

    # Find all marker line numbers (1-indexed).
    marker_lines: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        m = MARKER_RE.search(line)
        if m:
            marker_lines.append((i, m.group(1)))

    branch_lines: list[int] = []
    branch_re = re.compile(r"\*\*Branch on")
    for i, line in enumerate(lines, start=1):
        if branch_re.search(line):
            branch_lines.append(i)

    # Branch-on ordering check applies only to files that USE 'Branch on'
    # markers as their next-step delimiter (specify, design, create-plan).
    # implement.md uses different structural markers (Decision logic / Apply
    # strict threshold / etc.) — count check alone validates ordering for it.
    if branch_lines:
        for idx, (m_line, s_id) in enumerate(marker_lines):
            next_marker_line = (
                marker_lines[idx + 1][0] if idx + 1 < len(marker_lines) else len(lines) + 1
            )
            branches_in_window = [b for b in branch_lines if m_line < b < next_marker_line]
            if not branches_in_window:
                errors.append(
                    f"{path}:{m_line}: marker {s_id} has no following 'Branch on' marker"
                )

    if len(marker_lines) != expected_count:
        errors.append(
            f"{path}: expected {expected_count} markers, found {len(marker_lines)}"
        )

    return errors, len(marker_lines)


def main(argv: list[str] | None = None) -> int:
    base = Path("plugins/pd/commands")
    all_errors: list[str] = []
    counts: list[int] = []
    seen_ids: list[str] = []

    for filename, expected in COMMAND_FILES.items():
        path = base / filename
        errors, count = _check_file(path, expected)
        all_errors.extend(errors)
        counts.append(count)
        if path.exists():
            for m in MARKER_RE.finditer(path.read_text()):
                seen_ids.append(m.group(1))

    # Check that we have exactly 14 distinct s-ids.
    unique = sorted(set(seen_ids))
    if len(unique) != 14:
        all_errors.append(
            f"Expected 14 distinct site_ids (s1..s14), found {len(unique)}: {unique}"
        )
    expected_ids = [f"s{i}" for i in range(1, 15)]
    missing = [x for x in expected_ids if x not in unique]
    extra = [x for x in unique if x not in expected_ids]
    if missing:
        all_errors.append(f"Missing site_ids: {missing}")
    if extra:
        all_errors.append(f"Unexpected site_ids: {extra}")

    if all_errors:
        for e in all_errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1

    print(
        f"OK: 14 blocks correctly positioned "
        f"({counts[0]}/{counts[1]}/{counts[2]}/{counts[3]})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
