"""MCP workflow-engine server for phase read/write operations.

Runs as a subprocess via stdio transport.  Never print to stdout
(corrupts JSON-RPC protocol) -- all logging goes to stderr.
"""
from __future__ import annotations

import functools
import json
import os
import sqlite3
import sys
from contextlib import asynccontextmanager

# Make workflow_engine, transition_gate, entity_registry, semantic_memory
# importable from hooks/lib/ — safety net for direct invocation and tests.
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

from entity_registry.database import EntityDatabase
from entity_registry.entity_lifecycle import (
    init_entity_workflow as _lib_init_entity_workflow,
    transition_entity_phase as _lib_transition_entity_phase,
)
from entity_registry.frontmatter_sync import (
    ARTIFACT_BASENAME_MAP,
    DriftReport,
    detect_drift,
    scan_all,
)
from semantic_memory.config import read_config
from transition_gate.models import Severity, TransitionResult
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.entity_engine import EntityWorkflowEngine
from workflow_engine.feature_lifecycle import (
    _atomic_json_write,
    _iso_now,
    _validate_feature_type_id,
    activate_feature as _lib_activate_feature,
    init_feature_state as _lib_init_feature_state,
    init_project_state as _lib_init_project_state,
)
from workflow_engine.kanban import derive_kanban
from workflow_engine.task_promotion import (
    TaskAlreadyPromotedError,
    TaskNotFoundError,
    promote_task as _lib_promote_task,
    query_ready_tasks as _lib_query_ready_tasks,
)
from workflow_engine.models import FeatureWorkflowState, TransitionResponse
from workflow_engine.notifications import NotificationQueue
from workflow_engine.reconciliation import (
    ReconcileAction,
    WorkflowDriftReport,
    apply_workflow_reconciliation,
    check_workflow_drift,
)

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Module-level globals (set during lifespan)
# ---------------------------------------------------------------------------

_db: EntityDatabase | None = None
_engine: WorkflowStateEngine | None = None
_entity_engine: EntityWorkflowEngine | None = None
_artifacts_root: str = ""
_project_root: str = ""
_notification_queue: NotificationQueue | None = None

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server):
    """Manage DB connection and engine lifecycle."""
    global _db, _engine, _entity_engine, _artifacts_root, _project_root, _notification_queue

    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/pd/entities/entities.db"),
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    _db = EntityDatabase(db_path)

    project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
    _project_root = project_root
    config = read_config(project_root)
    _artifacts_root = os.path.join(project_root, str(config.get("artifacts_root", "docs")))

    _engine = WorkflowStateEngine(_db, _artifacts_root)
    _notification_queue = NotificationQueue()
    _entity_engine = EntityWorkflowEngine(_db, _artifacts_root, _notification_queue)

    print(f"workflow-engine: started (db={db_path}, artifacts={_artifacts_root})", file=sys.stderr)

    try:
        yield {}
    finally:
        if _db is not None:
            _db.close()
            _db = None
        _engine = None
        _entity_engine = None
        _notification_queue = None


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_state(state: FeatureWorkflowState) -> dict:
    """Convert FeatureWorkflowState to JSON-serializable dict."""
    return {
        "feature_type_id": state.feature_type_id,
        "current_phase": state.current_phase,
        "last_completed_phase": state.last_completed_phase,
        "mode": state.mode,
        "degraded": state.source == "meta_json_fallback",
    }


def _serialize_result(result: TransitionResult) -> dict:
    """Convert TransitionResult to JSON-serializable dict.

    guard_id is always a non-None string — the engine guarantees this
    for all gate evaluations.
    """
    return {
        "allowed": result.allowed,
        "reason": result.reason,
        "severity": result.severity.value,
        "guard_id": result.guard_id,
    }


def _serialize_workflow_drift_report(report: WorkflowDriftReport) -> dict:
    """Convert WorkflowDriftReport to JSON-serializable dict."""
    return {
        "feature_type_id": report.feature_type_id,
        "status": report.status,
        "meta_json": report.meta_json,
        "db": report.db,
        "mismatches": [
            {"field": m.field, "meta_json_value": m.meta_json_value, "db_value": m.db_value}
            for m in report.mismatches
        ],
    }


