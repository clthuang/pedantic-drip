#!/usr/bin/env python3
"""Probe: verify the TD-1 Verified Behavior matrix for fnmatch.fnmatch.

Feature 110 design §TD-1 documents the fnmatch behavior the dispatcher relies
on. This probe exercises each row of the matrix and exits nonzero on any
deviation, giving future implementers a fast empirical check.

Note on row 5: the original design predicted `False` for
`fnmatch.fnmatch('docs/projects/P003/.meta.json', 'docs/projects/*/*.meta.json')`,
but Python's stdlib actually returns `True` (the second `*` may be empty, so
`.meta.json` matches `*.meta.json`). This probe records empirical truth.
"""
from __future__ import annotations

import fnmatch
import sys

MATRIX: list[tuple[str, str, bool]] = [
    ("docs/features/043/.meta.json", "*.meta.json", True),
    ("docs/projects/P003/.meta.json", "*.meta.json", True),
    ("docs/projects/P003/.meta.json", "docs/projects/*/.meta.json", True),
    ("docs/backlog.md", "docs/backlog.md", True),
    # See module docstring: empirical True, design said False.
    ("docs/projects/P003/.meta.json", "docs/projects/*/*.meta.json", True),
]


def main() -> int:
    failures: list[str] = []
    for path, pattern, expected in MATRIX:
        actual = fnmatch.fnmatch(path, pattern)
        ok = actual is expected
        marker = "OK" if ok else "FAIL"
        print(f"[{marker}] fnmatch({path!r}, {pattern!r}) -> {actual} (expected {expected})")
        if not ok:
            failures.append(f"  fnmatch({path!r}, {pattern!r}) returned {actual}, expected {expected}")

    if failures:
        print("\nFAILURES:", file=sys.stderr)
        for line in failures:
            print(line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
