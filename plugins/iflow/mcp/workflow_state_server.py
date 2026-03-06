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
from entity_registry.frontmatter_sync import (
    ARTIFACT_BASENAME_MAP,
    DriftReport,
    detect_drift,
    scan_all,
)
from semantic_memory.config import read_config
from transition_gate.models import Severity, TransitionResult
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
) -> str:
    response = engine.transition_phase(feature_type_id, target_phase, yolo_active)
    transitioned = all(r.allowed for r in response.results)
    return json.dumps({
        "transitioned": transitioned,
        "results": [_serialize_result(r) for r in response.results],
        "degraded": response.degraded,
    })


@_with_error_handling
@_catch_value_error
def _process_complete_phase(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    phase: str,
) -> str:
    state = engine.complete_phase(feature_type_id, phase)
    return json.dumps(_serialize_state(state))


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
    """Workflow drift detection. Returns JSON string."""
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
) -> str:
    """Validate and enter a target phase."""
    if _engine is None:
        return _NOT_INITIALIZED
    return _process_transition_phase(_engine, feature_type_id, target_phase, yolo_active)


@mcp.tool()
async def complete_phase(feature_type_id: str, phase: str) -> str:
    """Record a phase as completed and advance to next phase."""
    if _engine is None:
        return _NOT_INITIALIZED
    return _process_complete_phase(_engine, feature_type_id, phase)


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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
