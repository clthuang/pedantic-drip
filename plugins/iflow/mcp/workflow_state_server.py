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
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone

# Make workflow_engine, transition_gate, entity_registry, semantic_memory
# importable from hooks/lib/ — safety net for direct invocation and tests.
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

from entity_registry.database import EntityDatabase
from entity_registry.frontmatter_sync import (
    ARTIFACT_BASENAME_MAP,
    DriftReport,
    detect_drift,
    scan_all,
)
from semantic_memory.config import read_config
from transition_gate.models import Severity, TransitionResult
from workflow_engine.constants import FEATURE_PHASE_TO_KANBAN
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.models import FeatureWorkflowState, TransitionResponse
from workflow_engine.reconciliation import (
    ReconcileAction,
    WorkflowDriftReport,
    apply_workflow_reconciliation,
    check_workflow_drift,
)

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Entity lifecycle state machines — single registry keyed by entity_type.
# Each entry defines: valid transitions, phase-to-kanban-column mapping,
# and forward transition set (for last_completed_phase updates).
# ---------------------------------------------------------------------------

ENTITY_MACHINES: dict[str, dict] = {
    "brainstorm": {
        "transitions": {
            "draft": ["reviewing", "abandoned"],
            "reviewing": ["promoted", "draft", "abandoned"],
        },
        "columns": {
            "draft": "wip",
            "reviewing": "agent_review",
            "promoted": "completed",
            "abandoned": "completed",
        },
        "forward": {
            ("draft", "reviewing"),
            ("reviewing", "promoted"),
            ("reviewing", "abandoned"),
            ("draft", "abandoned"),
        },
    },
    "backlog": {
        "transitions": {
            "open": ["triaged", "dropped"],
            "triaged": ["promoted", "dropped"],
        },
        "columns": {
            "open": "backlog",
            "triaged": "prioritised",
            "promoted": "completed",
            "dropped": "completed",
        },
        "forward": {
            ("open", "triaged"),
            ("triaged", "promoted"),
            ("triaged", "dropped"),
            ("open", "dropped"),
        },
    },
}

# ---------------------------------------------------------------------------
# Status-to-kanban mapping for feature init-time (matches backfill.py:35-40).
# Also referenced by scripts/fix_kanban_columns.py.
# ---------------------------------------------------------------------------

STATUS_TO_KANBAN: dict[str, str] = {
    "active": "wip",
    "planned": "backlog",
    "completed": "completed",
    "abandoned": "completed",
}

# ---------------------------------------------------------------------------
# Module-level globals (set during lifespan)
# ---------------------------------------------------------------------------

_db: EntityDatabase | None = None
_engine: WorkflowStateEngine | None = None
_artifacts_root: str = ""

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server):
    """Manage DB connection and engine lifecycle."""
    global _db, _engine, _artifacts_root

    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/iflow/entities/entities.db"),
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    _db = EntityDatabase(db_path)

    project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
    config = read_config(project_root)
    _artifacts_root = os.path.join(project_root, str(config.get("artifacts_root", "docs")))

    _engine = WorkflowStateEngine(_db, _artifacts_root)

    print(f"workflow-engine: started (db={db_path}, artifacts={_artifacts_root})", file=sys.stderr)

    try:
        yield {}
    finally:
        if _db is not None:
            _db.close()
            _db = None
        _engine = None


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_state(state: FeatureWorkflowState) -> dict:
    """Convert FeatureWorkflowState to JSON-serializable dict."""
    return {
        "feature_type_id": state.feature_type_id,
        "current_phase": state.current_phase,
        "last_completed_phase": state.last_completed_phase,
        "completed_phases": list(state.completed_phases),
        "mode": state.mode,
        "source": state.source,
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
# Utility functions
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_write(path: str, data: dict) -> None:
    """Atomic JSON write: NamedTemporaryFile + os.replace()."""
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=os.path.dirname(path),
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as fd:
            tmp_name = fd.name
            json.dump(data, fd, indent=2)
            fd.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        raise


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


def _validate_feature_type_id(feature_type_id: str, artifacts_root: str) -> str:
    """Validate feature_type_id and extract slug with realpath defense.

    1. Split on ':', raise ValueError if no colon present
    2. Extract slug from second part
    3. Check null bytes BEFORE os.path.realpath()
    4. Resolve realpath of {artifacts_root}/features/{slug}/
    5. Verify resolved path starts with realpath(artifacts_root) + os.sep
    6. Return validated slug

    Raises ValueError on invalid input (caught by _catch_value_error).
    """
    if ":" not in feature_type_id:
        raise ValueError("invalid_input: missing colon in feature_type_id")

    slug = feature_type_id.split(":", 1)[1]

    if not slug:
        raise ValueError("feature_not_found: empty slug")

    # Check null bytes before ANY filesystem call
    if "\0" in slug:
        raise ValueError(f"feature_not_found: {slug} not found or path traversal blocked")

    candidate = os.path.join(artifacts_root, "features", slug)
    resolved = os.path.realpath(candidate)
    root = os.path.realpath(artifacts_root)

    if not resolved.startswith(root + os.sep) or not os.path.isdir(resolved):
        raise ValueError(f"feature_not_found: {slug} not found or path traversal blocked")

    return slug


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
) -> str:
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
            kanban = FEATURE_PHASE_TO_KANBAN.get(target_phase)
            if kanban:
                db.update_workflow_phase(feature_type_id, kanban_column=kanban)

        # Project .meta.json
        warning = _project_meta_json(db, engine, feature_type_id)

        result["started_at"] = phase_timing[target_phase]["started"]
        if skipped_phases:
            result["skipped_phases_stored"] = True
        if warning:
            result["projection_warning"] = warning

    return json.dumps(result)


