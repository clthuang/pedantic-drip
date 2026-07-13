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


# Known TD-11 drift classes (feature 110 design §3 TD-11).
_DRIFT_LAST_COMPLETED_PHASE = "lastCompletedPhase mismatch"
_DRIFT_STATUS_MISMATCH = "status mismatch"
_DRIFT_BRANCH_FIELD_STALE = "branch field stale"


def _fix_meta_json_via_mcp(
    ctx: FixContext,
    drift_class: str,
    feature_type_id: str,
) -> str:
    """Route .meta.json drift fixes through MCP / projection (TD-11).

    Per design TD-11, doctor autofix MUST NOT write .meta.json directly.
    Each drift class corresponds to a specific MCP / projection invocation
    that re-derives the file from DB state.

    Returns a status string describing the action taken. For unknown drift
    classes, returns a WARN string (no autofix; surface to user).
    """
    # F4-AUDIT: MCP-routed (TD-11)
    if not feature_type_id:
        raise ValueError("No feature_type_id provided for drift fix")

    # Drift class #1: lastCompletedPhase mismatch -> complete_phase(DB phase).
    if drift_class == _DRIFT_LAST_COMPLETED_PHASE:
        if ctx.engine is None or ctx.db is None:
            raise ValueError(
                "Engine + DB required for lastCompletedPhase fix (drift "
                "class #1); both must be present on FixContext."
            )
        # DB phase = current last_completed_phase column on workflow_phases.
        row = ctx.db.get_workflow_phase(feature_type_id)
        if row is None:
            raise ValueError(
                f"workflow_phases row missing for {feature_type_id}; cannot "
                "route lastCompletedPhase fix through MCP."
            )
        if isinstance(row, dict):
            db_phase = row.get("last_completed_phase")
        else:
            db_phase = row["last_completed_phase"]
        if not db_phase:
            raise ValueError(
                f"workflow_phases.last_completed_phase NULL for "
                f"{feature_type_id}; nothing to project."
            )
        ctx.engine.complete_phase(feature_type_id, db_phase)
        return (
            f"Routed lastCompletedPhase fix through complete_phase MCP for "
            f"{feature_type_id} (phase={db_phase})"
        )

    # Drift class #2: status mismatch (DB completed, file active) ->
    # complete_phase(phase='finish').
    if drift_class == _DRIFT_STATUS_MISMATCH:
        if ctx.engine is None:
            raise ValueError(
                "Engine required for status mismatch fix (drift class #2)."
            )
        ctx.engine.complete_phase(feature_type_id, "finish")
        return (
            f"Routed status mismatch fix through complete_phase(phase='finish') "
            f"MCP for {feature_type_id}"
        )

    # Drift class #3: branch field stale -> re-project via _project_meta_json.
    if drift_class == _DRIFT_BRANCH_FIELD_STALE:
        if ctx.db is None:
            raise ValueError(
                "DB required for branch field stale fix (drift class #3)."
            )
        # In-process import per design TD-11 -- workflow_state_server.py is in
        # plugins/pd/mcp (added to sys.path at MCP server import time).
        from workflow_state_server import _project_meta_json
        warning = _project_meta_json(ctx.db, ctx.engine, feature_type_id)
        if warning:
            return (
                f"Re-projected .meta.json for {feature_type_id} via "
                f"_project_meta_json (with warning: {warning})"
            )
        return (
            f"Re-projected .meta.json for {feature_type_id} via "
            f"_project_meta_json (branch field refreshed)"
        )

    # Drift class #4: unknown -> WARN-only finding (no autofix).
    return (
        f"WARN: unknown drift class '{drift_class}' for {feature_type_id}; "
        f"no autofix available — surface to user for manual MCP invocation."
    )


# F4-AUDIT: MCP-routed (TD-11)
def _fix_last_completed_phase(ctx: FixContext, issue: Issue) -> str:
    """MCP-routing wrapper for lastCompletedPhase drift (TD-11 drift class #1).

    Replaces direct .meta.json write; routes through engine.complete_phase
    so the projection function regenerates the file from DB state.
    """
    if not issue.entity:
        raise ValueError("No entity on issue")
    return _fix_meta_json_via_mcp(ctx, _DRIFT_LAST_COMPLETED_PHASE, issue.entity)


# F4-AUDIT: MCP-routed (TD-11)
def _fix_completed_timestamp(ctx: FixContext, issue: Issue) -> str:
    """MCP-routing wrapper for status / completed-timestamp drift (TD-11 #2).

    Replaces direct .meta.json write; routes through
    engine.complete_phase(phase='finish') so the projection refreshes the
    top-level `completed` timestamp from DB state.
    """
    if not issue.entity:
        raise ValueError("No entity on issue")
    return _fix_meta_json_via_mcp(ctx, _DRIFT_STATUS_MISMATCH, issue.entity)


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


def _fix_entity_status_dropped(ctx: FixContext, issue: Issue) -> str:
    """Update entity status to 'dropped'."""
    if not ctx.db or not issue.entity:
        raise ValueError("No DB or entity on issue")
    ctx.db.update_entity(type_id=issue.entity, status="dropped")
    return f"Updated {issue.entity} status to 'dropped'"


# F4-AUDIT: annotation-only; not state mutation
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
        return f"Removed stale dependency on {blocked_by_uuid}, unblocked {len(result)} entities"
    return f"Stale dependency on {blocked_by_uuid} already cleaned"


