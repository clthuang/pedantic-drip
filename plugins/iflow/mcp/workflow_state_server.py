"""MCP workflow-engine server for phase read/write operations.

Runs as a subprocess via stdio transport.  Never print to stdout
(corrupts JSON-RPC protocol) -- all logging goes to stderr.
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager

# Make workflow_engine, transition_gate, entity_registry, semantic_memory
# importable from hooks/lib/ — safety net for direct invocation and tests.
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

from entity_registry.database import EntityDatabase
from semantic_memory.config import read_config
from transition_gate.models import Severity, TransitionResult
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.models import FeatureWorkflowState

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


# ---------------------------------------------------------------------------
# Processing functions
# ---------------------------------------------------------------------------


def _process_get_phase(engine: WorkflowStateEngine, feature_type_id: str) -> str:
    try:
        state = engine.get_state(feature_type_id)
        if state is None:
            return f"Feature not found: {feature_type_id}"
        return json.dumps(_serialize_state(state))
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"


def _process_transition_phase(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    target_phase: str,
    yolo_active: bool,
) -> str:
    try:
        results = engine.transition_phase(feature_type_id, target_phase, yolo_active)
        # allowed and transitioned are always equal; both keys exist for
        # MCP consumer clarity.  Mirrors engine.py — updates DB iff all pass.
        transitioned = all(r.allowed for r in results)
        return json.dumps({
            "allowed": transitioned,
            "results": [_serialize_result(r) for r in results],
            "transitioned": transitioned,
        })
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"


def _process_complete_phase(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    phase: str,
) -> str:
    try:
        state = engine.complete_phase(feature_type_id, phase)
        return json.dumps(_serialize_state(state))
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"


def _process_validate_prerequisites(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    target_phase: str,
) -> str:
    try:
        results = engine.validate_prerequisites(feature_type_id, target_phase)
        all_passed = all(r.allowed for r in results)
        return json.dumps({
            "all_passed": all_passed,
            "results": [_serialize_result(r) for r in results],
        })
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"


def _process_list_features_by_phase(engine: WorkflowStateEngine, phase: str) -> str:
    # ValueError from _row_to_state on corrupt DB data is intentionally caught
    # by Exception and reported as "Internal error:" (not user input error).
    try:
        states = engine.list_by_phase(phase)
        return json.dumps([_serialize_state(s) for s in states])
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"


def _process_list_features_by_status(engine: WorkflowStateEngine, status: str) -> str:
    # ValueError from _row_to_state on corrupt DB data is intentionally caught
    # by Exception and reported as "Internal error:" (not user input error).
    try:
        states = engine.list_by_status(status)
        return json.dumps([_serialize_state(s) for s in states])
    except Exception as exc:
        return f"Internal error: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# MCP tool handlers
# ---------------------------------------------------------------------------

mcp = FastMCP("workflow-engine", lifespan=lifespan)


@mcp.tool()
async def get_phase(feature_type_id: str) -> str:
    """Read the current workflow state for a feature."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_get_phase(_engine, feature_type_id)


@mcp.tool()
async def transition_phase(
    feature_type_id: str,
    target_phase: str,
    yolo_active: bool = False,
) -> str:
    """Validate and enter a target phase."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_transition_phase(_engine, feature_type_id, target_phase, yolo_active)


@mcp.tool()
async def complete_phase(feature_type_id: str, phase: str) -> str:
    """Record a phase as completed and advance to next phase."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_complete_phase(_engine, feature_type_id, phase)


@mcp.tool()
async def validate_prerequisites(feature_type_id: str, target_phase: str) -> str:
    """Dry-run gate evaluation without executing the transition."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_validate_prerequisites(_engine, feature_type_id, target_phase)


@mcp.tool()
async def list_features_by_phase(phase: str) -> str:
    """All features currently in a given workflow phase."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_list_features_by_phase(_engine, phase)


@mcp.tool()
async def list_features_by_status(status: str) -> str:
    """All features with a given entity status."""
    if _engine is None:
        return "Error: engine not initialized (server not started)"
    return _process_list_features_by_status(_engine, status)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