@_with_error_handling
@_catch_value_error
def _process_complete_phase(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    phase: str,
    db: EntityDatabase | None = None,
    iterations: int | None = None,
    reviewer_notes: str | None = None,
) -> str:
    state = engine.complete_phase(feature_type_id, phase)
    result = _serialize_state(state)

    if db is not None:
        # Store timing metadata in entity
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

        # Update entity -- set status to "completed" for terminal phase
        update_kwargs: dict = {"metadata": metadata}
        if phase == "finish":
            update_kwargs["status"] = "completed"
        db.update_entity(feature_type_id, **update_kwargs)

        # Update kanban_column for features based on completed phase
        if feature_type_id.startswith("feature:"):
            if phase == "finish":
                kanban = "completed"
            else:
                kanban = FEATURE_PHASE_TO_KANBAN.get(state.current_phase)
            if kanban:
                db.update_workflow_phase(feature_type_id, kanban_column=kanban)

        # Project .meta.json
        warning = _project_meta_json(db, engine, feature_type_id)

        result["completed_at"] = phase_timing[phase]["completed"]
        if warning:
            result["projection_warning"] = warning

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
# Reconciliation constants
# ---------------------------------------------------------------------------

_SUPPORTED_DIRECTIONS = frozenset({"meta_json_to_db"})


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
    direction: str,
    dry_run: bool,
) -> str:
    """Workflow reconciliation. Validates direction, returns JSON string."""
    if direction not in _SUPPORTED_DIRECTIONS:
        return _make_error(
            "invalid_transition",
            f"Unsupported direction: {direction}. Supported: {', '.join(sorted(_SUPPORTED_DIRECTIONS))}",
            "Use direction='meta_json_to_db' (the only supported direction)",
        )
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

    summary = _build_frontmatter_summary(reports)

    return json.dumps({
        "reports": [_serialize_drift_report(r) for r in reports],
        "summary": summary,
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
    """Create initial feature state in DB + entity registry, then project .meta.json."""
    feature_type_id = f"feature:{feature_id}-{slug}"

    # Validate feature_type_id for path traversal defense
    _validate_feature_type_id(feature_type_id, artifacts_root)

    # Build metadata dict
    metadata: dict = {
        "id": feature_id,
        "slug": slug,
        "mode": mode,
        "branch": branch,
        "phase_timing": {"brainstorm": {"started": _iso_now()}} if status == "active" else {},
    }
    if brainstorm_source:
        metadata["brainstorm_source"] = brainstorm_source
    if backlog_source:
        metadata["backlog_source"] = backlog_source

    # Register or update entity
    existing = db.get_entity(feature_type_id)
    if existing is None:
        db.register_entity(
            entity_type="feature",
            entity_id=f"{feature_id}-{slug}",
            name=slug,
            artifact_path=feature_dir,
            status=status,
            metadata=metadata,
        )
    else:
        # Retry path: preserve existing phase_timing, last_completed_phase,
        # skipped_phases to avoid clobbering progress data.
        existing_meta_raw = existing.get("metadata")
        if existing_meta_raw:
            existing_meta = json.loads(existing_meta_raw) if isinstance(existing_meta_raw, str) else existing_meta_raw
        else:
            existing_meta = {}
        metadata["phase_timing"] = existing_meta.get("phase_timing", metadata["phase_timing"])
        if existing_meta.get("last_completed_phase"):
            metadata["last_completed_phase"] = existing_meta["last_completed_phase"]
        if existing_meta.get("skipped_phases"):
            metadata["skipped_phases"] = existing_meta["skipped_phases"]
        db.update_entity(feature_type_id, status=status, metadata=metadata)

    # Project .meta.json
    warning = _project_meta_json(db, engine, feature_type_id, feature_dir)

    # Fix kanban_column based on status (init-time uses STATUS_TO_KANBAN).
    init_kanban = STATUS_TO_KANBAN.get(status)
    if init_kanban:
        try:
            db.update_workflow_phase(feature_type_id, kanban_column=init_kanban)
        except ValueError:
            # Row may not exist if engine initialization failed — create it.
            try:
                db.create_workflow_phase(feature_type_id, kanban_column=init_kanban)
            except ValueError:
                pass  # Entity itself may be missing; workflow row cannot be created

    result = {
        "created": True,
        "feature_type_id": feature_type_id,
        "status": status,
        "meta_json_path": os.path.join(feature_dir, ".meta.json"),
    }
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
    """Create initial project state in DB + .meta.json."""
    # Path traversal validation: block null bytes and ensure resolved path
    # matches the intended directory (no symlink escape)
    if "\0" in project_dir:
        raise ValueError("invalid_input: project_dir path traversal blocked")
    resolved = os.path.realpath(project_dir)
    if not os.path.isdir(resolved):
        raise ValueError(f"invalid_input: project_dir does not exist: {project_dir}")

    project_type_id = f"project:{project_id}-{slug}"

    # Parse JSON params (raises ValueError/JSONDecodeError on malformed input)
    features_list = json.loads(features)
    milestones_list = json.loads(milestones)

    # Register entity (idempotent — skip if already exists)
    existing = db.get_entity(project_type_id)
    metadata = {
        "id": project_id,
        "slug": slug,
        "features": features_list,
        "milestones": milestones_list,
    }
    if brainstorm_source:
        metadata["brainstorm_source"] = brainstorm_source

    if existing is None:
        db.register_entity(
            entity_type="project",
            entity_id=f"{project_id}-{slug}",
            name=slug,
            artifact_path=project_dir,
            status="active",
            metadata=metadata,
        )

    # Build project .meta.json (different schema from features — no phases,
    # lastCompletedPhase, branch, mode)
    meta = {
        "id": project_id,
        "slug": slug,
        "status": "active",
        "created": _iso_now(),
        "features": features_list,
        "milestones": milestones_list,
    }
    if brainstorm_source:
        meta["brainstorm_source"] = brainstorm_source

    # Atomic write
    meta_path = os.path.join(project_dir, ".meta.json")
    _atomic_json_write(meta_path, meta)

    return json.dumps({
        "created": True,
        "project_type_id": project_type_id,
        "meta_json_path": meta_path,
    })


@_with_error_handling
@_catch_value_error
def _process_activate_feature(
    db: EntityDatabase,
    engine: WorkflowStateEngine,
    feature_type_id: str,
    artifacts_root: str,
) -> str:
    """Transition a planned feature to active status.

    Pre-condition: entity status must be 'planned'.
    Post-condition: entity status becomes 'active', .meta.json projected.
    """
    _validate_feature_type_id(feature_type_id, artifacts_root)

    entity = db.get_entity(feature_type_id)
    if entity is None:
        raise ValueError(f"feature_not_found: {feature_type_id}")

    current_status = entity.get("status")
    if current_status != "planned":
        raise ValueError(
            f"invalid_transition: feature status is '{current_status}', "
            f"expected 'planned' for activation"
        )

    db.update_entity(feature_type_id, status="active")

    warning = _project_meta_json(db, engine, feature_type_id)

    result = {
        "activated": True,
        "feature_type_id": feature_type_id,
        "previous_status": "planned",
        "new_status": "active",
    }
    if warning:
        result["projection_warning"] = warning
    return json.dumps(result)


@_with_error_handling
@_catch_entity_value_error
def _process_init_entity_workflow(
    db: EntityDatabase, type_id: str, workflow_phase: str, kanban_column: str
) -> str:
    """Create a workflow_phases row for a brainstorm or backlog entity.

    Idempotent: if a row already exists, returns existing values with created=false.
    Validates entity existence, rejects feature/project types, and checks
    phase/column consistency against ENTITY_MACHINES when applicable.
    """
    # 1. Validate entity exists
    entity = db.get_entity(type_id)
    if entity is None:
        raise ValueError(f"entity_not_found: {type_id}")

    # 1b. Reject entity types that have their own workflow management
    if ":" in type_id:
        entity_type = type_id.split(":", 1)[0]
        if entity_type in ("feature", "project"):
            raise ValueError(
                f"invalid_entity_type: {entity_type} entities use the feature workflow engine"
            )
        if entity_type in ENTITY_MACHINES:
            machine = ENTITY_MACHINES[entity_type]
            if workflow_phase not in machine["columns"]:
                raise ValueError(
                    f"invalid_transition: {workflow_phase} is not a valid phase for {entity_type}"
                )
            expected_column = machine["columns"][workflow_phase]
            if kanban_column != expected_column:
                raise ValueError(
                    f"invalid_transition: kanban_column {kanban_column} does not match "
                    f"expected {expected_column} for phase {workflow_phase}"
                )

    # 2. Check idempotency — existing row means no-op (preserves MCP-managed state)
    existing = db._conn.execute(
        "SELECT workflow_phase, kanban_column FROM workflow_phases WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    if existing:
        return json.dumps({
            "created": False,
            "type_id": type_id,
            "workflow_phase": existing["workflow_phase"],
            "kanban_column": existing["kanban_column"],
            "reason": "already_exists",
        })

    # 3. Insert workflow_phases row
    db._conn.execute(
        "INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column, updated_at) "
        "VALUES (?, ?, ?, ?)",
        (type_id, workflow_phase, kanban_column, db._now_iso()),
    )
    db._conn.commit()

    return json.dumps({
        "created": True,
        "type_id": type_id,
        "workflow_phase": workflow_phase,
        "kanban_column": kanban_column,
    })


@_with_error_handling
@_catch_entity_value_error
def _process_transition_entity_phase(
    db: EntityDatabase, type_id: str, target_phase: str
) -> str:
    """Transition a brainstorm or backlog entity to a new lifecycle phase.

    Validates entity type, existence, current phase, and transition legality
    against ENTITY_MACHINES. Updates both entities.status and workflow_phases
    atomically. Forward transitions update last_completed_phase; backward
    transitions preserve it.
    """
    # 1. Parse entity_type
    if ":" not in type_id:
        raise ValueError(f"invalid_entity_type: malformed type_id: {type_id}")
    entity_type = type_id.split(":", 1)[0]

    # 2. Validate entity_type
    if entity_type not in ENTITY_MACHINES:
        raise ValueError(
            f"invalid_entity_type: {entity_type} — only brainstorm and backlog supported"
        )

    # 3. Validate entity exists
    entity = db.get_entity(type_id)
    if entity is None:
        raise ValueError(f"entity_not_found: {type_id}")

    # 4. Get current phase
    row = db._conn.execute(
        "SELECT workflow_phase FROM workflow_phases WHERE type_id = ?", (type_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"entity_not_found: no workflow_phases row for {type_id}")
    current_phase = row["workflow_phase"]
    if current_phase is None:
        raise ValueError(
            f"invalid_transition: {type_id} has NULL current_phase — "
            "call init_entity_workflow first"
        )

    # 5. Validate transition
    machine = ENTITY_MACHINES[entity_type]
    valid_targets = machine["transitions"].get(current_phase, [])
    if target_phase not in valid_targets:
        raise ValueError(
            f"invalid_transition: cannot transition {entity_type} from "
            f"{current_phase} to {target_phase}"
        )

    # 6. Look up target kanban column
    kanban_column = machine["columns"][target_phase]

    # 7. Determine if forward transition (for last_completed_phase)
    is_forward = (current_phase, target_phase) in machine["forward"]

    # 8. Atomic update in transaction
    now = db._now_iso()
    db._conn.execute(
        "UPDATE entities SET status = ?, updated_at = ? WHERE type_id = ?",
        (target_phase, now, type_id),
    )

    if is_forward:
        db._conn.execute(
            "UPDATE workflow_phases SET workflow_phase = ?, kanban_column = ?, "
            "last_completed_phase = ?, updated_at = ? WHERE type_id = ?",
            (target_phase, kanban_column, current_phase, now, type_id),
        )
    else:
        db._conn.execute(
            "UPDATE workflow_phases SET workflow_phase = ?, kanban_column = ?, "
            "updated_at = ? WHERE type_id = ?",
            (target_phase, kanban_column, now, type_id),
        )

    db._conn.commit()

    return json.dumps({
        "transitioned": True,
        "type_id": type_id,
        "from_phase": current_phase,
        "to_phase": target_phase,
        "kanban_column": kanban_column,
    })


@_with_error_handling
def _process_reconcile_status(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
) -> str:
    """Combined drift report. Returns JSON string."""
    # Workflow drift
    workflow_result = check_workflow_drift(engine, db, artifacts_root)

    # Frontmatter drift
    frontmatter_reports = scan_all(db, artifacts_root)

    fm_summary = _build_frontmatter_summary(frontmatter_reports)

    # Healthy: both dimensions have all counts except in_sync == 0
    wf_healthy = all(
        v == 0 for k, v in workflow_result.summary.items() if k != "in_sync"
    )
    fm_healthy = all(
        v == 0 for k, v in fm_summary.items() if k != "in_sync"
    )
    healthy = wf_healthy and fm_healthy

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
# MCP tool handlers
# ---------------------------------------------------------------------------

_NOT_INITIALIZED = _make_error(
    "not_initialized",
    "Engine not initialized (server not started)",
    "Wait for server startup or restart the MCP server",
)

mcp = FastMCP("workflow-engine", lifespan=lifespan)


@mcp.tool()
async def get_phase(feature_type_id: str) -> str:
    """Read the current workflow state for a feature."""
    if _engine is None:
        return _NOT_INITIALIZED
    return _process_get_phase(_engine, feature_type_id)


@mcp.tool()
async def transition_phase(
    feature_type_id: str,
    target_phase: str,
    yolo_active: bool = False,
    skipped_phases: str | None = None,
) -> str:
    """Validate and enter a target phase."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_transition_phase(
        _engine, feature_type_id, target_phase, yolo_active,
        db=_db, skipped_phases=skipped_phases,
    )


@mcp.tool()
async def complete_phase(
    feature_type_id: str,
    phase: str,
    iterations: int | None = None,
    reviewer_notes: str | None = None,
) -> str:
    """Record a phase as completed and advance to next phase."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_complete_phase(
        _engine, feature_type_id, phase,
        db=_db, iterations=iterations, reviewer_notes=reviewer_notes,
    )


@mcp.tool()
async def validate_prerequisites(feature_type_id: str, target_phase: str) -> str:
    """Dry-run gate evaluation without executing the transition."""
    if _engine is None:
        return _NOT_INITIALIZED
    return _process_validate_prerequisites(_engine, feature_type_id, target_phase)


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
    direction: str = "meta_json_to_db",
    dry_run: bool = False,
) -> str:
    """Sync .meta.json workflow state to DB for features where .meta.json is ahead."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_apply(
        _engine, _db, _artifacts_root, feature_type_id, direction, dry_run
    )


@mcp.tool()
async def reconcile_frontmatter(feature_type_id: str | None = None) -> str:
    """Check frontmatter headers against DB entity records for drift."""
    if _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_frontmatter(_db, _artifacts_root, feature_type_id)


@mcp.tool()
async def reconcile_status() -> str:
    """Unified health report across workflow state and frontmatter drift."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_status(_engine, _db, _artifacts_root)


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
async def activate_feature(feature_type_id: str) -> str:
    """Transition a planned feature to active status."""
    if _db is None or _engine is None:
        return _NOT_INITIALIZED
    return _process_activate_feature(_db, _engine, feature_type_id, _artifacts_root)


@mcp.tool()
async def init_entity_workflow(type_id: str, workflow_phase: str, kanban_column: str) -> str:
    """Create a workflow_phases row for any entity type."""
    if _db is None:
        return _NOT_INITIALIZED
    return _process_init_entity_workflow(_db, type_id, workflow_phase, kanban_column)


@mcp.tool()
async def transition_entity_phase(type_id: str, target_phase: str) -> str:
    """Transition a brainstorm or backlog entity to a new lifecycle phase."""
    if _db is None:
        return _NOT_INITIALIZED
    return _process_transition_entity_phase(_db, type_id, target_phase)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
