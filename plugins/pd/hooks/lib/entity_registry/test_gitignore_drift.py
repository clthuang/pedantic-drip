"""Gitignore + tracked-data-file drift tests (feature 110, Group 13).

Scope:
  - ``test_gitignore_contains_meta_json_pattern`` (Task 13.3 / AC-1.4): the
    repo ``.gitignore`` MUST contain the literal line ``**/.meta.json`` so
    every regenerable meta-json projection stays out of the index.
  - ``test_gitignore_contains_backlog_pattern`` (Task 13.3 / AC-1.4): the
    repo ``.gitignore`` MUST contain the literal line ``docs/backlog.md`` so
    the projected backlog file stays out of the index.
  - ``test_gitignore_contains_pd_state_diff_pattern`` (Task 13.3 / AC-1.4):
    the repo ``.gitignore`` MUST contain the literal line
    ``pd-state.diff.md`` so the pre-commit-hook-generated state-diff
    artifact stays out of the index.
  - ``test_no_tracked_data_files`` (Task 13.4 / AC-1.5): ``git ls-files``
    in the repo root MUST return zero entries matching
    ``\\.meta\\.json$``, ``^docs/backlog\\.md$``, or
    ``^pd-state\\.diff\\.md$``. Catches re-tracking regressions post the
    Group 13 ``git rm --cached`` sweep.

Notes:
  - Tests resolve the repo root via ``Path(__file__).resolve().parents[5]``
    (test file lives 5 directories below the repo root: entity_registry/
    lib/ hooks/ pd/ plugins/ -> repo) in either the main worktree or a
    feature worktree.
  - The ``git ls-files`` test uses ``subprocess.run`` against the resolved
    repo root and filters in Python; this avoids depending on a shell
    ``grep`` and works identically in worktree and main checkouts.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[5]
_GITIGNORE = _REPO_ROOT / ".gitignore"

# AC-1.5 regex pin: matches any tracked .meta.json (full-path or basename),
# top-level docs/backlog.md, and top-level pd-state.diff.md.
_TRACKED_DATA_RE = re.compile(
    r"(\.meta\.json|^docs/backlog\.md|^pd-state\.diff\.md)$"
)


def _read_gitignore_lines() -> list[str]:
    """Return the .gitignore file's lines, stripped of trailing newlines."""
    text = _GITIGNORE.read_text(encoding="utf-8")
    return text.splitlines()


def test_gitignore_contains_meta_json_pattern() -> None:
    """AC-1.4: .gitignore has a literal ``**/.meta.json`` line."""
    lines = _read_gitignore_lines()
    assert "**/.meta.json" in lines, (
        "Expected literal line '**/.meta.json' in .gitignore "
        "(Group 0 / FR-4.5)"
    )


def test_gitignore_contains_backlog_pattern() -> None:
    """AC-1.4: .gitignore has a literal ``docs/backlog.md`` line."""
    lines = _read_gitignore_lines()
    assert "docs/backlog.md" in lines, (
        "Expected literal line 'docs/backlog.md' in .gitignore "
        "(Group 0 / FR-4.5)"
    )


def test_gitignore_contains_pd_state_diff_pattern() -> None:
    """AC-1.4: .gitignore has a literal ``pd-state.diff.md`` line."""
    lines = _read_gitignore_lines()
    assert "pd-state.diff.md" in lines, (
        "Expected literal line 'pd-state.diff.md' in .gitignore "
        "(Group 0 / AC-6.3)"
    )


def test_no_tracked_data_files() -> None:
    """AC-1.5: zero tracked .meta.json / docs/backlog.md / pd-state.diff.md.

    Runs ``git ls-files`` in the repo root and asserts that no path
    matches the AC-1.5 regex (``\\.meta\\.json$``, ``^docs/backlog\\.md$``,
    ``^pd-state\\.diff\\.md$``).
    """
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=str(_REPO_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    matches = [
        line
        for line in result.stdout.splitlines()
        if _TRACKED_DATA_RE.search(line)
    ]
    assert matches == [], (
        "Expected zero tracked data-files matching "
        "(\\.meta\\.json|^docs/backlog\\.md|^pd-state\\.diff\\.md)$, "
        f"got {len(matches)}: {matches[:5]}"
    )