def _serialize_reconcile_action(action: ReconcileAction) -> dict:
    """Convert ReconcileAction to JSON-serializable dict.

    For meta_json_to_db direction: old_value = DB (being overwritten),
    new_value = .meta.json (source of truth).
    """
    return {
        "feature_type_id": action.feature_type_id,
        "action": action.action,
        "direction": action.direction,
        "changes": [
            {"field": c.field, "old_value": c.db_value, "new_value": c.meta_json_value}
            for c in action.changes
        ],
        "message": action.message,
    }


def _serialize_drift_report(report: DriftReport) -> dict:
    """Convert frontmatter_sync.DriftReport to JSON-serializable dict."""
    return {
        "filepath": report.filepath,
        "type_id": report.type_id,
        "status": report.status,
        "file_fields": report.file_fields,
        "db_fields": report.db_fields,
        "mismatches": [
            {"field": m.field, "file_value": m.file_value, "db_value": m.db_value}
            for m in report.mismatches
        ],
    }


def _build_frontmatter_summary(reports: list[DriftReport]) -> dict[str, int]:
    """Count frontmatter drift reports by status."""
    summary: dict[str, int] = {
        "in_sync": 0, "file_only": 0, "db_only": 0,
        "diverged": 0, "no_header": 0, "error": 0,
    }
    for r in reports:
        if r.status in summary:
            summary[r.status] += 1
        else:
            summary["error"] += 1
    return summary


# ---------------------------------------------------------------------------
# Projection function
# ---------------------------------------------------------------------------


def _project_meta_json(
    db: EntityDatabase,
    engine: WorkflowStateEngine | None,
    feature_type_id: str,
    feature_dir: str | None = None,
) -> str | None:
    """Regenerate .meta.json from DB + engine state. Returns warning string or None.

    Uses engine.get_state() as authoritative source for last_completed_phase
    and current_phase. Falls back to entity metadata if engine is None or
    engine state unavailable. Phase timing details (iterations, reviewerNotes)
    come from entity metadata only (engine doesn't track these).
    """
    entity = db.get_entity(feature_type_id)
    if entity is None:
        return f"entity not found: {feature_type_id}"

    if feature_dir is None:
        feature_dir = entity.get("artifact_path")
        if not feature_dir:
            return f"artifact_path not set and no feature_dir provided: {feature_type_id}"

    meta_path = os.path.join(feature_dir, ".meta.json")

    # Parse metadata -- it's a JSON TEXT column, not a dict
    raw_metadata = entity.get("metadata")
    if raw_metadata:
        metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
    else:
        metadata = {}

    phase_timing = metadata.get("phase_timing", {})

    # Get authoritative state from engine when available
    if engine is not None:
        engine_state = engine.get_state(feature_type_id)
        last_completed = (
            engine_state.last_completed_phase if engine_state else None
        )
    else:
        last_completed = metadata.get("last_completed_phase")

    # Build .meta.json structure
    meta = {
        "id": metadata.get("id", ""),
        "slug": metadata.get("slug", ""),
        "mode": metadata.get("mode", "standard"),
        "status": entity.get("status") or "active",
        "created": entity.get("created_at") or _iso_now(),
        "branch": metadata.get("branch", ""),
    }

    # Top-level completed timestamp for terminal statuses (R1/R2/R4)
    # Also trigger on last_completed == "finish" as a defensive fallback
    # when entity status hasn't propagated yet (e.g., status=None in DB).
    if meta["status"] in ("completed", "abandoned") or last_completed == "finish":
        finish_completed = phase_timing.get("finish", {}).get("completed")
        meta["completed"] = finish_completed or _iso_now()

    # Optional fields -- only include when present
    if metadata.get("brainstorm_source"):
        meta["brainstorm_source"] = metadata["brainstorm_source"]
    if metadata.get("backlog_source"):
        meta["backlog_source"] = metadata["backlog_source"]

    # Workflow state (engine is authoritative when available)
    meta["lastCompletedPhase"] = last_completed

    # Phases from phase_timing metadata
    phases = {}
    for phase_name, timing in phase_timing.items():
        phase_entry = {}
        if timing.get("started"):
            phase_entry["started"] = timing["started"]
        if timing.get("completed"):
            phase_entry["completed"] = timing["completed"]
        if timing.get("iterations") is not None:
            phase_entry["iterations"] = timing["iterations"]
        if timing.get("reviewerNotes"):
            phase_entry["reviewerNotes"] = timing["reviewerNotes"]
        if phase_entry:
            phases[phase_name] = phase_entry
    meta["phases"] = phases

    # Skipped phases
    if metadata.get("skipped_phases"):
        meta["skippedPhases"] = metadata["skipped_phases"]

    # Atomic write (fail-open)
    try:
        _atomic_json_write(meta_path, meta)
        return None  # success
    except Exception as exc:
        return f"projection failed: {exc}"


