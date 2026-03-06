# Spec: Graceful Degradation to .meta.json

## Problem Statement

The WorkflowStateEngine (feature 008) and its MCP tools (feature 009) currently require a functioning SQLite database to operate. If the database file is corrupted, locked by another process, or the MCP server fails to start, all state queries and transitions fail with unhandled exceptions. This blocks agents from making any workflow progress.

The engine already has a `.meta.json` hydration path (`_hydrate_from_meta_json`) that reads `.meta.json` and backfills the DB — but this only works when the DB is accessible. Specifically, `_hydrate_from_meta_json()` calls `self.db.get_entity()` as its first operation (engine.py:238), so it fails when the DB itself is the problem.

### Evidence

- `engine.py:43-46` — `get_state()` calls `db.get_workflow_phase()` with no try/except; any `sqlite3.Error` propagates as an unhandled crash
- `engine.py:64` — `transition_phase()` calls `db.update_workflow_phase()` with no fallback; DB lock or corruption = hard failure
- `engine.py:238` — `_hydrate_from_meta_json()` calls `self.db.get_entity()` as precondition; fails when DB is unavailable
- `workflow_state_server.py:105-134` — MCP tool handlers catch generic `Exception` but return opaque "Internal error" strings with no degradation signal
- PRD FR-15: "State engine gracefully degrades to reading `.meta.json` directly if MCP server is unreachable; agents are not blocked (degradation notice returned with result)"
- NFR-2: "Zero-downtime migration with graceful degradation fallback to .meta.json"

### FR-15 Scope Clarification

PRD FR-15 mentions "MCP server unreachable" — this feature addresses the **DB unavailability** subset of that scenario. When the MCP server process itself is down, callers get no response at all (transport-level failure). This feature ensures that when the MCP server IS running but the DB backing it is unavailable, the server returns useful fallback data instead of crashing. Full MCP-server-down handling is infrastructure (out of scope).

## Scope

### In Scope

1. **Read degradation** — When DB queries fail (any `sqlite3.Error`), the engine falls back to reading `.meta.json` directly via a new pure-filesystem path (bypassing the existing `_hydrate_from_meta_json` which requires DB access) and returns valid `FeatureWorkflowState` with `source="meta_json_fallback"`
2. **Write degradation** — When DB writes fail during `transition_phase()` or `complete_phase()`, the engine writes state changes to `.meta.json` as fallback, returns results with a degradation notice
3. **MCP server degradation signal** — MCP tool responses include a `degraded` boolean field so callers can detect when operating in fallback mode
4. **Structured error responses** — Replace opaque "Internal error: ..." strings with JSON error responses containing error type and recovery hints
5. **DB health check** — A lightweight probe (`SELECT 1` via `self.db._conn`) that the engine uses to detect DB issues before attempting complex queries
6. **List operation fallback** — `list_by_phase()` and `list_by_status()` fall back to scanning `.meta.json` files in the features directory when DB is unavailable
7. **Transitive degradation for read-only methods** — `validate_prerequisites()` degrades transitively via its `get_state()` call; no separate handling needed

### Out of Scope

