"""Individual fix action implementations for pd:doctor auto-fix.

Each fix function takes a FixContext and an Issue, returns a str description
of the action taken. Raises on failure (caller catches and records as failed).
"""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from doctor.models import Issue

if TYPE_CHECKING:
    from entity_registry.database import EntityDatabase
    from workflow_engine.engine import WorkflowStateEngine


@dataclass
class FixContext:
    """Shared context for all fix functions."""

    entities_db_path: str
    artifacts_root: str
    project_root: str
    db: EntityDatabase | None
    engine: WorkflowStateEngine | None
    # entities_conn IS db._conn (intentional encapsulation bypass — EntityDatabase
    # lacks public setters for parent_uuid/parent_type_id).
    entities_conn: sqlite3.Connection | None


def _fix_wal_entities(ctx: FixContext, issue: Issue) -> str:
    """Set PRAGMA journal_mode=WAL on the entity database."""
    if not ctx.entities_conn:
        raise ValueError("No entities connection")
    ctx.entities_conn.execute("PRAGMA journal_mode=WAL")
    return "Set journal_mode=WAL on entity DB"


def _fix_self_referential_parent(ctx: FixContext, issue: Issue) -> str:
    """Clear self-referential parent_uuid."""
    if not ctx.entities_conn or not issue.entity:
        raise ValueError("No entities connection or entity")

    ctx.entities_conn.execute(
        "UPDATE entities SET parent_uuid = NULL WHERE type_id = ?",
        (issue.entity,),
    )
    ctx.entities_conn.commit()
    return f"Cleared self-referential parent for {issue.entity}"


def _fix_remove_orphan_tag(ctx: FixContext, issue: Issue) -> str:
    """Remove orphaned tag row."""
    if not ctx.entities_conn:
        raise ValueError("No entities connection")

    uuids = re.findall(r"'([0-9a-f-]{36})'", issue.message)
    if not uuids:
        raise ValueError(f"Could not extract UUID from: {issue.message}")

    entity_uuid = uuids[0]
    ctx.entities_conn.execute(
        "DELETE FROM entity_tags WHERE entity_uuid = ?",
        (entity_uuid,),
    )
    ctx.entities_conn.commit()
    return f"Removed orphan tags for {entity_uuid}"


def _fix_remove_orphan_workflow(ctx: FixContext, issue: Issue) -> str:
    """Remove orphaned workflow_phases row."""
    if not ctx.entities_conn:
        raise ValueError("No entities connection")

    # Use issue.entity if available, else try to extract from message
    type_id = issue.entity
    if not type_id:
        # Try to extract type_id from message
        match = re.search(r"type_id '([^']+)'", issue.message)
        if match:
            type_id = match.group(1)
    if not type_id:
        raise ValueError(f"Could not determine type_id from issue")

    ctx.entities_conn.execute(
        "DELETE FROM workflow_phases WHERE type_id = ?",
        (type_id,),
    )
    ctx.entities_conn.commit()
    return f"Removed orphan workflow_phases for {type_id}"


def _fix_rebuild_fts(ctx: FixContext, issue: Issue) -> str:
    """Rebuild FTS index via migrate_db.py."""
    # Try project_root/scripts/migrate_db.py first
    script_path = os.path.join(ctx.project_root, "scripts", "migrate_db.py")
    if not os.path.isfile(script_path):
        # Fallback: try plugin root (parent of hooks/lib)
        # Navigate from doctor module location
        doctor_dir = os.path.dirname(os.path.abspath(__file__))
        # doctor_dir is hooks/lib/doctor -> plugin root is hooks/lib/../../..
        plugin_root = os.path.normpath(os.path.join(doctor_dir, "..", "..", ".."))
        script_path = os.path.join(plugin_root, "scripts", "migrate_db.py")
        if not os.path.isfile(script_path):
            raise FileNotFoundError(
                f"migrate_db.py not found in project or plugin root"
            )

    result = subprocess.run(
        [sys.executable, script_path, "rebuild-fts", "--skip-kill", ctx.entities_db_path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"rebuild-fts failed: {result.stderr[:200]}")

    return "Rebuilt FTS index"


def _fix_run_entity_migrations(ctx: FixContext, issue: Issue) -> str:
    """Run entity DB migrations by constructing EntityDatabase."""
    from entity_registry.database import EntityDatabase

    db = EntityDatabase(ctx.entities_db_path)
    db.close()
    return "Ran entity DB migrations"


def _fix_missed_cascade(ctx: FixContext, issue: Issue) -> str:
    """Run the missed cascade evaluation via cascade_unblock (feature 124 D6).

    Renamed from ``_fix_stale_dependency`` -- the underlying mechanism is
    unchanged (post-D3, cascade_unblock IS the flip evaluation): re-running
    it on any one of the flagged entity's now-resolved blockers re-checks
    ALL of that entity's blockers via ``_all_blockers_resolved`` and flips
    it (and any other affected dependents) to 'ready'.
    """
    if ctx.db is None:
        raise ValueError("No entity database")
    uuids = re.findall(r"'([0-9a-f-]{36})'", issue.message)
    if len(uuids) < 2:
        raise ValueError(f"Cannot extract UUIDs from: {issue.message}")
    blocked_by_uuid = uuids[1]
    from entity_registry.dependencies import DependencyManager
    result = DependencyManager().cascade_unblock(ctx.db, blocked_by_uuid)
    if result:
        return f"Re-evaluated blocker {blocked_by_uuid}, flipped {len(result)} entities to ready"
    return f"Cascade for blocker {blocked_by_uuid} already applied"


