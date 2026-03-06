# Spec: Reconciliation MCP Tool

## Problem Statement

Feature 010 introduced graceful degradation: when the DB is unavailable, the workflow engine falls back to reading and writing `.meta.json` directly, returning `source="meta_json_fallback"`. However, when the DB recovers, the engine reads from the DB (stale) rather than `.meta.json` (current). State changes accumulated during degraded mode are invisible to the engine once the DB is back online.

### Evidence

- Feature 010 retro R4: "Degraded Mode State Drift — When operating in degraded mode, .meta.json writes accumulate state changes that are not reflected in the database. On DB recovery, the engine reads from DB (stale) rather than .meta.json (current). No reconciliation mechanism exists yet (planned as Feature 011)."
- Feature 010 spec Out of Scope: "Write-back reconciliation from .meta.json fallback state to DB (that's feature 011)"
- PRD FR-14: "Reconciliation tool compares .meta.json and DB state, reports drift, prompts user for resolution"
- Feature 003 spec: "Required by: 011-reconciliation-mcp-tool" and "Feature 011 will cover both .meta.json-vs-DB and frontmatter-vs-DB drift detection, building on top of feature 003's sync primitives"

### Dual Reconciliation Dimensions

Two independent drift axes exist:

1. **Workflow state drift (.meta.json vs DB `workflow_phases` table):** The DB's `workflow_phase`, `last_completed_phase`, and `mode` columns may lag behind `.meta.json`'s `lastCompletedPhase`, `phases`, and `status` fields after degraded-mode writes. This is the primary risk identified in feature 010.

2. **Frontmatter drift (file frontmatter headers vs DB `entities` table):** File frontmatter `entity_uuid` and `entity_type_id` may diverge from DB entity records. Feature 003 already provides the detection primitives (`detect_drift`, `scan_all`); this feature exposes them via MCP.

## Scope

### In Scope

1. **Workflow state drift detection** — Compare `.meta.json` workflow state against DB `workflow_phases` row for a single feature or all features. Report which fields differ and which source is fresher.
2. **Workflow state reconciliation** — Sync `.meta.json` workflow state back to DB when `.meta.json` is the fresher source (post-degradation recovery). Uses existing `WorkflowStateEngine` and `EntityDatabase` APIs — no raw SQL.
3. **Frontmatter drift detection via MCP** — Expose feature 003's `scan_all()` and `detect_drift()` as MCP tools so callers can check frontmatter-vs-DB consistency without CLI access.
4. **Combined drift report** — Single MCP tool that runs both workflow state and frontmatter drift scans, returning a unified summary.
5. **MCP tools in existing `workflow-engine` server** — New tools added to the existing server (feature 009), not a separate server. The workflow-engine server already has access to `EntityDatabase` and `artifacts_root`.

### Out of Scope