- MCP server process monitoring or auto-restart (that's infrastructure, not engine logic)
- Automatic DB repair or corruption recovery (out of scope — user must intervene)
- Write-back reconciliation from `.meta.json` fallback state to DB (that's feature 011)
- Migrating commands to use MCP tools (that's features 014-017)
- UI server graceful degradation (that's Release 2)
- Full "MCP server unreachable" handling (transport-level — callers get no response regardless)

## Feasibility Assessment

### Key Dependency: `_hydrate_from_meta_json()` DB Precondition

The existing `_hydrate_from_meta_json()` (engine.py:233-310) calls `self.db.get_entity()` at line 238 as its first operation. This means the current hydration path CANNOT serve as a fallback when the DB is unavailable. The implementation must create a **new pure-filesystem fallback method** (`_read_state_from_meta_json`) that:
- Derives `feature_type_id` from the `.meta.json` `id` and `slug` fields instead of querying the entity table
- Reuses the same phase derivation logic (lines 255-283) from `_hydrate_from_meta_json`
- Skips the DB backfill step entirely (lines 286-301)

### Health Probe Access Path

`EntityDatabase` exposes `_conn` (a `sqlite3.Connection` instance) at `database.py:353`. The health probe will execute `SELECT 1` via `self.db._conn.execute("SELECT 1")`. This is a private attribute access — acceptable since both classes are in the same package and the constraint says "Must not modify EntityDatabase class."

### `.meta.json` Field Mapping for Write Fallback

The write fallback updates only fields that already exist in `.meta.json`:
- `lastCompletedPhase` — updated by `complete_phase()`
- `phases.{phase}.started` / `phases.{phase}.completed` — timestamps
- `status` — updated to "completed" when finishing

The DB's `workflow_phase` column has no `.meta.json` equivalent. This is acceptable because `workflow_phase` is derivable from `lastCompletedPhase` + `status` (the same derivation logic in `_hydrate_from_meta_json` lines 259-283). When the DB recovers, feature 011 reconciliation will backfill the `workflow_phase` column.

## Requirements

### R1: Read Fallback on DB Failure

When `get_state()` encounters any `sqlite3.Error` (covers `OperationalError`, `DatabaseError`, `InterfaceError`, etc.):
1. Catch the error and log a warning to stderr: `"[degraded] get_state({feature_type_id}): DB unavailable ({error}), falling back to .meta.json"`
2. Extract the feature slug from `feature_type_id` (reuse `_extract_slug()`)
3. Read `{artifacts_root}/features/{slug}/.meta.json` directly from filesystem
4. Derive `FeatureWorkflowState` using the same phase derivation logic as `_hydrate_from_meta_json` (status → workflow_phase mapping, `_derive_completed_phases`, `_next_phase_value`) but **without any DB calls**
5. Return `FeatureWorkflowState` with `source="meta_json_fallback"`
6. If `.meta.json` doesn't exist or is unparseable, return `None` (same as current behavior for missing features)
7. Do NOT re-raise the exception

Implementation: Add a new private method `_read_state_from_meta_json(feature_type_id: str) -> FeatureWorkflowState | None` that performs steps 2-6. This is distinct from `_hydrate_from_meta_json` which requires DB access for entity lookup and backfill.

### R2: Write Fallback on DB Failure

When `transition_phase()` encounters a `sqlite3.Error` during `db.update_workflow_phase()`:
1. Catch the error and log a warning to stderr
2. The transition is semantically "entering a phase" — there is no `.meta.json` field to update (`.meta.json` has no `workflow_phase` field, and the constraint prohibits schema changes)
3. Gate evaluation results are still valid (computed from in-memory `FeatureWorkflowState` and filesystem artifacts, not from DB state)
4. Return the gate results with `source="meta_json_fallback"` on the state to signal degradation
5. Note: The DB update is a recording step; the phase transition is logically valid based on the gate results. Feature 011 reconciliation will sync state when DB recovers.

When `complete_phase()` encounters a `sqlite3.Error` during `db.update_workflow_phase()`:
1. Catch the error and log a warning to stderr
2. Write the state change to `.meta.json` directly (these fields already exist):
   - Update `lastCompletedPhase` field to the completed phase
   - Update `phases.{phase}` sub-object: add `completed` timestamp (and `started` if missing)
   - Update `status` to `"completed"` if completing the `finish` phase
3. Return `FeatureWorkflowState` with `source="meta_json_fallback"` to signal degradation

### R3: MCP Degradation Signal

All MCP tool responses include a `degraded` boolean field:
- `false` when operating normally (DB as primary)
- `true` when any fallback was used during the request

Detection: `degraded = (state.source == "meta_json_fallback")` where state is the `FeatureWorkflowState` returned by the engine method.

Serialization helpers (`_serialize_state`, `_serialize_result`) include this field. For `_serialize_state`, derive from `state.source`. For composite responses (e.g., `transition_phase` returning a list of `TransitionResult`), include a top-level `degraded` field.

### R4: Structured Error Responses

Replace string error messages in MCP handlers with JSON:
```json
{
  "error": true,
  "error_type": "db_unavailable|feature_not_found|invalid_transition|internal",
  "message": "Human-readable description",
  "recovery_hint": "Suggested action"
}
```

Error type mapping:
- `sqlite3.Error` in engine → `"db_unavailable"` with hint `"Check DB file at {path}"`
- `ValueError("Feature not found")` → `"feature_not_found"` with hint `"Verify feature_type_id format: 'feature:{id}-{slug}'"`
- `ValueError` (other) → `"invalid_transition"` with hint from error message
- Other `Exception` → `"internal"` with hint `"Report this error"`

### R5: DB Health Probe

Add a `_check_db_health()` method to `WorkflowStateEngine`:
- Executes `self.db._conn.execute("SELECT 1")` (accesses the `sqlite3.Connection` via `EntityDatabase._conn`)
- Returns `True` if successful, `False` on any `sqlite3.Error`
- Called once at the start of each public method to set a `_db_available` flag for the duration of that call
- The flag is a local variable passed through the call chain, NOT an instance attribute (preserves stateless design per NFR-4)
- When `_db_available` is `False`, methods skip DB calls entirely and go straight to filesystem fallback

### R6: List Operation Fallback

When `list_by_phase()` encounters DB failure:
1. Scan `{artifacts_root}/features/*/` directories for `.meta.json` files
2. Parse each file and derive `FeatureWorkflowState` using the same pure-filesystem logic as R1's `_read_state_from_meta_json`
3. Filter by matching `current_phase == requested_phase`
4. Return results with `source="meta_json_fallback"`

When `list_by_status()` encounters DB failure:
1. Scan `{artifacts_root}/features/*/` directories for `.meta.json` files
2. Parse each file's `status` field (this is the **entity status** from `.meta.json`, e.g., "active", "completed", "planned")
3. Filter by matching `meta["status"] == requested_status`
4. For matching features, derive `FeatureWorkflowState` using the same pure-filesystem logic as R1
5. Return results with `source="meta_json_fallback"`

Note: In normal operation, `list_by_status()` queries the entity table for status. In fallback mode, `.meta.json`'s `status` field is the authoritative source — it is the same field that the entity registry reads during backfill. The fallback may miss features that have entity records but no `.meta.json` files, which is acceptable since `.meta.json` is the primary data source.

### R7: Transitive Degradation for validate_prerequisites

`validate_prerequisites()` calls `get_state()` internally and then `_evaluate_gates()`. Since `_evaluate_gates()` uses in-memory state and filesystem artifact checks (no DB calls), the only DB dependency is `get_state()`. R1 already handles `get_state()` degradation, so `validate_prerequisites()` degrades transitively — no separate fallback logic needed.

### R8: No Behavioral Change in Happy Path

When the DB is available and working:
- All operations behave identically to the current implementation
- No additional I/O or filesystem scanning (health probe is the only added overhead: one `SELECT 1`)
- The `degraded` field is `false` in all responses
- Performance remains within the existing sub-100ms NFR

## Success Criteria

- [ ] SC-1: `get_state()` returns valid state from `.meta.json` when DB raises `sqlite3.Error`
- [ ] SC-2: `transition_phase()` returns gate results when DB write fails, with degradation signal
- [ ] SC-3: `complete_phase()` writes to `.meta.json` when DB write fails, returns state with `source="meta_json_fallback"`
- [ ] SC-4: `list_by_phase()` returns results from filesystem scan when DB fails
- [ ] SC-5: `list_by_status()` returns results from filesystem scan when DB fails, filtering by `.meta.json` `status` field
- [ ] SC-6: MCP tool responses include `degraded: true/false` boolean field
- [ ] SC-7: MCP error responses are structured JSON (not plain strings)
- [ ] SC-8: All existing tests pass without modification (happy path unchanged)
- [ ] SC-9: New tests cover each degradation path with mocked DB failures
- [ ] SC-10: `_check_db_health()` correctly detects DB unavailability
- [ ] SC-11: `validate_prerequisites()` returns valid results when DB is unavailable (transitive via R1)

## Acceptance Criteria

- [ ] AC-1: Engine unit tests: mock `sqlite3.Error` on `db.get_workflow_phase()` and `db.get_entity()`, verify `_read_state_from_meta_json` fallback produces correct `FeatureWorkflowState` with `source="meta_json_fallback"`
- [ ] AC-2: Engine unit tests: mock DB write failures on `db.update_workflow_phase()`, verify `complete_phase()` updates `.meta.json` correctly (lastCompletedPhase, phases timestamps, status)
- [ ] AC-3: MCP server tests: verify `degraded` field present in all tool responses (both normal and fallback paths)
- [ ] AC-4: MCP server tests: verify structured JSON error format for all error paths (db_unavailable, feature_not_found, invalid_transition, internal)
- [ ] AC-5: Engine unit tests: mock `sqlite3.Error` on health probe, verify all public methods (`get_state`, `transition_phase`, `complete_phase`, `validate_prerequisites`, `list_by_phase`, `list_by_status`) fall back correctly
- [ ] AC-6: No performance regression: healthy-path operations complete within existing benchmarks (health probe adds negligible overhead)
- [ ] AC-7: Backward compatible: `FeatureWorkflowState.source` field already exists; new value `"meta_json_fallback"` added alongside existing `"db"` and `"meta_json"`
- [ ] AC-8: All existing test suites pass without modification: `pytest plugins/iflow/hooks/lib/workflow_engine/ -v` and `pytest plugins/iflow/mcp/test_workflow_state_server.py -v` (if exists)

## Non-Functional Requirements

- NFR-1: Degraded mode for single-feature operations adds <5ms overhead (filesystem stat + JSON parse). List operations scanning N features: <5ms + (N × ~1ms per .meta.json parse), acceptable for typical feature counts (<50)
- NFR-2: No new dependencies — uses only stdlib `sqlite3`, `json`, `os`, `glob`
- NFR-3: All degradation events logged to stderr (MCP stdio safety — never stdout)
- NFR-4: Thread-safe — the health probe result is passed as a local variable through the call chain, not stored as instance state. No shared mutable state introduced.

## Constraints

- Must not modify `EntityDatabase` class — degradation wrapping happens in `WorkflowStateEngine` only
- Must not change the `.meta.json` schema — only write fields that already exist
- Must preserve the existing hydration path (DB row exists → use it; DB row missing → hydrate from `.meta.json`) when DB is healthy
- `FeatureWorkflowState` dataclass is frozen — cannot add mutable fields; `source` field already carries provenance
- Accessing `EntityDatabase._conn` for health probe is acceptable (same-package private access, avoids modifying EntityDatabase)
