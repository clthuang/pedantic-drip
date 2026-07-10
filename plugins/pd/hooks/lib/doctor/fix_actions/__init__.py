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
import unicodedata
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


# ---------------------------------------------------------------------------
# Feature 116 FR-9: Defensive parser layer for adversarial fix_hint inputs.
# ---------------------------------------------------------------------------

_UUID_LIKE = re.compile(r"^[0-9a-fA-F\-]+$")        # for parent_uuid, child_uuid segments
_CHOICE_LIKE = re.compile(r"^[a-zA-Z\- ]+$")        # for choice value
_REASON_DENY = re.compile(r"[\x00-\x1f;&()`$\\]")   # control chars + all shell metas (;|&`$()); `|` is segment separator so excluded
_MAX_LEN = 1024


def _normalize_and_validate_fix_hint(fix_hint: str | None) -> str:
    """Defensive parser layer for adversarial fix_hint inputs (Feature 116 FR-9).

    Steps:
    1. NFC-normalize unicode confusables.
    2. Reject if utf-8 byte length > 1024.
    3. Split on '|' into segments; validate each by grammar:
       - First segment: 'triage_cross_workspace_links:<uuid>:<uuid>' — UUID-like chars only.
       - 'choice:<value>' — choice value matches _CHOICE_LIKE.
       - 'reason:<value>' — free text, but reject control chars + shell metas ($, \\, `, ;, &, (, )).
    4. Reject other unknown top-level segments.

    Raises ValueError on rejection (reuses existing exception type — no new
    InvalidFixHintError class introduced).

    Returns the NFC-normalized, whitespace-stripped string.
    """
    if not fix_hint:
        return ""
    nfc = unicodedata.normalize("NFC", fix_hint)
    if len(nfc.encode("utf-8")) > _MAX_LEN:
        raise ValueError(f"fix_hint too long ({len(nfc)} chars, max {_MAX_LEN})")
    stripped = nfc.strip()
    segments = stripped.split("|")
    head = segments[0]
    if head.startswith("triage_cross_workspace_links:"):
        try:
            _, parent, child = head.split(":", 2)
        except ValueError:
            raise ValueError("fix_hint malformed: requires parent_uuid:child_uuid after prefix")
        if not _UUID_LIKE.match(parent) or not _UUID_LIKE.match(child):
            raise ValueError(f"fix_hint contains invalid character in uuid field: {head!r}")
    for seg in segments[1:]:
        if seg.startswith("choice:"):
            val = seg[len("choice:"):]
            if not _CHOICE_LIKE.match(val):
                raise ValueError(f"fix_hint contains invalid character in choice: {val!r}")
        elif seg.startswith("reason:"):
            val = seg[len("reason:"):]
            if _REASON_DENY.search(val):
                raise ValueError(f"fix_hint contains invalid character in reason: {val!r}")
        else:
            raise ValueError(f"fix_hint contains unknown segment: {seg!r}")
    return stripped


def _parse_triage_choice(fix_hint: str | None) -> dict:
    """Parse a triage choice encoded in Issue.fix_hint.

    Format options:
        "triage_cross_workspace_links:<parent_uuid>:<child_uuid>"
            (default — no choice pre-collected; caller will prompt via
            AskUserQuestion at harness layer)
        "triage_cross_workspace_links:<parent_uuid>:<child_uuid>|choice:<value>|reason:<reason>"
            (post-AskUserQuestion: choice ∈ {"re-attribute parent",
            "re-attribute child", "delete relation", "grandfather"})

    Returns dict with optional keys: choice, reason, parent_uuid, child_uuid.
    """
    result: dict[str, str | None] = {
        "choice": None, "reason": None,
        "parent_uuid": None, "child_uuid": None,
    }
    if not fix_hint:
        return result
    parts = fix_hint.split("|")
    head = parts[0]
    if head.startswith("triage_cross_workspace_links:"):
        try:
            _, parent_uuid, child_uuid = head.split(":", 2)
            result["parent_uuid"] = parent_uuid
            result["child_uuid"] = child_uuid
        except ValueError:
            pass
    for part in parts[1:]:
        if part.startswith("choice:"):
            result["choice"] = part[len("choice:"):]
        elif part.startswith("reason:"):
            result["reason"] = part[len("reason:"):]
    return result


