# Specification: complete_phase Missing Top-Level completed Timestamp

## Problem Statement

When `complete_phase` MCP tool is called for the "finish" phase, `.meta.json` gets `status: "completed"` but no top-level `completed` timestamp. The `validate.sh` script requires `completed` when `status in ["completed", "abandoned"]`, causing CI failures.

Affected features: 035-039 — all required manual patching (see commits `47014eb` and `f436e94` which added `"completed": "<timestamp>"` to each feature's `.meta.json`).

## Root Cause

`_project_meta_json()` in `workflow_state_server.py` builds the `.meta.json` dict (the `meta = {...}` construction block between the `# Build .meta.json structure` comment and the `_atomic_json_write` call) but never populates a top-level `completed` field. The finish timestamp exists in `phase_timing["finish"]["completed"]` but is not extracted to the top level.

**Invariant:** `status == "completed"` (not `"abandoned"`) is only reachable when the finish phase is completed via `complete_phase`. The `"abandoned"` status is set via direct entity update, not through `complete_phase`. If either invariant is violated (status is terminal but no finish phase timing exists), R2 fallback applies.

## Requirements

### R1: Add top-level `completed` timestamp during projection

When `_project_meta_json` builds the meta dict and `status == "completed"`, it MUST set `meta["completed"]` using the "finish" phase's completed timestamp from `phase_timing`.

### R2: Graceful fallback for missing finish timing

If `status == "completed"` but `phase_timing["finish"]["completed"]` is absent (e.g., legacy data), fall back to current ISO timestamp (`_iso_now()`).

Trade-off: For legacy data without finish phase timing, the completed timestamp will reflect projection time, not actual completion time. This is acceptable because legacy features (035-039) were already manually patched.

### R3: No `completed` field when status is active

When `status == "active"`, the top-level `completed` field MUST NOT appear in `.meta.json`.

### R4: Handle `abandoned` status

When `status == "abandoned"`, set `meta["completed"]` using the same logic as R1/R2. `validate.sh` requires `completed` for both `completed` and `abandoned` statuses.

Note: Abandoned features never reach the finish phase, so finish phase timing is always absent. R2 fallback (`_iso_now()`) is the only path for abandoned status. The completed timestamp will reflect the time of the abandon-action projection.

## Acceptance Criteria

- AC1: Given a feature with active status, when `complete_phase("feature:X", "finish")` is called, then the projected `.meta.json` contains a top-level `completed` key whose value is an ISO 8601 timestamp matching the format used by `_iso_now()`.
- AC2: Given a projected `.meta.json` with `status: "completed"`, when `validate.sh` runs, then no errors are reported for the `completed` field.
- AC3: Given a feature with `status: "active"`, when `.meta.json` is projected, then no `completed` field is present.
- AC4: Existing tests continue to pass (`plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`).
- AC5: Given a feature with `status: "abandoned"` and no finish phase timing, when `.meta.json` is projected, then a top-level `completed` field is present with a value from `_iso_now()` (R2 fallback).

## Scope

### In Scope
- Fix `_project_meta_json` in `workflow_state_server.py`
- Add test coverage for the completed timestamp projection
- Handle both `completed` and `abandoned` statuses

### Out of Scope
- Backfilling existing `.meta.json` files (already manually fixed)
- Changes to `validate.sh` validation logic
- Changes to `init_feature_state`