def _read_workspace_json_file_uuid(project_root: str) -> tuple[str, str | None]:
    """Return (workspace_json_path, file_uuid) for the project, re-derived at
    fix time. file_uuid is None when the file is absent."""
    import json as _json

    ws_path = os.path.join(project_root, ".claude", "pd", "workspace.json")
    if not os.path.isfile(ws_path):
        return ws_path, None
    try:
        with open(ws_path, encoding="utf-8") as fh:
            return ws_path, _json.load(fh).get("workspace_uuid")
    except (OSError, _json.JSONDecodeError) as exc:
        raise ValueError(f"workspace.json unreadable: {exc}") from exc


def _fix_adopt_workspace_uuid(ctx: FixContext, issue: Issue) -> str:
    """Adopt the project_root's canonical workspace UUID into workspace.json.

    Re-derives all state at fix time (never trusts the issue message). No-ops
    gracefully when the split-brain has already been healed (file uuid now a
    member, or the file is gone).
    """
    if not ctx.project_root:
        raise ValueError(
            "FixContext.project_root required for workspace UUID fix actions"
        )
    if not ctx.entities_conn:
        raise ValueError("No entities connection")
    from entity_registry.project_identity import (
        _rewrite_workspace_json_if_matches,
    )

    ws_path, file_uuid = _read_workspace_json_file_uuid(ctx.project_root)
    if file_uuid is None:
        return "already consistent: workspace.json absent — no rewrite needed"
    if ctx.entities_conn.execute(
        "SELECT 1 FROM workspaces WHERE uuid = ?", (file_uuid,)
    ).fetchone() is not None:
        return "already consistent: workspace.json uuid present in DB"
    rows = ctx.entities_conn.execute(
        "SELECT uuid FROM workspaces "
        "WHERE project_root IS NOT NULL AND project_root = ?",
        (os.path.abspath(ctx.project_root),),
    ).fetchall()
    if len(rows) != 1:
        return (
            f"no-op: expected exactly one project_root row to adopt, "
            f"found {len(rows)}"
        )
    adopted = rows[0][0]
    result = _rewrite_workspace_json_if_matches(ws_path, file_uuid, adopted)
    return (
        f"Adopted workspace UUID {adopted} into workspace.json "
        f"(was orphan {file_uuid}); on-disk now {result}"
    )


def _fix_insert_workspace_row(ctx: FixContext, issue: Issue) -> str:
    """Insert the missing workspaces row for the file's orphaned UUID.

    Re-derives state at fix time. No-ops when already healed or when the
    project_root turns out to be owned by another uuid (defensive — the check
    only emits this hint when zero rows match the root).
    """
    if not ctx.project_root:
        raise ValueError(
            "FixContext.project_root required for workspace UUID fix actions"
        )
    if not ctx.entities_conn:
        raise ValueError("No entities connection")
    from entity_registry.project_identity import (
        _WORKSPACE_UUID_RE,
        _compute_legacy_project_id,
        _insert_workspace_row_if_absent,
    )

    _ws_path, file_uuid = _read_workspace_json_file_uuid(ctx.project_root)
    if file_uuid is None:
        return "already consistent: workspace.json absent — no row needed"
    if not _WORKSPACE_UUID_RE.match(file_uuid or ""):
        # Defensive: never insert a malformed uuid as a workspaces.uuid.
        raise ValueError(
            f"workspace.json workspace_uuid {file_uuid!r} is malformed; "
            f"refusing to insert. rm the file and re-run session-start."
        )
    if ctx.entities_conn.execute(
        "SELECT 1 FROM workspaces WHERE uuid = ?", (file_uuid,)
    ).fetchone() is not None:
        return "already consistent: workspace.json uuid present in DB"
    root = os.path.abspath(ctx.project_root)
    outcome = _insert_workspace_row_if_absent(
        ctx.entities_conn, file_uuid, root, _compute_legacy_project_id(root)
    )
    if outcome == "conflict-root":
        return "no-op: project_root already owned by another workspace row"
    ctx.entities_conn.commit()
    return f"Inserted workspaces row for {file_uuid} (outcome={outcome})"


def _fix_claim_unknown_entities(ctx: FixContext, issue: Issue) -> str:
    """Re-attribute unknown-workspace orphan entities into the project's workspace.

    Re-derives the target workspace at fix time from ``project_root`` (never
    trusts the issue message), mirroring ``_fix_adopt_workspace_uuid``.
    Delegates the actual re-attribution — and its trigger-dance — to
    ``EntityDatabase.claim_unknown_entities``, which itself guards the
    no-op self-claim and missing-workspace cases.
    """
    if not ctx.project_root:
        raise ValueError(
            "FixContext.project_root required for workspace claim fix actions"
        )
    if not ctx.db or not ctx.entities_conn:
        raise ValueError("No entities DB")
    rows = ctx.entities_conn.execute(
        "SELECT uuid FROM workspaces "
        "WHERE project_root IS NOT NULL AND project_root = ?",
        (os.path.abspath(ctx.project_root),),
    ).fetchall()
    if len(rows) != 1:
        return (
            f"no-op: expected exactly one project_root workspace row to claim "
            f"into, found {len(rows)}"
        )
    ws_uuid = rows[0][0]
    n = ctx.db.claim_unknown_entities(workspace_uuid=ws_uuid)
    noun = "entity" if n == 1 else "entities"
    return f"Claimed {n} unknown-workspace {noun} into {ws_uuid}"
