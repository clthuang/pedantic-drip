# Plan: Hook Migration — yolo-stop.sh

## Implementation Order

Single-file migration with 4 sequential phases:

```
Phase 0: Baseline verification
  → Task 0.1: Run existing hook tests to establish passing baseline

Phase 1: Replace phase_map (core change)
  → Task 1.1: Replace phase_map block with combined Python invocation
  → Task 1.2: Verify PYTHONPATH and shell variable interpolation

Phase 2: Test verification
  → Task 2.1: Run existing hook tests (AC-6) — compare against baseline
  → Task 2.2: Run transition_gate + workflow_engine tests

Phase 3: Manual verification checkpoint (AC-8 required gate)
  → Task 3.1: Execute AC-8 manual verification
```

**Line number convention:** All line references below are pre-migration values from the current `yolo-stop.sh`. The replacement block (design.md C1, ~38 lines including the `NEXT_PHASE=$(...)` wrapper) is longer than the original (13 lines), so post-migration line numbers for subsequent sections will shift by ~25 lines. Implementers should locate blocks by code pattern, not line number alone.

## Phase 0: Baseline Verification

### Task 0.1: Run existing hook tests before changes

```bash
bash plugins/iflow/hooks/tests/test-hooks.sh
```

Establishes a passing baseline. If any tests fail here, they are pre-existing failures — not regressions from this migration.

## Phase 1: Replace phase_map with Combined Python Invocation

### Task 1.1: Replace phase_map block

**File:** `plugins/iflow/hooks/yolo-stop.sh`

**What stays (lines 1-171):** All existing code is untouched — YOLO checks (20-69), active feature scanning (75-107), feature state reading (110-130), completion check (132-135), stop_hook_active check (137-154), stop count / max blocks (155-169), and the `# Determine next phase` comment on line 171.

**What gets replaced (lines 172-184):** The entire `NEXT_PHASE=$(python3 -c "phase_map = {` block — locate by pattern-matching the `phase_map` dictionary assignment opening and the `" 2>/dev/null)` closing. Line 172 itself (`NEXT_PHASE=$(python3 -c "`) is rewritten to include the `PYTHONPATH` prefix: `NEXT_PHASE=$(PYTHONPATH="${SCRIPT_DIR}/lib" python3 -c "`. The block starts with `NEXT_PHASE=$(` and ends with `" 2>/dev/null)`.

**Replacement:** The combined Python invocation from design.md C1 — a single `PYTHONPATH="${SCRIPT_DIR}/lib" python3 -c` call that:
1. **Try block (engine path):** Imports `PHASE_SEQUENCE`, `WorkflowStateEngine`, `EntityDatabase`. Constructs DB connection, calls `get_state()`, derives next phase via sequence index lookup.
2. **Except block (fallback path):** Retains inline `phase_map` dictionary for graceful degradation per NFR-3.

The `2>/dev/null` stderr suppression is preserved per NFR-4.

**What stays after (pre-migration lines 185-200):** The `NEXT_PHASE` empty check, `FEATURE_REF` construction, `REASON` message, and JSON output block are untouched — they consume `$NEXT_PHASE` identically regardless of how it was derived. Post-migration, these lines shift down by ~25 lines due to the larger replacement block.

### Task 1.2: Verify PYTHONPATH and variable interpolation

Verify:
- `${SCRIPT_DIR}/lib` resolves to the hooks/lib directory containing `transition_gate/`, `workflow_engine/`, `entity_registry/`
- Shell variables `${PROJECT_ROOT}`, `${ARTIFACTS_ROOT}`, `${FEATURE_ID}`, `${FEATURE_SLUG}`, `${LAST_COMPLETED_PHASE}` are all in scope at the replacement point — trace assignments: `FEATURE_ID` at line 126, `LAST_COMPLETED_PHASE` at line 126, `PROJECT_ROOT` at line 11, `ARTIFACTS_ROOT` at line 73
- The `NEXT_PHASE=$( ... )` capture pattern matches the existing assignment

## Phase 2: Test Verification

### Task 2.1: Run existing hook tests (AC-6)

```bash
bash plugins/iflow/hooks/tests/test-hooks.sh
```

All existing tests must pass without modification. These tests exercise the **fallback path** (no database in test environment) which produces identical output to the engine path by design.

### Task 2.2: Run transition_gate and workflow_engine tests

```bash
plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/ -v
plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/ -v
```

Confirms the engine modules (184 + 257 tests) that the hook now depends on are healthy. These tests confirm module health and internal correctness. The specific hook integration path (hook → EntityDatabase → WorkflowStateEngine → get_state) is validated by Task 3.1.

## Phase 3: Manual Verification Checkpoint (AC-8 — Required Gate)

### Task 3.1: Execute AC-8 manual verification

**This is a required gate task** — it must pass before the feature can be marked complete.

**Steps:**
1. Ensure `ENTITY_DB_PATH` points to a valid database
2. Verify the feature entity exists in the DB: `sqlite3 $ENTITY_DB_PATH "SELECT type_id FROM entities WHERE type_id = 'feature:014-hook-migration-yolo-stopsh-and'"`. If missing, register it first — otherwise `get_state()` returns None and the verification silently tests the fallback-within-try path instead of the DB path
3. Run the hook against a feature with `lastCompletedPhase="specify"`
4. Confirm the block message reads `"Invoke /iflow:design"` — proving the engine path produced the correct next phase

This compensates for zero automated hook-level coverage of the primary engine path.

## Acceptance Criteria Coverage

| AC | Covered By |
|----|------------|
| AC-1: No hardcoded phase_map in primary path | Task 1.1 — phase_map moves to except block only |
| AC-2: Uses PHASE_SEQUENCE | Task 1.1 — try block imports and uses PHASE_SEQUENCE |
| AC-3: specify → "Invoke /iflow:design" | Task 2.1 (fallback), Task 3.1 (engine) |
| AC-4: null → "Invoke /iflow:specify" | Task 2.1 (fallback). Note: brainstorm → specify is also covered implicitly by PHASE_SEQUENCE index lookup (index 0 → index 1) |
| AC-5: finish/completed → clean exit | Unchanged (lines 132-135 untouched) |
| AC-6: Existing tests pass | Task 2.1 |
| AC-7: Graceful fallback on import/DB failure | Task 1.1 — except Exception block |
| AC-8: Engine path manual verification | Task 3.1 (required gate) |
| AC-9: PYTHONPATH correct | Task 1.2 |

## Risk Mitigations

- **Import latency (R-1):** Estimated ~35-100ms, within 500ms NFR-2 budget. The fallback catches import/construction failures but not slow execution. If total latency exceeds 500ms without an exception, the hook runs slow. Mitigation: measured cold-start estimate provides substantial margin. Monitor post-deployment.
- **Phase sequence drift (R-3):** Accepted — fallback phase_map is temporary.
- **Shell variable injection (R-4):** All interpolated values come from controlled .meta.json fields, not user input.