# ---------------------------------------------------------------------------
# Processing functions
# ---------------------------------------------------------------------------


def _make_error(error_type: str, message: str, recovery_hint: str) -> str:
    """Create structured JSON error response for MCP tools."""
    return json.dumps({
        "error": True,
        "error_type": error_type,
        "message": message,
        "recovery_hint": recovery_hint,
    })


def _with_error_handling(func):
    """Wrap _process_* functions with standard DB/internal error handling."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except sqlite3.Error as exc:
            return _make_error(
                "db_unavailable",
                f"Database error: {type(exc).__name__}: {exc}",
                "Check database file permissions and disk space",
            )
        except Exception as exc:
            return _make_error(
                "internal",
                f"Internal error: {type(exc).__name__}: {exc}",
                "Report this error — it may indicate a bug",
            )
    return wrapper


def _catch_value_error(func):
    """Wrap functions that raise ValueError for invalid user input.

    Prefix-based routing: checks for "feature_not_found:" prefix first
    (new convention from _validate_feature_type_id), then falls back to
    substring match for "not found" (existing engine.py convention).
    All other ValueErrors map to 'invalid_transition'.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as exc:
            msg = str(exc)
            if msg.startswith("feature_not_found:") or "not found" in msg.lower():
                return _make_error(
                    "feature_not_found",
                    msg,
                    "Verify feature_type_id format: 'feature:{id}-{slug}'",
                )
            return _make_error(
                "invalid_transition",
                msg,
                "Check current phase with get_phase before transitioning",
            )
    return wrapper


_ENTITY_RECOVERY_HINTS = {
    "entity_not_found": "Verify type_id exists via get_entity",
    "invalid_entity_type": "Only brainstorm and backlog entities support lifecycle transitions",
    "invalid_transition": "Check current phase — transition may not be valid from current state",
}


