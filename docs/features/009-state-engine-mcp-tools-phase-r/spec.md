# Spec: State Engine MCP Tools — Phase Read/Write

## Overview

Expose `WorkflowStateEngine` operations as MCP tools so that commands, hooks, and the future iflow-UI can interact with the workflow state engine through the MCP protocol instead of direct Python imports.

This is the MCP boundary layer for the state engine — a thin adapter that delegates to `WorkflowStateEngine` (feature 008) and returns string responses following established MCP server conventions.

## Background

Feature 008 delivered `WorkflowStateEngine` as a stateless Python orchestrator. Currently, only Python code in `hooks/lib/` can use it via direct import. Downstream features (014 hook migration, 015 command migration, 018 UI server) need MCP-protocol access to drive phase transitions without code-level coupling (NFR-3).

### Dependency API

`WorkflowStateEngine` and `FeatureWorkflowState` are from `workflow_engine` (feature 008). `TransitionResult` and `Severity` are from `transition_gate.models` (feature 007).

```python
class WorkflowStateEngine:
    def __init__(self, db: EntityDatabase, artifacts_root: str) -> None
    def get_state(self, feature_type_id: str) -> FeatureWorkflowState | None
    def transition_phase(self, feature_type_id: str, target_phase: str, yolo_active: bool = False) -> list[TransitionResult]
    def complete_phase(self, feature_type_id: str, phase: str) -> FeatureWorkflowState
    def validate_prerequisites(self, feature_type_id: str, target_phase: str) -> list[TransitionResult]
    def list_by_phase(self, phase: str) -> list[FeatureWorkflowState]
    def list_by_status(self, status: str) -> list[FeatureWorkflowState]

@dataclass(frozen=True)
class FeatureWorkflowState:
    feature_type_id: str
    current_phase: str | None
    last_completed_phase: str | None
    completed_phases: tuple[str, ...]
    mode: str | None
    source: str  # "db" | "meta_json"

@dataclass(frozen=True)
class TransitionResult:
    allowed: bool
    reason: str
    severity: Severity  # block | warn | info
    guard_id: str
```

## Requirements

### R1: MCP Server — `workflow-engine`

A new FastMCP server named `workflow-engine` registered in `plugin.json` alongside the existing `memory-server` and `entity-registry` servers.

**Lifespan:** Initialize `EntityDatabase` and `WorkflowStateEngine` during startup, close DB on shutdown. Resolve `artifacts_root` from project config using `semantic_memory.config.read_config()` (same import as `entity_server.py`).

**Bootstrap:** Shell script `run-workflow-server.sh` following the same 4-step resolution pattern as `run-entity-server.sh`: (1) venv fast-path, (2) system python3, (3) uv bootstrap, (4) pip fallback. Must set `PYTHONPATH` to include `hooks/lib/` and `PYTHONUNBUFFERED=1`.

### R2: MCP Tools

Six tools mapping 1:1 to `WorkflowStateEngine` public methods:

#### R2.1: `get_phase`

Read the current workflow state for a feature.

- **Input:** `feature_type_id: str` (e.g., `"feature:009-state-engine-mcp-tools-phase-r"`)
- **Output:** JSON string with state fields (`feature_type_id`, `current_phase`, `last_completed_phase`, `completed_phases`, `mode`, `source`)
- **Error:** `"Feature not found: {feature_type_id}"` if engine returns None
- **Maps to:** `WorkflowStateEngine.get_state()`

#### R2.2: `transition_phase`

Validate and enter a target phase.

- **Input:**
  - `feature_type_id: str`
  - `target_phase: str` (one of: `brainstorm`, `specify`, `design`, `create-plan`, `create-tasks`, `implement`, `finish`)
  - `yolo_active: bool = False`
- **Output:** JSON string with:
  - `allowed: bool` — true only if ALL gate results are allowed
  - `results: list` — per-gate result objects (`allowed`, `reason`, `severity`, `guard_id`)
  - `transitioned: bool` — derived in the processing function: `transitioned = all(r.allowed for r in results)`, mirroring the engine logic where DB update only occurs when all gates pass
- **Error:** `"Error: {exception message}"` on ValueError from engine
- **Maps to:** `WorkflowStateEngine.transition_phase()`

#### R2.3: `complete_phase`

Record a phase as completed and advance to next phase.

- **Input:**
  - `feature_type_id: str`
  - `phase: str`
- **Output:** JSON string with updated state fields (same shape as `get_phase`)
- **Error:** `"Error: {exception message}"` on ValueError (unknown phase, phase mismatch, no active phase)
- **Maps to:** `WorkflowStateEngine.complete_phase()`

#### R2.4: `validate_prerequisites`

Dry-run gate evaluation without executing the transition.

- **Input:**
  - `feature_type_id: str`
  - `target_phase: str`
- **Output:** JSON string with:
  - `all_passed: bool` — true if ALL gates allow
  - `results: list` — per-gate result objects
- **Error:** `"Error: {exception message}"` on ValueError
- **Maps to:** `WorkflowStateEngine.validate_prerequisites()`

#### R2.5: `list_features_by_phase`

All features currently in a given workflow phase.