- Interactive conflict resolution UI (that's future UI features 018-022)
- Automatic scheduled reconciliation or background sync (reconciliation is invoked explicitly)
- DB schema changes — operates within existing `entities` and `workflow_phases` tables
- Modifying feature 003's `frontmatter_sync` module — uses it as-is
- Modifying `WorkflowStateEngine` internals — reconciliation operates at the DB/filesystem boundary, not inside the engine
- Frontmatter stamping or ingestion via MCP (feature 003's CLI handles those)
- Reconciliation of non-feature entity types (brainstorms, backlogs, projects have no `workflow_phases` rows)

## Requirements

### R1: Workflow State Drift Detection

`reconcile_check` MCP tool — compare `.meta.json` state against DB `workflow_phases` row.

- **Input:**
  - `feature_type_id: str | None` — if provided, check a single feature; if omitted, check all features
- **Output:** JSON string with:
  - `features: list` — per-feature drift reports
  - `summary: dict` — aggregate counts (`in_sync`, `meta_json_ahead`, `db_ahead`, `meta_json_only`, `db_only`, `error`)

Per-feature drift report structure:
```json
{
  "feature_type_id": "feature:010-graceful-degradation-to-metajs",
  "status": "in_sync|meta_json_ahead|db_ahead|meta_json_only|db_only|error",
  "meta_json": { "workflow_phase": "...", "last_completed_phase": "...", "mode": "...", "status": "..." },
  "db": { "workflow_phase": "...", "last_completed_phase": "...", "mode": "...", "kanban_column": "..." },
  "mismatches": [
    { "field": "last_completed_phase", "meta_json_value": "implement", "db_value": "design" }
  ]
}
```

**Field source mapping:**

| Output field | Source | Compared for drift? |
|---|---|---|
| `meta_json.workflow_phase` | Derived via `_derive_state_from_meta()` | Yes (secondary tiebreaker) |
| `meta_json.last_completed_phase` | `.meta.json` `lastCompletedPhase` field | Yes (primary comparator) |
| `meta_json.mode` | `.meta.json` `mode` field | Yes (field mismatch, not phase ordering) |
| `meta_json.status` | `.meta.json` `status` field | Informational only — not in workflow_phases table |
| `db.workflow_phase` | `workflow_phases.workflow_phase` column | Yes (secondary tiebreaker) |
| `db.last_completed_phase` | `workflow_phases.last_completed_phase` column | Yes (primary comparator) |
| `db.mode` | `workflow_phases.mode` column | Yes (field mismatch, not phase ordering) |
| `db.kanban_column` | `workflow_phases.kanban_column` column | Informational only — included for context |

**Drift status determination:** The overall `status` field is determined solely by phase comparison logic (R8) — only `last_completed_phase` and `workflow_phase` indices affect status. The `mode` field is compared separately: if phases match but `mode` differs, `status` is `"in_sync"` and `mismatches` includes `{field: "mode", ...}`. This allows callers to detect mode drift without it affecting the phase ordering heuristic.

Drift status logic:
- `"in_sync"`: Both sources exist and phase positions match (both `last_completed_phase` and `workflow_phase` have equal indices in `PHASE_SEQUENCE`). Note: `mode` may still differ — mode mismatches appear in `mismatches` but do not affect `status`
- `"meta_json_ahead"`: `.meta.json` has a later phase than DB (post-degradation scenario — `.meta.json` was updated during fallback, DB was not)
- `"db_ahead"`: DB has a later phase than `.meta.json` (unexpected but possible if DB was updated directly)
- `"meta_json_only"`: `.meta.json` exists but no `workflow_phases` row in DB
- `"db_only"`: DB has `workflow_phases` row but `.meta.json` not found or unparseable
- `"error"`: Comparison failed (e.g., invalid phase values, filesystem error)

Phase comparison logic for determining "ahead":
1. Parse `last_completed_phase` from both sources
2. Use `PHASE_SEQUENCE` index to compare: higher index = more advanced
3. If `.meta.json` last_completed_phase index > DB last_completed_phase index → `meta_json_ahead`
4. If DB last_completed_phase index > `.meta.json` last_completed_phase index → `db_ahead`
5. If indices equal, compare `workflow_phase` (current phase) using same logic
6. If both match → `in_sync`
7. If either has a `None` last_completed_phase and the other doesn't → the non-None source is ahead
8. If both have `None` last_completed_phase → indices are equal (-1); proceed to workflow_phase comparison (step 5). If both workflow_phase are also `None` → `in_sync`

### R2: Workflow State Reconciliation

`reconcile_apply` MCP tool — sync `.meta.json` state to DB for features where `.meta.json` is ahead.

- **Input:**
  - `feature_type_id: str | None` — if provided, reconcile a single feature; if omitted, reconcile all drifted features
  - `direction: str = "meta_json_to_db"` — reconciliation direction. Only `"meta_json_to_db"` is supported in this feature (the primary post-degradation use case). Future work may add `"db_to_meta_json"`.
  - `dry_run: bool = False` — if true, report what would change without applying
- **Output:** JSON string with:
  - `actions: list` — per-feature reconciliation actions
  - `summary: dict` — aggregate counts (`reconciled`, `skipped`, `error`, `dry_run`)

Per-feature action structure:
```json
{
  "feature_type_id": "feature:010-graceful-degradation-to-metajs",
  "action": "reconciled|skipped|error",
  "direction": "meta_json_to_db",
  "changes": [
    { "field": "last_completed_phase", "old_value": "design", "new_value": "implement" },
    { "field": "workflow_phase", "old_value": "create-plan", "new_value": "finish" }
  ],
  "message": "..."
}
```

Reconciliation logic for `meta_json_to_db`:
1. Run `reconcile_check` internally to detect drift
2-5 below are mutually exclusive branches — each feature's `status` from step 1 maps to exactly one branch:
2. For each feature with `status == "meta_json_ahead"`:
   a. Read `.meta.json` to derive target state via `engine._derive_state_from_meta()` (instance method on the passed WorkflowStateEngine)
   b. If `workflow_phases` row exists: call `db.update_workflow_phase()` with `workflow_phase`, `last_completed_phase`, and `mode` derived from `.meta.json`. **Field name translation:** `FeatureWorkflowState.current_phase` maps to the `workflow_phase` DB column; `FeatureWorkflowState.last_completed_phase` maps directly. **`kanban_column` is left unchanged** — the `_UNSET` sentinel pattern in `update_workflow_phase()` means omitted keyword arguments are not written to the DB; passing only `workflow_phase`, `last_completed_phase`, and `mode` leaves `kanban_column` at its existing value. This is a known limitation; callers should verify kanban state separately.
   c. If no `workflow_phases` row: call `db.create_workflow_phase()` to create the row. `kanban_column` uses the DB default (`"backlog"`).
   d. Record the changes made
3. For features with `status == "in_sync"`: skip (action `"skipped"`, message "Already in sync")
4. For features with `status == "db_ahead"`: skip (action `"skipped"`, message "DB is ahead — manual resolution required")
5. For features with `status == "meta_json_only"`: Check if entity exists in DB. If entity exists but no `workflow_phases` row, create the row from `.meta.json` state (kanban_column uses DB default). If entity doesn't exist, skip with error.
6. If `dry_run` is true: compute all changes but do not execute DB writes

**Note on user confirmation (PRD FR-14):** The PRD states reconciliation should "prompt user for resolution". This responsibility belongs to the agent/command layer, not the MCP tool. Callers should use `dry_run=True` to preview changes and present them to the user, then call with `dry_run=False` after confirmation. The MCP tool itself is a low-level primitive that does not prompt.

### R3: Frontmatter Drift Detection via MCP

`reconcile_frontmatter` MCP tool — expose feature 003's drift detection.

- **Input:**
  - `feature_type_id: str | None` — if provided, check artifacts for a single feature; if omitted, scan all features
- **Output:** JSON string with:
  - `reports: list` — per-file `DriftReport` objects serialized as JSON dicts
  - `summary: dict` — aggregate counts by status (`in_sync`, `file_only`, `db_only`, `diverged`, `no_header`, `error`)

Implementation:
- If `feature_type_id` provided: (1) extract feature slug via `feature_type_id.split(":", 1)[1]` with path-traversal validation (reject if slug contains `..`, `/`, or null bytes — same defense as `engine._extract_slug()`), (2) construct directory path `os.path.join(artifacts_root, "features", slug)`, (3) iterate artifact files listed in `ARTIFACT_BASENAME_MAP` from `entity_registry.frontmatter_sync` (currently: `spec.md`, `design.md`, `plan.md`, `tasks.md`, `retro.md`, `prd.md`), calling `detect_drift(db, filepath)` for each existing file. This is a known simplification vs `frontmatter_sync._derive_feature_directory()`'s 4-step fallback chain; all features in this codebase follow the `{slug}` directory convention. Note: all artifact files under a feature share the same entity record. `detect_drift()` compares each file's frontmatter against that single entity record. A feature with 6 artifact files produces up to 6 `DriftReport` entries, all referencing the same `type_id`.
- If omitted: call `scan_all()` from `frontmatter_sync`
- Serialize `DriftReport` dataclass fields to JSON dict (filepath, type_id, status, file_fields, db_fields, mismatches)
- Serialize `FieldMismatch` as `{field, file_value, db_value}`

### R4: Combined Drift Report

`reconcile_status` MCP tool — unified drift summary across both dimensions.

- **Input:** None (always scans all features). `reconcile_status` does not accept `feature_type_id` because its purpose is system-wide health assessment. Per-feature checks use `reconcile_check` and `reconcile_frontmatter` directly.
- **Output:** JSON string with:
  - `workflow_drift: dict` — summary from `reconcile_check` (counts by status)
  - `frontmatter_drift: dict` — summary from `reconcile_frontmatter` (counts by status)
  - `healthy: bool` — true only if all workflow features are `in_sync` AND all frontmatter files are `in_sync`
  - `total_features_checked: int`
  - `total_files_checked: int`

### R5: Processing Functions

Each tool delegates to a `_process_*()` function that accepts explicit parameters (no global state), matching the existing pattern in `workflow_state_server.py`. Processing functions never raise — they catch exceptions and return structured error JSON via `_make_error()`.

New processing functions (use existing `_with_error_handling` and `_catch_value_error` decorators from `workflow_state_server.py` for consistent error handling):
- `_process_reconcile_check(engine, db, artifacts_root, feature_type_id)` — delegates to `check_workflow_drift()`
- `_process_reconcile_apply(engine, db, artifacts_root, feature_type_id, direction, dry_run)` — validates `direction == "meta_json_to_db"` (returns `_make_error("invalid_transition", ...)` for unsupported directions), then delegates to `apply_workflow_reconciliation()` (which has no `direction` param since only one direction is supported)
- `_process_reconcile_frontmatter(db, artifacts_root, feature_type_id)` — extracts feature slug from `feature_type_id` via string split with path-traversal validation (no engine needed), then delegates to per-feature `detect_drift()` or `frontmatter_sync.scan_all()` when no `feature_type_id`
- `_process_reconcile_status(engine, db, artifacts_root)` — calls both check and frontmatter internally

### R6: Reconciliation Engine Module

Create `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py` — pure logic module containing:
- `check_workflow_drift(engine, db, artifacts_root, feature_type_id=None)` — workflow drift detection
- `apply_workflow_reconciliation(engine, db, artifacts_root, feature_type_id=None, dry_run=False)` — workflow reconciliation
- Dataclasses: `WorkflowDriftReport`, `WorkflowMismatch`, `ReconcileAction`

This separation follows the same pattern as `engine.py` (logic) vs `workflow_state_server.py` (MCP adapter). The processing functions in the server are thin wrappers around reconciliation module functions.

### R7: Integration with Existing Server

The 4 new MCP tools are added to the existing `workflow-engine` server in `workflow_state_server.py`. No new server or bootstrap script needed. The server already has access to `EntityDatabase` and `WorkflowStateEngine` via the lifespan context.

For `reconcile_frontmatter`, the server imports `detect_drift` and `scan_all` from `entity_registry.frontmatter_sync`. The `PYTHONPATH` already includes `hooks/lib/` (set by `run-workflow-server.sh`), so the import works without changes.

### R8: Freshness Heuristic for Phase Comparison

To determine which source is "ahead", compare phase positions in `PHASE_SEQUENCE`:

```python
from transition_gate import PHASE_SEQUENCE

PHASE_VALUES = tuple(p.value for p in PHASE_SEQUENCE)
# ("brainstorm", "specify", "design", "create-plan", "create-tasks", "implement", "finish")

def _phase_index(phase: str | None) -> int:
    """Return ordinal index of a phase, or -1 for None."""
    if phase is None:
        return -1
    try:
        return PHASE_VALUES.index(phase)
    except ValueError:
        return -1
```

Comparison:
1. Compare `last_completed_phase` indices from both sources
2. Higher index = more advanced (more phases completed)
3. If equal, compare `workflow_phase` (current phase) indices
4. If both equal → `in_sync`

Edge case: if `.meta.json` has `status: "completed"` and DB has `workflow_phase: "implement"`, `.meta.json` is ahead (finish > implement).

## Non-Functional Requirements

- **NFR-1 (Performance):** `reconcile_check` for a single feature is O(1) DB queries + O(1) file reads. Full scan is O(N) where N is the number of features (one DB query + one file read per feature). No batch optimizations needed for < 100 features.
- **NFR-2 (No new dependencies):** Uses only existing imports — `entity_registry.frontmatter_sync`, `entity_registry.database`, `workflow_engine.engine`, `transition_gate`.
- **NFR-3 (MCP boundary):** All reconciliation access goes through MCP tools. No direct Python import of reconciliation module by commands or skills.
- **NFR-4 (Idempotency):** `reconcile_apply` is idempotent — running it twice when already in sync produces no changes (all features skip with "Already in sync").
- **NFR-5 (Safety):** `reconcile_apply` defaults to `dry_run=False` for automation but the `dry_run=True` option allows preview. The `meta_json_to_db` direction only writes to DB (never modifies `.meta.json` files).
- **NFR-6 (Stdio safety):** No stdout output from processing functions. All diagnostics to stderr via `print(..., file=sys.stderr)`.

## Constraints

- Must not modify `WorkflowStateEngine` class — reconciliation wraps around it
- Must not modify `EntityDatabase` class — uses existing CRUD methods
- Must not modify `frontmatter_sync` module — uses existing functions as-is
- Must not change the `.meta.json` schema or `workflow_phases` DB schema
- Must not add new MCP server processes — tools are added to the existing `workflow-engine` server
- Reconciliation calls `engine._derive_state_from_meta()` on the `WorkflowStateEngine` instance passed to reconciliation functions. This avoids duplicating phase derivation logic. The method is private but accessible within the same `workflow_engine` package.

## Success Criteria

- SC-1: `reconcile_check` correctly identifies `in_sync`, `meta_json_ahead`, `db_ahead`, `meta_json_only`, and `db_only` states
- SC-2: `reconcile_apply` with `meta_json_to_db` syncs `.meta.json` state to DB for features where `.meta.json` is ahead, and the engine subsequently reads the updated state from DB
- SC-3: `reconcile_apply` with `dry_run=True` reports changes without modifying DB
- SC-4: `reconcile_frontmatter` returns correct drift reports matching feature 003's `scan_all()` output
- SC-5: `reconcile_status` returns unified health summary with correct `healthy` flag
- SC-6: All 4 new MCP tools callable via Claude's tool-use protocol and returning structured JSON
- SC-7: Processing functions testable in isolation (no MCP server required)
- SC-8: Idempotency — `reconcile_apply` on already-synced features produces no DB writes
- SC-9: Error handling — all tools return structured JSON errors (via `_make_error`) for DB failures, missing files, and invalid inputs

## Acceptance Criteria

### Workflow Drift Detection

- AC-1: `reconcile_check` on a feature with matching `.meta.json` and DB state returns `status: "in_sync"` with empty `mismatches`
- AC-2: Given `.meta.json` has `lastCompletedPhase: "implement"`, `status: "active"`, and `mode: "standard"`, and DB has `last_completed_phase: "design"`, `workflow_phase: "create-plan"`, and `mode: "standard"`, when `reconcile_check` runs, then `status` is `"meta_json_ahead"` and `mismatches` contains `{field: "last_completed_phase", meta_json_value: "implement", db_value: "design"}` and `{field: "workflow_phase", meta_json_value: "finish", db_value: "create-plan"}`
- AC-3: `reconcile_check` on a feature with `.meta.json` but no DB `workflow_phases` row returns `status: "meta_json_only"`
- AC-4: `reconcile_check` on a feature with DB `workflow_phases` row but no `.meta.json` returns `status: "db_only"`
- AC-5: `reconcile_check` with no argument scans all features and returns aggregate summary counts

### Workflow Reconciliation

- AC-6: `reconcile_apply` on a feature with `status: "meta_json_ahead"` updates DB `workflow_phases` row to match `.meta.json` state. Verified by subsequent `reconcile_check` returning `"in_sync"`
- AC-7: `reconcile_apply` on a feature with `status: "in_sync"` returns `action: "skipped"`
- AC-8: `reconcile_apply` on a feature with `status: "meta_json_only"` creates a new `workflow_phases` row from `.meta.json` state (entity must exist in DB)
- AC-9: `reconcile_apply` with `dry_run=True` returns the changes that would be made without modifying DB. Verified by subsequent `reconcile_check` still showing drift.
- AC-10: `reconcile_apply` is idempotent — running twice produces `"skipped"` on second run

### Frontmatter Drift Detection

- AC-11: `reconcile_frontmatter` for a feature with valid frontmatter matching DB returns reports with `status: "in_sync"`
- AC-12: `reconcile_frontmatter` for a feature with no frontmatter returns reports with `status: "db_only"` or `"no_header"`
- AC-13: `reconcile_frontmatter` with no argument scans all features and returns aggregate summary

### Combined Report

- AC-14: `reconcile_status` returns `healthy: true` when all workflow states are in sync and all frontmatter files are in sync
- AC-15: `reconcile_status` returns `healthy: false` when any drift exists in either dimension

### Error Handling

- AC-16: All reconciliation tools return structured JSON error (via `_make_error`) when DB is unavailable
- AC-17: `reconcile_apply` with unsupported direction returns structured error with `invalid_transition` type
- AC-18: `reconcile_check` with non-existent `feature_type_id` (e.g., `"feature:999-nonexistent"`) returns structured error with `feature_not_found` type. Malformed `feature_type_id` (e.g., missing colon) returns `invalid_transition` type via `_catch_value_error`

## Test Strategy

Unit tests for `reconciliation.py` covering:
- Workflow drift detection: all 5 status outcomes (AC-1 through AC-4, plus error case)
- Workflow reconciliation: apply, skip, create, dry_run, idempotency (AC-6 through AC-10)
- Phase comparison edge cases: None values, terminal phases, invalid phases

Integration tests in `test_workflow_state_server.py` (extending existing test file) covering:
- Processing functions for all 4 new tools (AC-1 through AC-18)
- Frontmatter drift detection integration with `frontmatter_sync` (AC-11 through AC-13)
- Combined status report (AC-14, AC-15)
- Error handling paths (AC-16 through AC-18)

All tests use in-memory SQLite DB and temp directories. Test file locations:
- `plugins/iflow/hooks/lib/workflow_engine/test_reconciliation.py` — unit tests for reconciliation module
- `plugins/iflow/mcp/test_workflow_state_server.py` — extended with processing function tests for new tools

## Dependencies

- **Depends on**: 009-state-engine-mcp-tools-phase-r (existing MCP server infrastructure, processing function pattern)
- **Depends on**: 003-bidirectional-uuid-sync-betwee (frontmatter_sync primitives: detect_drift, scan_all, DriftReport, FieldMismatch)
- **Depends on**: 010-graceful-degradation-to-metajs (defines the degradation paths that create the drift this feature resolves)
