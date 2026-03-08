"""One-time fix for stale feature kanban_column values.

Uses STATUS_TO_KANBAN (status-based) rather than FEATURE_PHASE_TO_KANBAN
(phase-based) because this remediates what init_feature_state should have
set at creation time. For active features in early phases (brainstorm/specify),
the kanban may change from 'wip' to 'backlog' on next runtime transition --
this is correct behavior as phase-based mapping becomes authoritative during
the feature lifecycle.

For completed/abandoned features, both mappings agree (-> 'completed').
"""
from __future__ import annotations

import argparse
import os
import sqlite3

# Inline copy -- must match STATUS_TO_KANBAN in backfill.py:35-40.
# Also referenced by workflow_state_server.py init-time kanban override.
STATUS_TO_KANBAN: dict[str, str] = {
    "planned": "backlog",
    "active": "wip",
    "completed": "completed",
    "abandoned": "completed",
}

_UPDATE_SQL = """\
UPDATE workflow_phases
SET kanban_column = CASE
    (SELECT status FROM entities WHERE entities.type_id = workflow_phases.type_id)
    WHEN 'planned' THEN 'backlog'
    WHEN 'active' THEN 'wip'
    WHEN 'completed' THEN 'completed'
    WHEN 'abandoned' THEN 'completed'
    ELSE kanban_column
END,
updated_at = datetime('now')
WHERE type_id LIKE 'feature:%'
"""

_PREVIEW_SQL = """\
SELECT
    wp.type_id,
    wp.kanban_column AS current_kanban,
    e.status,
    CASE e.status
        WHEN 'planned' THEN 'backlog'
        WHEN 'active' THEN 'wip'
        WHEN 'completed' THEN 'completed'
        WHEN 'abandoned' THEN 'completed'
        ELSE wp.kanban_column
    END AS new_kanban
FROM workflow_phases wp
LEFT JOIN entities e ON e.type_id = wp.type_id
WHERE wp.type_id LIKE 'feature:%'
"""


def fix_kanban_columns(db_path_or_conn: str | sqlite3.Connection) -> int:
    """Fix kanban_column values for feature workflow_phases rows.

    Args:
        db_path_or_conn: Either a filesystem path to the SQLite DB or an
            existing sqlite3.Connection (used in tests).

    Returns:
        Number of rows updated.
    """
    own_conn = False
    if isinstance(db_path_or_conn, sqlite3.Connection):
        conn = db_path_or_conn
    else:
        conn = sqlite3.connect(db_path_or_conn)
        own_conn = True

    try:
        cursor = conn.execute(_UPDATE_SQL)
        rows_changed = cursor.rowcount
        conn.commit()
        return rows_changed
    finally:
        if own_conn:
            conn.close()


def _dry_run(db_path: str) -> None:
    """Show what changes would be made without applying them."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(_PREVIEW_SQL).fetchall()
        changes = [r for r in rows if r["current_kanban"] != r["new_kanban"]]
        if not changes:
            print("No changes needed.")
            return
        print(f"Would update {len(changes)} row(s):")
        for r in changes:
            print(
                f"  {r['type_id']}: {r['current_kanban']} -> {r['new_kanban']}"
                f" (status={r['status']})"
            )
    finally:
        conn.close()


def main() -> None:
    default_db = os.path.expanduser("~/.claude/iflow/entities/entities.db")
    parser = argparse.ArgumentParser(
        description="Fix stale kanban_column values for feature workflow_phases."
    )
    parser.add_argument(
        "--db-path",
        default=default_db,
        help=f"Path to entities DB (default: {default_db})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without applying them.",
    )
    args = parser.parse_args()

    if args.dry_run:
        _dry_run(args.db_path)
    else:
        updated = fix_kanban_columns(args.db_path)
        print(f"Updated {updated} row(s).")


if __name__ == "__main__":
    main()
