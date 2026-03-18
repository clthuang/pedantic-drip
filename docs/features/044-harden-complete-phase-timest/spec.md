# Specification: Harden complete_phase Timestamp Projection

## Problem Statement
When `complete_phase(feature_type_id, "finish")` runs, it should always produce a `.meta.json` with a top-level `completed` timestamp field. Feature 041 ended up with `status: "completed"` but no `completed` field, causing `validate.sh` CI failures.

## Root Cause (Verified)

`_project_meta_json()` at workflow_state_server.py:322 computes status as:
```python
"status": entity.get("status") or "active"
```

If the entity has `status=None` (entity exists but status was never set), this defaults to `"active"`. The `completed` field check at line 328 then skips: `if meta["status"] in ("completed", "abandoned")` evaluates to `False`.

Meanwhile, the `.meta.json` gets `status: "completed"` written either by:
- The engine's `_write_meta_json_fallback` (which writes status directly at engine.py:480)
- A subsequent projection where the entity status IS set

This creates a window where `.meta.json` has `status: "completed"` but no `completed` timestamp field.

**Key finding:** `engine.db` and the MCP server's `db` are the **same** EntityDatabase instance (line 130: `_engine = WorkflowStateEngine(_db, ...)`). So SQLite read-after-write within `_process_complete_phase` is NOT a race — writes at line 602 are visible to the read at line 288. The issue is entities with `status=None`.

**Secondary defense:** `_project_meta_json` should also add the `completed` field when `lastCompletedPhase == "finish"`, not just when `entity.get("status") == "completed"`. This covers the case where the entity status hasn't been updated but the workflow state indicates completion.

## Success Criteria
- [ ] After `complete_phase("finish")` runs, `.meta.json` always contains a top-level `completed` field with an ISO timestamp matching `_iso_now()` format (e.g., `2026-03-18T12:00:00.000000+00:00`)
- [ ] `validate.sh` passes for all completed features
- [ ] Existing workflow engine tests continue to pass
- [ ] New test verifies the `completed` field is projected when `phase="finish"`

## Scope

### In Scope
- Add `lastCompletedPhase == "finish"` as an alternative trigger for the `completed` field in `_project_meta_json` (line 328)
- Add a unit test in `test_workflow_state_server.py` that verifies `complete_phase("finish")` produces a `.meta.json` with the `completed` field
- Verify the three code paths: (1) DB healthy normal path, (2) engine fallback to `_write_meta_json_fallback`, (3) projection with entity status=None but lastCompletedPhase="finish"

### Out of Scope
- Changing `validate.sh`
- Fixing the double-write of `status="completed"` (engine.py:173 + workflow_state_server.py:602) — both are intentional (engine writes for its own DB consistency, server writes for entity metadata update)
- Modifying `_write_meta_json_fallback` (already correctly sets `completed` at engine.py:480-481)

## Acceptance Criteria

### AC-1: complete_phase finish produces completed timestamp
- Given a feature in active status with current_phase="implement"
- When `complete_phase(feature_type_id, "finish")` is called via the MCP tool
- Then the resulting `.meta.json` contains `"completed": "<ISO timestamp>"` at the top level

### AC-2: Projection with entity status=None but finish phase completed
- Given an entity with `status=None` in the DB and `lastCompletedPhase="finish"` in engine state
- When `_project_meta_json` is called
- Then `.meta.json` contains `"completed": "<ISO timestamp>"` (triggered by `lastCompletedPhase == "finish"`)

### AC-3: Existing degraded mode behavior preserved
- Given DB is unavailable (engine falls back to `_write_meta_json_fallback`)
- When `complete_phase(feature_type_id, "finish")` runs
- Then `.meta.json` contains `"completed": "<ISO timestamp>"` (engine.py:480-481 already handles this — verify with test)

### AC-4: validate.sh passes
- Given all features in the repo
- When `./validate.sh` is run
- Then zero errors about missing `completed` field

## Feasibility Assessment
**Overall:** Confirmed — one-line fix + one test.
**Fix:** In `_project_meta_json`, change line 328 from:
```python
if meta["status"] in ("completed", "abandoned"):
```
to:
```python
if meta["status"] in ("completed", "abandoned") or last_completed == "finish":
```
This ensures the `completed` field is added even when entity status hasn't propagated yet.

## Dependencies
- `plugins/iflow/mcp/workflow_state_server.py` (the fix)
- `plugins/iflow/mcp/test_workflow_state_server.py` (the test)
