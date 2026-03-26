"""Individual fix action implementations for pd:doctor auto-fix.

Each fix function takes a FixContext and an Issue, returns a str description
of the action taken. Raises on failure (caller catches and records as failed).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from doctor.models import Issue
from workflow_engine.feature_lifecycle import _atomic_json_write

if TYPE_CHECKING:
    from entity_registry.database import EntityDatabase
    from workflow_engine.engine import WorkflowStateEngine


@dataclass
class FixContext:
    """Shared context for all fix functions."""

    entities_db_path: str
    memory_db_path: str
    artifacts_root: str
    project_root: str
    db: EntityDatabase | None
    engine: WorkflowStateEngine | None
    # entities_conn IS db._conn (intentional encapsulation bypass — EntityDatabase
    # lacks public setters for parent_uuid/parent_type_id).
    entities_conn: sqlite3.Connection | None
    memory_conn: sqlite3.Connection | None


# Canonical phase sequence — must match transition_gate.constants.PHASE_SEQUENCE
_PHASE_ORDER = [
    "brainstorm",
    "specify",
    "design",
    "create-plan",
    "create-tasks",
    "implement",
    "finish",
]


def _fix_last_completed_phase(ctx: FixContext, issue: Issue) -> str:
    """Update .meta.json lastCompletedPhase to the latest completed phase."""
    if not issue.entity:
        raise ValueError("No entity on issue")
    # Extract entity_id from type_id (e.g., "feature:008-test" -> "008-test")
    parts = issue.entity.split(":", 1)
    entity_id = parts[1] if len(parts) > 1 else parts[0]

    meta_path = os.path.join(
        ctx.project_root, ctx.artifacts_root, "features", entity_id, ".meta.json"
    )
    with open(meta_path) as f:
        meta = json.load(f)

    phases = meta.get("phases", {})
    latest_phase = None
    latest_idx = -1
    for phase_name, phase_data in phases.items():
        if isinstance(phase_data, dict) and phase_data.get("completed"):
            try:
                idx = _PHASE_ORDER.index(phase_name)
            except ValueError:
                continue
            if idx > latest_idx:
                latest_idx = idx
                latest_phase = phase_name

    if latest_phase is None:
        raise ValueError(f"No completed phases found in {meta_path}")

    meta["lastCompletedPhase"] = latest_phase
    _atomic_json_write(meta_path, meta)
    return f"Set lastCompletedPhase to '{latest_phase}'"


def _fix_completed_timestamp(ctx: FixContext, issue: Issue) -> str:
    """Set top-level 'completed' timestamp from latest phase completion."""
    if not issue.entity:
        raise ValueError("No entity on issue")
    parts = issue.entity.split(":", 1)
    entity_id = parts[1] if len(parts) > 1 else parts[0]

    meta_path = os.path.join(
        ctx.project_root, ctx.artifacts_root, "features", entity_id, ".meta.json"
    )
    with open(meta_path) as f:
        meta = json.load(f)

    # Find latest completed timestamp from phases
    from datetime import datetime, timezone
    latest = None
    for phase_data in meta.get("phases", {}).values():
        if isinstance(phase_data, dict) and "completed" in phase_data:
            ts = phase_data["completed"]
            if latest is None or ts > latest:
                latest = ts

    if latest is None:
        latest = datetime.now(timezone.utc).isoformat()

    meta["completed"] = latest
    _atomic_json_write(meta_path, meta)
    return f"Set completed timestamp to {latest}"


def _fix_reconcile(ctx: FixContext, issue: Issue) -> str:
    """Run reconcile_apply for a specific feature."""
    from workflow_engine.reconciliation import apply_workflow_reconciliation

    if not issue.entity:
        raise ValueError("No entity on issue")

    apply_workflow_reconciliation(
        engine=ctx.engine,
        db=ctx.db,
        artifacts_root=ctx.artifacts_root,
        feature_type_id=issue.entity,
    )
    return f"Ran reconcile_apply for {issue.entity}"


def _fix_entity_status_promoted(ctx: FixContext, issue: Issue) -> str:
    """Update entity status to 'promoted'."""
    if not ctx.db or not issue.entity:
        raise ValueError("No DB or entity on issue")
    ctx.db.update_entity(type_id=issue.entity, status="promoted")
    return f"Updated {issue.entity} status to 'promoted'"


def _fix_backlog_annotation(ctx: FixContext, issue: Issue) -> str:
    """Add (promoted -> feature) annotation to backlog.md."""
    if not issue.entity:
        raise ValueError("No entity on issue")

    # Extract backlog ID from type_id (e.g., "backlog:00042" -> "00042")
    parts = issue.entity.split(":", 1)
    backlog_id = parts[1] if len(parts) > 1 else parts[0]

    backlog_path = os.path.join(
        ctx.project_root, ctx.artifacts_root, "backlog.md"
    )
    with open(backlog_path) as f:
        content = f.read()

    pattern = re.compile(r"(\|)\s*" + re.escape(backlog_id) + r"\s*(\|)")
    if not pattern.search(content):
        raise ValueError(f"Could not find backlog row for ID {backlog_id}")

    # Find the line with this ID and append annotation
    lines = content.split("\n")
    updated = False
    for i, line in enumerate(lines):
        if pattern.search(line):
            # Append annotation before the trailing pipe if present
            if line.rstrip().endswith("|"):
                lines[i] = line.rstrip()[:-1] + f" (promoted) |"
            else:
                lines[i] = line + f" (promoted)"
            updated = True
            break

    if not updated:
        raise ValueError(f"Failed to update backlog row for ID {backlog_id}")

    with open(backlog_path, "w") as f:
        f.write("\n".join(lines))

    return f"Added promotion annotation for {backlog_id}"


def _fix_wal_entities(ctx: FixContext, issue: Issue) -> str:
    """Set PRAGMA journal_mode=WAL on the entity database."""
    if not ctx.entities_conn:
        raise ValueError("No entities connection")
    ctx.entities_conn.execute("PRAGMA journal_mode=WAL")
    return "Set journal_mode=WAL on entity DB"


def _fix_wal_memory(ctx: FixContext, issue: Issue) -> str:
    """Set PRAGMA journal_mode=WAL on the memory database."""
    if not ctx.memory_conn:
        raise ValueError("No memory connection")
    ctx.memory_conn.execute("PRAGMA journal_mode=WAL")
    return "Set journal_mode=WAL on memory DB"


def _fix_parent_uuid(ctx: FixContext, issue: Issue) -> str:
    """Lookup parent entity uuid and update parent_uuid via direct SQL."""
    if not ctx.entities_conn or not issue.entity:
        raise ValueError("No entities connection or entity")

    # Get parent_type_id for this entity
    row = ctx.entities_conn.execute(
        "SELECT parent_type_id FROM entities WHERE type_id = ?",
        (issue.entity,),
    ).fetchone()
    if not row or not row[0]:
        raise ValueError(f"No parent_type_id for {issue.entity}")

    parent_type_id = row[0]
    # Lookup parent uuid
    parent_row = ctx.entities_conn.execute(
        "SELECT uuid FROM entities WHERE type_id = ?",
        (parent_type_id,),
    ).fetchone()
    if not parent_row:
        raise ValueError(f"Parent entity {parent_type_id} not found")

    parent_uuid = parent_row[0]
    # Intentional encapsulation bypass -- EntityDatabase has no public
    # setter for parent_uuid.
    ctx.entities_conn.execute(
        "UPDATE entities SET parent_uuid = ? WHERE type_id = ?",
        (parent_uuid, issue.entity),
    )
    ctx.entities_conn.commit()
    return f"Set parent_uuid to {parent_uuid} for {issue.entity}"


def _fix_self_referential_parent(ctx: FixContext, issue: Issue) -> str:
    """Remove self-referential parent_type_id."""
    if not ctx.entities_conn or not issue.entity:
        raise ValueError("No entities connection or entity")

    # Intentional encapsulation bypass -- EntityDatabase.update_entity
    # lacks parent_type_id param.
    ctx.entities_conn.execute(
        "UPDATE entities SET parent_type_id = NULL, parent_uuid = NULL WHERE type_id = ?",
        (issue.entity,),
    )
    ctx.entities_conn.commit()
    return f"Removed self-referential parent for {issue.entity}"


def _fix_remove_orphan_dependency(ctx: FixContext, issue: Issue) -> str:
    """Remove orphaned dependency row."""
    if not ctx.entities_conn:
        raise ValueError("No entities connection")

    # Extract UUIDs from issue.message
    uuids = re.findall(r"'([0-9a-f-]{36})'", issue.message)
    if len(uuids) < 2:
        raise ValueError(f"Could not extract 2 UUIDs from: {issue.message}")

    entity_uuid, blocked_by_uuid = uuids[0], uuids[1]
    ctx.entities_conn.execute(
        "DELETE FROM entity_dependencies WHERE entity_uuid = ? AND blocked_by_uuid = ?",
        (entity_uuid, blocked_by_uuid),
    )
    ctx.entities_conn.commit()
    return f"Removed orphan dependency {entity_uuid} -> {blocked_by_uuid}"


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


def _fix_run_memory_migrations(ctx: FixContext, issue: Issue) -> str:
    """Run memory DB migrations by constructing MemoryDatabase."""
    from semantic_memory.database import MemoryDatabase

    db = MemoryDatabase(ctx.memory_db_path)
    db.close()
    return "Ran memory DB migrations"


def _fix_project_attribution(ctx: FixContext, issue: Issue) -> str:
    """Backfill project_id for __unknown__ entities under project_root."""
    if not ctx.db:
        raise ValueError("No entity database available")
    if not ctx.project_root:
        raise ValueError("No project_root available")

    from entity_registry.project_identity import detect_project_id

    project_id = detect_project_id(ctx.project_root)
    count = ctx.db.backfill_project_ids(ctx.project_root, project_id)
    return f"Backfilled project_id for {count} entities (project={project_id})"


def _fix_stale_dependency(ctx: FixContext, issue: Issue) -> str:
    """Remove stale dependency on a completed blocker via cascade_unblock."""
    if ctx.db is None:
        raise ValueError("No entity database")
    uuids = re.findall(r"'([0-9a-f-]{36})'", issue.message)
    if len(uuids) < 2:
        raise ValueError(f"Cannot extract UUIDs from: {issue.message}")
    blocked_by_uuid = uuids[1]
    from entity_registry.dependencies import DependencyManager
    result = DependencyManager().cascade_unblock(ctx.db, blocked_by_uuid)
    if result:
        return f"Removed stale dependency on {blocked_by_uuid}, unblocked {len(result)} entities"
    return f"Stale dependency on {blocked_by_uuid} already cleaned"
