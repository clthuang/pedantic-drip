#!/usr/bin/env python3
"""Feature 110 Task 8.6 — Whitespace-normalized diff between
``_project_backlog_md(db)`` output and the existing ``docs/backlog.md``.

Exit status:
  0 — no semantic drift (whitespace-normalized diff is empty).
  1 — diff found; first ~50 lines printed to stderr.
  2 — script execution error (missing file, DB connect failure, etc.).

Whitespace normalization (per design TD-10 AC-4.2a):
  - Collapse runs of multiple blank lines to a single blank line.
  - Strip trailing whitespace from each line.
  - Ignore differences in indentation of bullet-item continuation
    lines (rare; matches the existing ``docs/backlog.md`` irregularity
    surface).

Stdlib-only. The script is intentionally usable from CI without the
plugin venv as long as the ``plugins/pd/hooks/lib`` modules are
importable on ``PYTHONPATH`` (or the script is invoked from the repo
root where ``plugins/pd/hooks/lib`` is auto-added via ``sys.path``
manipulation below).
"""
from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
from pathlib import Path


def _resolve_repo_root() -> Path:
    """Return the repo root by walking parents from this script."""
    return Path(__file__).resolve().parents[3]


def _setup_imports() -> None:
    """Augment ``sys.path`` so ``workflow_state_server`` + ``entity_registry``
    can be imported from a vanilla python invocation."""
    repo_root = _resolve_repo_root()
    mcp_dir = repo_root / "plugins" / "pd" / "mcp"
    hooks_lib = repo_root / "plugins" / "pd" / "hooks" / "lib"
    for p in (mcp_dir, hooks_lib):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)


def _normalize(text: str) -> list[str]:
    """Apply whitespace normalization per AC-4.2a contract."""
    lines = text.splitlines()
    # Strip trailing whitespace from each line.
    lines = [line.rstrip() for line in lines]
    # Collapse runs of consecutive blank lines to a single blank.
    out: list[str] = []
    prev_blank = False
    for line in lines:
        if line.strip() == "":
            if prev_blank:
                continue
            prev_blank = True
            out.append("")
        else:
            prev_blank = False
            out.append(line)
    # Strip leading/trailing blank lines for symmetric comparison.
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare _project_backlog_md output to docs/backlog.md "
                    "(whitespace-normalized).",
    )
    parser.add_argument(
        "--backlog-path",
        default=None,
        help="Path to the existing backlog.md (default: "
             "<repo>/docs/backlog.md).",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to entity registry SQLite DB. If omitted, uses the "
             "default ENTITY_DB_PATH or ~/.claude/pd/entities/entities.db.",
    )
    parser.add_argument(
        "--diff-limit",
        type=int,
        default=50,
        help="Max diff lines to print on drift (default: 50).",
    )
    args = parser.parse_args(argv)

    repo_root = _resolve_repo_root()
    backlog_path = (
        Path(args.backlog_path)
        if args.backlog_path
        else repo_root / "docs" / "backlog.md"
    )
    if not backlog_path.exists():
        sys.stderr.write(f"error: backlog file not found: {backlog_path}\n")
        return 2

    _setup_imports()
    try:
        from entity_registry.database import EntityDatabase
        from workflow_state_server import _project_backlog_md
    except Exception as exc:
        sys.stderr.write(f"error: failed to import projection modules: {exc}\n")
        return 2

    # Database opens via the standard path (or override).
    if args.db_path:
        db_path = args.db_path
    else:
        db_path = os.environ.get(
            "ENTITY_DB_PATH",
            str(Path.home() / ".claude" / "pd" / "entities" / "entities.db"),
        )

    try:
        db = EntityDatabase(db_path)
        projected = _project_backlog_md(db)
    except Exception as exc:
        sys.stderr.write(f"error: projection failed: {exc}\n")
        return 2

    existing = backlog_path.read_text(encoding="utf-8")

    proj_norm = _normalize(projected)
    exist_norm = _normalize(existing)

    if proj_norm == exist_norm:
        return 0

    # Drift — emit unified diff (truncated).
    diff_iter = difflib.unified_diff(
        exist_norm,
        proj_norm,
        fromfile=str(backlog_path),
        tofile="_project_backlog_md(db)",
        lineterm="",
    )
    diff_lines = list(diff_iter)
    if not diff_lines:
        # Defensive: equality check disagreed with empty diff. Treat as
        # drift to avoid silent-pass on a normalization bug.
        sys.stderr.write(
            "drift detected: projection and backlog.md differ but unified "
            "diff returned no lines (normalization mismatch)\n"
        )
        return 1

    limit = max(0, args.diff_limit)
    for line in diff_lines[:limit]:
        sys.stderr.write(line + "\n")
    if len(diff_lines) > limit:
        sys.stderr.write(
            f"... (truncated {len(diff_lines) - limit} more lines)\n"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