def _execute_re_attribute_with_trigger_dance(
    conn: sqlite3.Connection,
    target_entity_uuid: str,
    target_workspace_uuid: str,
) -> None:
    """F117 FR-A.1: wrap an UPDATE entities SET workspace_uuid statement with
    sqlite_master capture/replay of the enforce_immutable_workspace_uuid
    trigger.

    Per Python 3.6+ sqlite3 semantics (bpo-27334) — CPython legacy autocommit
    mode — DDL (DROP/CREATE) autocommits immediately; the `finally` block is
    the SOLE trigger-restoration mechanism. The `with conn:` rolls back the
    UPDATE's implicit DML transaction only. Both layers are load-bearing —
    neither is optional. PyPy may diverge; F117 assumes CPython only.

    Strengthens the inline-hardcoded pattern at
    entity_registry/database.py:7956-7975 (claim_unknown_entities) by
    capturing the live trigger SQL from sqlite_master at call time —
    byte-identical to whatever the DB actually has, regardless of source
    drift in database.py.

    Raises RuntimeError if the trigger is not present at call time (do NOT
    silently degrade to a bare UPDATE).
    """
    trigger_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE name='enforce_immutable_workspace_uuid'"
    ).fetchone()
    if trigger_sql_row is None or not trigger_sql_row[0]:
        raise RuntimeError(
            "F117 FR-A.1: enforce_immutable_workspace_uuid trigger not "
            "found in sqlite_master; cannot safely drop/recreate. "
            "Aborting re-attribute."
        )
    captured_sql = trigger_sql_row[0]

    with conn:
        conn.execute(
            "DROP TRIGGER IF EXISTS enforce_immutable_workspace_uuid"
        )
        try:
            conn.execute(
                "UPDATE entities SET workspace_uuid = ? WHERE uuid = ?",
                (target_workspace_uuid, target_entity_uuid),
            )
        finally:
            conn.execute(captured_sql)


def _fix_triage_cross_workspace_link(ctx: FixContext, issue: Issue) -> str:
    """Feature 115 C14-115 / IF-8: triage a single cross-workspace parent_uuid link.

    Per spec FR-E.2.2: harness presents AskUserQuestion with 4 options before
    invoking this function and encodes the choice in issue.fix_hint:
        - "re-attribute parent": UPDATE parent.workspace_uuid = child.workspace_uuid
        - "re-attribute child": UPDATE child.workspace_uuid = parent.workspace_uuid
        - "delete relation": UPDATE child SET parent_uuid = NULL
        - "grandfather": INSERT INTO cross_workspace_allowlist (with reason)

    The fix function is a pure mutation: harness handles UI consent + choice.
    """
    if ctx.entities_conn is None:
        raise RuntimeError("entities_conn not available")
    # Feature 116 FR-9: validate + normalize before parsing.
    normalized_hint = _normalize_and_validate_fix_hint(issue.fix_hint)
    choice_info = _parse_triage_choice(normalized_hint)
    parent_uuid = choice_info["parent_uuid"]
    child_uuid = choice_info["child_uuid"] or issue.entity
    choice = choice_info["choice"]
    if not parent_uuid or not child_uuid:
        raise ValueError(
            f"triage fix requires parent_uuid:child_uuid in issue.fix_hint; "
            f"got fix_hint={issue.fix_hint!r}"
        )
    if not choice:
        raise ValueError(
            "triage fix requires choice:<value> in issue.fix_hint after the "
            "AskUserQuestion harness collects the operator decision; got "
            f"fix_hint={issue.fix_hint!r}"
        )

    row = ctx.entities_conn.execute(
        "SELECT e.workspace_uuid AS child_ws, p.workspace_uuid AS parent_ws "
        "FROM entities e LEFT JOIN entities p ON e.parent_uuid = p.uuid "
        "WHERE e.uuid = ?",
        (child_uuid,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Child entity {child_uuid} not found")
    child_ws = row[0] if not hasattr(row, "keys") else row["child_ws"]
    parent_ws = row[1] if not hasattr(row, "keys") else row["parent_ws"]

    if choice == "re-attribute parent":
        _execute_re_attribute_with_trigger_dance(
            ctx.entities_conn, parent_uuid, child_ws
        )
        action = f"re-attributed parent {parent_uuid} → workspace {child_ws}"
    elif choice == "re-attribute child":
        _execute_re_attribute_with_trigger_dance(
            ctx.entities_conn, child_uuid, parent_ws
        )
        action = f"re-attributed child {child_uuid} → workspace {parent_ws}"
    elif choice == "delete relation":
        ctx.entities_conn.execute(
            "UPDATE entities SET parent_uuid = NULL WHERE uuid = ?",
            (child_uuid,),
        )
        action = f"deleted parent_uuid on {child_uuid}"
    elif choice == "grandfather":
        reason = choice_info.get("reason") or "operator-grandfathered (no reason supplied)"
        ctx.entities_conn.execute(
            "INSERT OR IGNORE INTO cross_workspace_allowlist "
            "(parent_uuid, child_uuid, reason) VALUES (?, ?, ?)",
            (parent_uuid, child_uuid, reason),
        )
        action = f"grandfathered pair ({parent_uuid}, {child_uuid}): {reason}"
    else:
        raise ValueError(f"Unknown triage choice: {choice!r}")

    ctx.entities_conn.commit()
    return action


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