def _catch_entity_value_error(func):
    """Map entity-related ValueErrors to structured error dicts."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            msg = str(e)
            for prefix in ("entity_not_found:", "invalid_entity_type:", "invalid_transition:"):
                if msg.startswith(prefix):
                    error_type = prefix.rstrip(":")
                    return _make_error(error_type, msg, _ENTITY_RECOVERY_HINTS.get(error_type, ""))
            raise
    return wrapper



@_with_error_handling
def _process_get_phase(engine: WorkflowStateEngine, feature_type_id: str) -> str:
    state = engine.get_state(feature_type_id)
    if state is None:
        return _make_error(
            "feature_not_found",
            f"Feature not found: {feature_type_id}",
            "Verify feature_type_id format: 'feature:{id}-{slug}'",
        )
    return json.dumps(_serialize_state(state))


@_with_error_handling
@_catch_value_error
def _process_transition_phase(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    target_phase: str,
    yolo_active: bool,
    db: EntityDatabase | None = None,
    skipped_phases: str | None = None,
    entity_engine: EntityWorkflowEngine | None = None,
) -> str:
    # Task 3.4: Check blocked_by via entity engine before transition.
    # For features, we still delegate to frozen engine for the actual transition
    # (entity_engine.transition_phase checks blockers then delegates).
    if entity_engine is not None and db is not None:
        entity = db.get_entity(feature_type_id)
        if entity is not None:
            try:
                response = entity_engine.transition_phase(entity["uuid"], target_phase)
            except ValueError as exc:
                # Blocked or invalid — return as structured error
                return _make_error(
                    "invalid_transition",
                    str(exc),
                    "Check blocked_by dependencies or current phase",
                )
        else:
            response = engine.transition_phase(feature_type_id, target_phase, yolo_active)
    else:
        response = engine.transition_phase(feature_type_id, target_phase, yolo_active)
    transitioned = all(r.allowed for r in response.results)

    result: dict = {
        "transitioned": transitioned,
        "results": [_serialize_result(r) for r in response.results],
        "degraded": response.degraded,
    }

    if transitioned and db is not None:
        # Store phase timing in entity metadata
        entity = db.get_entity(feature_type_id)
        raw_metadata = entity.get("metadata") if entity else None
        if raw_metadata:
            metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
        else:
            metadata = {}

        phase_timing = metadata.get("phase_timing", {})
        phase_timing.setdefault(target_phase, {})
        phase_timing[target_phase]["started"] = _iso_now()
        metadata["phase_timing"] = phase_timing

        # Store skipped phases if provided
        if skipped_phases:
            metadata["skipped_phases"] = json.loads(skipped_phases)

        db.update_entity(feature_type_id, metadata=metadata)

        # Update kanban_column for features based on phase
        if feature_type_id.startswith("feature:"):
            kanban = derive_kanban("active", target_phase)
            db.update_workflow_phase(feature_type_id, kanban_column=kanban)

        # Project .meta.json
        warning = _project_meta_json(db, engine, feature_type_id)

        result["started_at"] = phase_timing[target_phase]["started"]
        if skipped_phases:
            result["skipped_phases_stored"] = True
        if warning:
            result["projection_warning"] = warning

    return json.dumps(result)


# ---------------------------------------------------------------------------
# Artifact completeness check (AC-5)
# ---------------------------------------------------------------------------

# Expected artifacts per mode for finish-phase completeness warning.
# Light mode deferred to task 1b.10.
_EXPECTED_ARTIFACTS: dict[str, list[str]] = {
    "standard": ["spec.md", "tasks.md", "retro.md"],
    "full": ["spec.md", "design.md", "plan.md", "tasks.md", "retro.md"],
    "light": ["spec.md"],
}


def _check_artifact_completeness(
    db: EntityDatabase,
    feature_type_id: str,
) -> list[str]:
    """Check for missing expected artifacts on finish. Returns list of warnings."""
    entity = db.get_entity(feature_type_id)
    if entity is None:
        return []

    artifact_path = entity.get("artifact_path")
    if not artifact_path or not os.path.isdir(artifact_path):
        return []

    # Read mode from workflow_phases table
    wf = db.get_workflow_phase(feature_type_id)
    mode = (wf.get("mode") if wf else None) or "standard"

    expected = _EXPECTED_ARTIFACTS.get(mode)
    if expected is None:
        return []

    missing = [
        name for name in expected
        if not os.path.isfile(os.path.join(artifact_path, name))
    ]

    return [f"Missing artifact: {name}" for name in missing]


@_with_error_handling
@_catch_value_error
def _process_complete_phase(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    phase: str,
    db: EntityDatabase | None = None,
    iterations: int | None = None,
    reviewer_notes: str | None = None,
    entity_engine: EntityWorkflowEngine | None = None,
) -> str:
    # Task 3.4: Route through EntityWorkflowEngine for cascade support.
    # If entity_engine is available, use it (handles frozen engine delegation
    # + cascade internally). Fall back to frozen engine if not wired yet.
    completion = None
    if entity_engine is not None and db is not None:
        entity = db.get_entity(feature_type_id)
        if entity is not None:
            completion = entity_engine.complete_phase(entity["uuid"], phase)
            state = completion.state
            if state is None:
                return _make_error(
                    "completion_failed",
                    f"Phase completion returned no state for {feature_type_id}",
                    "Check entity type and phase validity",
                )
        else:
            # Entity not in registry — fall back to frozen engine
            state = engine.complete_phase(feature_type_id, phase)
    else:
        state = engine.complete_phase(feature_type_id, phase)

    result = _serialize_state(state)

    # Add cascade info when entity engine was used
    if completion is not None:
        if completion.unblocked_uuids:
            result["unblocked_count"] = len(completion.unblocked_uuids)
        if completion.parent_progress is not None:
            result["parent_progress"] = completion.parent_progress
        if completion.cascade_error:
            result["cascade_warning"] = completion.cascade_error

    if db is not None:
        # Store timing metadata in entity (MCP-layer responsibility)
        entity = db.get_entity(feature_type_id)
        if entity is None:
            return _make_error(
                "feature_not_found",
                f"Feature not found after completion: {feature_type_id}",
                "Verify feature_type_id format: 'feature:{id}-{slug}'",
            )

        raw_metadata = entity.get("metadata")
        if raw_metadata:
            metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
        else:
            metadata = {}

        phase_timing = metadata.get("phase_timing", {})
        phase_timing.setdefault(phase, {})
        phase_timing[phase]["completed"] = _iso_now()
        if iterations is not None:
            phase_timing[phase]["iterations"] = iterations
        if reviewer_notes:
            phase_timing[phase]["reviewerNotes"] = json.loads(reviewer_notes)
        metadata["phase_timing"] = phase_timing
        metadata["last_completed_phase"] = phase

        # Update entity metadata (status='completed' handled by entity engine
        # for features via frozen engine, and for tasks via _task_complete)
        db.update_entity(feature_type_id, metadata=metadata)

        # Update kanban_column for features based on completed phase
        if feature_type_id.startswith("feature:"):
            status = "completed" if phase == "finish" else "active"
            kanban = derive_kanban(status, state.current_phase)
            db.update_workflow_phase(feature_type_id, kanban_column=kanban)

        # Project .meta.json
        warning = _project_meta_json(db, engine, feature_type_id)

        result["completed_at"] = phase_timing[phase]["completed"]
        if warning:
            result["projection_warning"] = warning

        # Artifact completeness warning on finish (AC-5)
        if phase == "finish":
            artifact_warnings = _check_artifact_completeness(
                db, feature_type_id,
            )
            if artifact_warnings:
                result["artifact_warnings"] = artifact_warnings

    return json.dumps(result)


@_with_error_handling
@_catch_value_error
def _process_validate_prerequisites(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    target_phase: str,
) -> str:
    results = engine.validate_prerequisites(feature_type_id, target_phase)
    all_passed = all(r.allowed for r in results)
    return json.dumps({
        "all_passed": all_passed,
        "results": [_serialize_result(r) for r in results],
    })


@_with_error_handling
def _process_list_features_by_phase(engine: WorkflowStateEngine, phase: str) -> str:
    states = engine.list_by_phase(phase)
    return json.dumps([_serialize_state(s) for s in states])


@_with_error_handling
def _process_list_features_by_status(engine: WorkflowStateEngine, status: str) -> str:
    states = engine.list_by_status(status)
    return json.dumps([_serialize_state(s) for s in states])


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Reconciliation processing functions
# ---------------------------------------------------------------------------


@_with_error_handling
@_catch_value_error
def _process_reconcile_check(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None,
) -> str:
    """Workflow drift detection. Returns JSON string.

    Note: Single-feature db_only is unreachable via MCP — _validate_feature_type_id
    requires the directory to exist (spec I7), so a feature with a DB row but no
    filesystem directory returns feature_not_found. db_only is only observable
    through the bulk scan path (feature_type_id=None).
    """
    if feature_type_id is not None:
        _validate_feature_type_id(feature_type_id, artifacts_root)
    result = check_workflow_drift(engine, db, artifacts_root, feature_type_id)
    return json.dumps({
        "features": [_serialize_workflow_drift_report(r) for r in result.features],
        "summary": result.summary,
    })


@_with_error_handling
@_catch_value_error
def _process_reconcile_apply(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None,
    dry_run: bool,
) -> str:
    """Workflow reconciliation. Hardcodes meta_json_to_db direction, returns JSON string."""
    if feature_type_id is not None:
        _validate_feature_type_id(feature_type_id, artifacts_root)
    result = apply_workflow_reconciliation(
        engine, db, artifacts_root, feature_type_id, dry_run
    )
    return json.dumps({
        "actions": [_serialize_reconcile_action(a) for a in result.actions],
        "summary": result.summary,
    })


@_with_error_handling
@_catch_value_error
def _process_reconcile_frontmatter(
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None,
) -> str:
    """Frontmatter drift detection. Returns JSON string."""
    if feature_type_id is None:
        reports: list[DriftReport] = scan_all(db, artifacts_root)
    else:
        slug = _validate_feature_type_id(feature_type_id, artifacts_root)
        feat_dir = os.path.join(artifacts_root, "features", slug)
        reports = []
        if os.path.isdir(feat_dir):
            for basename in ARTIFACT_BASENAME_MAP:
                filepath = os.path.join(feat_dir, basename)
                if os.path.isfile(filepath):
                    report = detect_drift(db, filepath, type_id=feature_type_id)
                    reports.append(report)

    drifted = [r for r in reports if r.status != "in_sync"]
    return json.dumps({
        "total_scanned": len(reports),
        "drifted_count": len(drifted),
        "reports": [_serialize_drift_report(r) for r in drifted],
    })


@_with_error_handling
@_catch_value_error
def _process_init_feature_state(
    db: EntityDatabase,
    engine: WorkflowStateEngine | None,
    feature_dir: str,
    feature_id: str,
    slug: str,
    mode: str,
    branch: str,
    brainstorm_source: str | None,
    backlog_source: str | None,
    status: str,
    *,
    artifacts_root: str,
) -> str:
    """Thin wrapper — delegates to feature_lifecycle.init_feature_state."""
    result = _lib_init_feature_state(
        db=db,
        engine=engine,
        artifacts_root=artifacts_root,
        feature_dir=feature_dir,
        feature_id=feature_id,
        slug=slug,
        mode=mode,
        branch=branch,
        brainstorm_source=brainstorm_source,
        backlog_source=backlog_source,
        status=status,
    )
    warning = _project_meta_json(db, engine, result["feature_type_id"], feature_dir)
    if warning:
        result["projection_warning"] = warning
    return json.dumps(result)


@_with_error_handling
@_catch_value_error
def _process_init_project_state(
    db: EntityDatabase,
    project_dir: str,
    project_id: str,
    slug: str,
    features: str,  # JSON string
    milestones: str,  # JSON string
    brainstorm_source: str | None,
) -> str:
    """Thin wrapper — delegates to feature_lifecycle.init_project_state."""
    result = _lib_init_project_state(
        db=db,
        artifacts_root=_artifacts_root,
        project_dir=project_dir,
        project_id=project_id,
        slug=slug,
        branch="",  # Not used in original project init path
        features=features,
        milestones=milestones,
        brainstorm_source=brainstorm_source,
    )
    return json.dumps(result)


@_with_error_handling
@_catch_value_error
def _process_activate_feature(
    db: EntityDatabase,
    engine: WorkflowStateEngine,
    feature_type_id: str,
    artifacts_root: str,
) -> str:
    """Thin wrapper — delegates to feature_lifecycle.activate_feature."""
    result = _lib_activate_feature(
        db=db,
        engine=engine,
        artifacts_root=artifacts_root,
        feature_type_id=feature_type_id,
    )
    warning = _project_meta_json(db, engine, result["feature_type_id"])
    if warning:
        result["projection_warning"] = warning
    return json.dumps(result)


@_with_error_handling
@_catch_entity_value_error
def _process_init_entity_workflow(
    db: EntityDatabase, type_id: str, workflow_phase: str, kanban_column: str
) -> str:
    """Thin wrapper — delegates to entity_lifecycle.init_entity_workflow."""
    return json.dumps(_lib_init_entity_workflow(db, type_id, workflow_phase, kanban_column))


@_with_error_handling
@_catch_entity_value_error
def _process_transition_entity_phase(
    db: EntityDatabase, type_id: str, target_phase: str
) -> str:
    """Thin wrapper — delegates to entity_lifecycle.transition_entity_phase."""
    return json.dumps(_lib_transition_entity_phase(db, type_id, target_phase))


@_with_error_handling
def _process_reconcile_status(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    summary_only: bool = False,
) -> str:
    """Combined drift report. Returns JSON string.

    When summary_only=True, returns a compact 3-field response:
    {"healthy": bool, "workflow_drift_count": int, "frontmatter_drift_count": int}
    """
    # Workflow drift
    workflow_result = check_workflow_drift(engine, db, artifacts_root)

    # Frontmatter drift
    frontmatter_reports = scan_all(db, artifacts_root)

    if summary_only:
        wf_drift = sum(
            1 for r in workflow_result.features if r.status != "in_sync"
        )
        fm_drift = sum(
            1 for r in frontmatter_reports if r.status != "in_sync"
        )
        return json.dumps({
            "healthy": wf_drift == 0,
            "workflow_drift_count": wf_drift,
            "frontmatter_drift_count": fm_drift,
        })

    fm_summary = _build_frontmatter_summary(frontmatter_reports)

    # Healthy: workflow drift only (frontmatter drift excluded per AC-2,
    # artifact_missing_count excluded — informational, not a health issue)
    _HEALTH_EXCLUDED = {"in_sync", "artifact_missing_count"}
    wf_healthy = all(
        v == 0 for k, v in workflow_result.summary.items() if k not in _HEALTH_EXCLUDED
    )
    healthy = wf_healthy

    return json.dumps({
        "workflow_drift": {
            "features": [
                _serialize_workflow_drift_report(r) for r in workflow_result.features
            ],
            "summary": workflow_result.summary,
        },
        "frontmatter_drift": {
            "reports": [_serialize_drift_report(r) for r in frontmatter_reports],
            "summary": fm_summary,
        },
        "healthy": healthy,
        "total_features_checked": len(workflow_result.features),
        "total_files_checked": len(frontmatter_reports),
    })


# ---------------------------------------------------------------------------
# Ref resolution helper (Task 1b.5)
# ---------------------------------------------------------------------------


def _resolve_ref_to_feature_type_id(
    db: EntityDatabase,
    feature_type_id: str | None,
    ref: str | None,
) -> str:
    """Resolve a feature_type_id or ref to a concrete feature_type_id.

    Parameters
    ----------
    db:
        Open EntityDatabase.
    feature_type_id:
        Explicit feature_type_id (takes precedence if provided).
    ref:
        Flexible reference: UUID, full type_id, or type_id prefix.

    Returns
    -------
    str
        The resolved feature_type_id.

    Raises
    ------
    ValueError
        If neither param provided, ref not found, or ambiguous.
    """
    if feature_type_id is not None:
        return feature_type_id
    if ref is None:
        raise ValueError("Either feature_type_id or ref must be provided")

    entity_uuid = db.resolve_ref(ref)
    entity = db.get_entity_by_uuid(entity_uuid)
    if entity is None:
        raise ValueError(f"No entity found matching ref: {ref!r}")
    return entity["type_id"]


# ---------------------------------------------------------------------------
# MCP tool handlers
# ---------------------------------------------------------------------------

_NOT_INITIALIZED = _make_error(
    "not_initialized",
    "Engine not initialized (server not started)",
    "Wait for server startup or restart the MCP server",
)

mcp = FastMCP("workflow-engine", lifespan=lifespan)


@mcp.tool()
async def get_phase(feature_type_id: str | None = None, ref: str | None = None) -> str:
    """Read the current workflow state for a feature."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, feature_type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid feature_type_id or ref")
    return _process_get_phase(_engine, resolved)