- **Input:** `phase: str`
- **Output:** JSON string array of state objects. Empty array `[]` for phases with no features (no validation against canonical phase values).
- **Error:** Returns error string on database exceptions.
- **Maps to:** `WorkflowStateEngine.list_by_phase()`

#### R2.6: `list_features_by_status`

All features with a given entity status.

- **Input:** `status: str`
- **Output:** JSON string array of state objects. Empty array `[]` for statuses with no features (no validation against canonical status values).
- **Error:** Returns error string on database exceptions.
- **Maps to:** `WorkflowStateEngine.list_by_status()`

### R3: Processing Functions

Each tool delegates to a `_process_*()` function that accepts explicit parameters (no global state). This enables unit testing without MCP server overhead, matching the pattern in `entity_server.py` and `memory_server.py`.

Processing functions never raise exceptions — they catch `ValueError` (from engine validation) and `Exception` (catch-all for unexpected errors like `sqlite3.OperationalError`, `OSError`) and return error strings. `ValueError` errors use the format `"Error: {message}"`. Unexpected exceptions use `"Internal error: {type.__name__}: {message}"`.

### R4: Serialization

`FeatureWorkflowState` and `TransitionResult` are frozen dataclasses. The server must serialize them to JSON dicts using manual dict construction with explicit `.value` for enum members (e.g., `severity.value`). `dataclasses.asdict()` does not automatically convert `Severity(str, Enum)` members to string values, so manual construction is preferred for correctness. The `completed_phases` tuple must serialize as a JSON array.

### R5: Plugin Registration

Add the `workflow-engine` server entry to `plugin.json`:
```json
"workflow-engine": {
  "command": "${CLAUDE_PLUGIN_ROOT}/mcp/run-workflow-server.sh",
  "args": []
}
```

### R6: DB Sharing

The workflow-engine server shares the same `EntityDatabase` instance path as the entity-registry server (resolved via `ENTITY_DB_PATH` env var or default `~/.claude/iflow/entities/entities.db`). The `EntityDatabase` class enables WAL mode in its constructor (`PRAGMA journal_mode = WAL`), which supports concurrent readers and serialized writers. The workflow-engine server relies on this existing behavior — it MUST NOT create a separate `sqlite3` connection outside `EntityDatabase`.

## Non-Functional Requirements

NFR numbers reference the iflow architecture evolution roadmap (P001 `roadmap.md` Cross-Cutting Concerns).

- **NFR-5 (Sub-100ms):** All read tools (`get_phase`, `list_features_by_phase`, `list_features_by_status`, `validate_prerequisites`) must respond within 100ms for typical workloads (< 50 features).
- **NFR-3 (MCP boundary):** No downstream consumer should import `WorkflowStateEngine` directly — all access goes through these MCP tools.
- **Stdio safety:** No stdout output before `mcp.run()`. All diagnostics to stderr only.
- **Test coverage:** Processing functions tested with real `EntityDatabase` (in-memory or temp file). Bootstrap script tested for PYTHONPATH and PYTHONUNBUFFERED correctness.

## Out of Scope

- Audit trail logging (NFR-4) — deferred to a future feature that adds event logging to the entity DB.
- UI-specific response formatting — downstream feature 018 handles that.
- Backward phase re-run semantics — already handled by `WorkflowStateEngine.complete_phase()`.
- Graceful degradation to `.meta.json` — that is feature 010.

## Success Criteria

- SC-1: All 6 MCP tools callable via Claude's tool-use protocol and returning correct JSON responses.
- SC-2: Processing functions have tests covering: (a) successful operation with valid input, (b) not-found / empty results, (c) ValueError from engine, (d) unexpected exception catch-all. Coverage verified via `pytest --cov` with branch mode.
- SC-3: Bootstrap script resolves Python environment correctly (4-step: venv → system python3 → uv bootstrap → pip fallback).
- SC-4: Plugin.json updated and server discoverable by Claude.
- SC-5: No stdout output from bootstrap script before `exec` (MCP stdio safety).
- SC-6: Read tools respond within 100ms when tested against a database seeded with 50 feature entities with workflow phase records.

## Acceptance Criteria

- AC-1: `get_phase` returns correct JSON for existing feature, "Feature not found" for missing.
- AC-2: `transition_phase` returns gate results and `transitioned: true` when all gates pass, `transitioned: false` when any gate blocks.
- AC-3: `complete_phase` returns updated state with advanced `current_phase` and updated `last_completed_phase`.
- AC-4: `validate_prerequisites` returns gate results without modifying DB state.
- AC-5: `list_features_by_phase` returns empty array for phases with no features, populated array otherwise.
- AC-6: `list_features_by_status` returns empty array for statuses with no features, populated array otherwise.
- AC-7: `transition_phase` with `yolo_active=True` passes YOLO-overridable gates.
- AC-8: Bootstrap script sets `PYTHONPATH` to include `hooks/lib/` and `PYTHONUNBUFFERED=1`.
- AC-9: Server registered in `plugin.json` under `mcpServers.workflow-engine`.
- AC-10: Processing functions testable in isolation (no MCP server required).
- AC-11: `transition_phase` and `validate_prerequisites` with an invalid phase string return an error string (not an unhandled exception).