@mcp.tool()
async def transition_phase(
    feature_type_id: str | None = None,
    target_phase: str = "",
    yolo_active: bool = False,
    skipped_phases: str | None = None,
    ref: str | None = None,
) -> str:
    """Validate and enter a target phase."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, feature_type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid feature_type_id or ref")
    return _process_transition_phase(
        _engine, resolved, target_phase, yolo_active,
        db=_db, skipped_phases=skipped_phases,
        entity_engine=_entity_engine,
    )


@mcp.tool()
async def complete_phase(
    feature_type_id: str | None = None,
    phase: str = "",
    iterations: int | None = None,
    reviewer_notes: str | None = None,
    ref: str | None = None,
) -> str:
    """Record a phase as completed and advance to next phase."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, feature_type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid feature_type_id or ref")
    return _process_complete_phase(
        _engine, resolved, phase,
        db=_db, iterations=iterations, reviewer_notes=reviewer_notes,
        entity_engine=_entity_engine,
    )


@mcp.tool()
async def validate_prerequisites(
    feature_type_id: str | None = None,
    target_phase: str = "",
    ref: str | None = None,
) -> str:
    """Dry-run gate evaluation without executing the transition."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, feature_type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid feature_type_id or ref")
    return _process_validate_prerequisites(_engine, resolved, target_phase)


@mcp.tool()
async def list_features_by_phase(phase: str) -> str:
    """All features currently in a given workflow phase."""
    if _engine is None:
        return _NOT_INITIALIZED
    return _process_list_features_by_phase(_engine, phase)


@mcp.tool()
async def list_features_by_status(status: str) -> str:
    """All features with a given entity status."""
    if _engine is None:
        return _NOT_INITIALIZED
    return _process_list_features_by_status(_engine, status)


@mcp.tool()
async def reconcile_check(feature_type_id: str | None = None) -> str:
    """Compare .meta.json workflow state against DB for drift detection."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_check(_engine, _db, _artifacts_root, feature_type_id)


@mcp.tool()
async def reconcile_apply(
    feature_type_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Sync .meta.json workflow state to DB for features where .meta.json is ahead."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_apply(
        _engine, _db, _artifacts_root, feature_type_id, dry_run
    )


@mcp.tool()
async def reconcile_frontmatter(feature_type_id: str | None = None) -> str:
    """Check frontmatter headers against DB entity records for drift."""
    if _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_frontmatter(_db, _artifacts_root, feature_type_id)


@mcp.tool()
async def reconcile_status(summary_only: bool = False) -> str:
    """Unified health report across workflow state and frontmatter drift."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_status(_engine, _db, _artifacts_root, summary_only=summary_only)


@mcp.tool()
async def init_feature_state(
    feature_dir: str,
    feature_id: str,
    slug: str,
    mode: str,
    branch: str,
    brainstorm_source: str | None = None,
    backlog_source: str | None = None,
    status: str = "active",
) -> str:
    """Create initial feature state in DB and write feature .meta.json."""
    if _db is None:
        return _NOT_INITIALIZED
    return _process_init_feature_state(
        _db, _engine, feature_dir, feature_id, slug, mode, branch,
        brainstorm_source, backlog_source, status,
        artifacts_root=_artifacts_root,
    )


@mcp.tool()
async def init_project_state(
    project_dir: str,
    project_id: str,
    slug: str,
    features: str,
    milestones: str,
    brainstorm_source: str | None = None,
) -> str:
    """Create initial project state in DB and write project .meta.json."""
    if _db is None:
        return _NOT_INITIALIZED
    return _process_init_project_state(
        _db, project_dir, project_id, slug, features, milestones, brainstorm_source
    )


@mcp.tool()
async def activate_feature(feature_type_id: str | None = None, ref: str | None = None) -> str:
    """Transition a planned feature to active status."""
    if _db is None or _engine is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, feature_type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid feature_type_id or ref")
    return _process_activate_feature(_db, _engine, resolved, _artifacts_root)


@mcp.tool()
async def init_entity_workflow(
    type_id: str | None = None,
    workflow_phase: str = "",
    kanban_column: str = "",
    ref: str | None = None,
) -> str:
    """Create a workflow_phases row for any entity type."""
    if _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid type_id or ref")
    return _process_init_entity_workflow(_db, resolved, workflow_phase, kanban_column)


@mcp.tool()
async def transition_entity_phase(
    type_id: str | None = None,
    target_phase: str = "",
    ref: str | None = None,
) -> str:
    """Transition a brainstorm or backlog entity to a new lifecycle phase."""
    if _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid type_id or ref")
    return _process_transition_entity_phase(_db, resolved, target_phase)


@mcp.tool()
async def get_notifications(project_root: str | None = None) -> str:
    """Drain pending notifications for the current project.

    Returns notifications queued by entity state changes (phase completions,
    threshold crossings, etc.). Drained notifications are removed from the
    queue so each notification is delivered exactly once.
    """
    if _notification_queue is None:
        return _NOT_INITIALIZED
    root = project_root or _project_root
    if not root:
        return _make_error(
            "missing_project_root",
            "No project_root provided and PROJECT_ROOT not set",
            "Pass project_root or set PROJECT_ROOT env var",
        )
    notifications = _notification_queue.drain(project_root=root)
    return json.dumps({
        "project_root": root,
        "count": len(notifications),
        "notifications": [
            {
                "message": n.message,
                "entity_type_id": n.entity_type_id,
                "event": n.event,
                "timestamp": n.timestamp,
            }
            for n in notifications
        ],
    })


@mcp.tool()
async def promote_task(feature_ref: str, task_heading: str) -> str:
    """Promote a task from tasks.md to a tracked task entity.

    Fuzzy-matches task_heading against headings in tasks.md, creates a task
    entity with parent=feature, status=planned, and links dependencies.
    """
    if _db is None:
        return _NOT_INITIALIZED
    try:
        result = _lib_promote_task(_db, feature_ref, task_heading)
        return json.dumps(result)
    except (TaskNotFoundError, TaskAlreadyPromotedError) as exc:
        return _make_error(type(exc).__name__, str(exc), "Check heading text or use exact heading from tasks.md")
    except (ValueError, FileNotFoundError) as exc:
        return _make_error("invalid_input", str(exc), "Provide valid feature_ref and ensure tasks.md exists")


@mcp.tool()
async def query_ready_tasks() -> str:
    """List task entities ready for execution.

    Returns tasks that are: type=task, status=planned, no blocked_by
    dependencies, and parent entity in implement phase.
    """
    if _db is None:
        return _NOT_INITIALIZED
    try:
        tasks = _lib_query_ready_tasks(_db)
        return json.dumps({"count": len(tasks), "tasks": tasks})
    except Exception as exc:
        return _make_error("internal", str(exc), "Report this error")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
