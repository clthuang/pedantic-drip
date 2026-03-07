# Tasks: Hook Migration — yolo-stop.sh

## Phase 0: Baseline Verification

### Task 0.1: Run existing hook tests before changes

**Why:** Establishes passing baseline so Phase 2 can detect regressions (plan Phase 0).

- [ ] Run `bash plugins/iflow/hooks/tests/test-hooks.sh`
- [ ] Record test count and pass/fail status
- [ ] If any tests fail, note them as pre-existing — not regressions

**Done when:** All tests run and baseline results are recorded. Pre-existing failures are noted but do not block.

**Files:** None (read-only)

---

## Phase 1: Replace phase_map with Combined Python Invocation

### Task 1.1: Pre-flight check — PYTHONPATH and variable scope

**Why:** Validates all prerequisites before modifying code — confirms packages exist and variables are in scope (plan Task 1.1, design C2).

**Depends on:** Task 0.1

- [ ] Run `ls plugins/iflow/hooks/lib/` and confirm `transition_gate/`, `workflow_engine/`, `entity_registry/` directories exist
- [ ] Read `plugins/iflow/hooks/yolo-stop.sh` and verify shell variables are assigned before line 172: `FEATURE_ID` (line 126), `LAST_COMPLETED_PHASE` (line 126), `PROJECT_ROOT` (line 11), `ARTIFACTS_ROOT` (line 73)
- [ ] Run `sed -n '172p' plugins/iflow/hooks/yolo-stop.sh` and confirm the output starts with `NEXT_PHASE=$(python3 -c "` — this is the line where the replacement begins

**Done when:** All three packages exist in `lib/`, all four variables are assigned before line 172, and `sed -n '172p'` output confirms the replacement target line. If any check fails, stop and investigate before proceeding.

**Files:** None (read-only)

---

### Task 1.2: Replace phase_map block with combined Python invocation

**Why:** Core migration — replaces hardcoded phase_map with PHASE_SEQUENCE lookup via WorkflowStateEngine (plan Task 1.2, design C1, spec FR-1/FR-2).

**Depends on:** Task 1.1

- [ ] Open `plugins/iflow/hooks/yolo-stop.sh`
- [ ] Locate the block starting with `NEXT_PHASE=$(python3 -c "` and ending on the line containing `" 2>/dev/null)` that immediately follows the `print(phase_map.get(last, ''))` line (pre-migration lines 172-184) — match by the `phase_map = {` pattern inside
- [ ] Replace the entire block (lines 172 through the `" 2>/dev/null)` closing line) with the combined Python invocation from design.md C1:

```bash
NEXT_PHASE=$(PYTHONPATH="${SCRIPT_DIR}/lib" python3 -c "
try:
    from transition_gate.constants import PHASE_SEQUENCE
    from workflow_engine.engine import WorkflowStateEngine
    from entity_registry.database import EntityDatabase
    import os

    _PHASE_VALUES = tuple(p.value for p in PHASE_SEQUENCE)
    db_path = os.environ.get('ENTITY_DB_PATH',
        os.path.expanduser('~/.claude/iflow/entities/entities.db'))
    db = EntityDatabase(db_path)
    engine = WorkflowStateEngine(db, '${PROJECT_ROOT}/${ARTIFACTS_ROOT}')
    state = engine.get_state('feature:${FEATURE_ID}-${FEATURE_SLUG}')

    if state is not None:
        last = state.last_completed_phase or ''
    else:
        last = '${LAST_COMPLETED_PHASE}'

    # Both null representations converge here:
    # Engine path: None -> '' (via 'or' fallback above)
    # Fallback path: string 'null' (from .meta.json parsing)
    if last in ('null', ''):
        print(PHASE_SEQUENCE[1].value)  # specify — first command phase
    elif last in _PHASE_VALUES:
        idx = _PHASE_VALUES.index(last)
        print(_PHASE_VALUES[idx + 1] if idx < len(_PHASE_VALUES) - 1 else '')
    else:
        print('')
except Exception:
    phase_map = {
        'null': 'specify', 'brainstorm': 'specify', 'specify': 'design',
        'design': 'create-plan', 'create-plan': 'create-tasks',
        'create-tasks': 'implement', 'implement': 'finish',
    }
    last = '${LAST_COMPLETED_PHASE}'
    print(phase_map.get(last, ''))
" 2>/dev/null)
```

- [ ] Verify the `2>/dev/null` stderr suppression is preserved at the end
- [ ] Run `bash -n plugins/iflow/hooks/yolo-stop.sh` and confirm exit code 0 (no syntax errors)
- [ ] Run `git diff plugins/iflow/hooks/yolo-stop.sh` and confirm only the phase_map block (lines 172-184) was modified — lines before and after are untouched

**Done when:** The phase_map block is replaced with the combined invocation. `bash -n` exits 0. `git diff` shows changes only in the phase_map block region.

**Files:** `plugins/iflow/hooks/yolo-stop.sh`

---

## Phase 2: Test Verification

### Task 2.1: Run existing hook tests (AC-6)

**Why:** Confirms zero regressions from the code change by comparing against Phase 0 baseline (plan Task 2.1, spec AC-6).

**Depends on:** Tasks 0.1 and 1.2

- [ ] Run `bash plugins/iflow/hooks/tests/test-hooks.sh`
- [ ] Compare results against Task 0.1 baseline — same tests must pass
- [ ] If any test that passed in baseline now fails, it is a regression — fix before proceeding

**Done when:** All tests that passed in Phase 0 baseline still pass. Zero regressions.

**Files:** None (read-only)

---

### Task 2.2: Run transition_gate and workflow_engine tests

**Why:** Confirms the engine modules the hook now depends on are healthy (plan Task 2.2, spec AC-6).

**Depends on:** Task 1.2

- [ ] Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/ -v`
- [ ] Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/ -v`
- [ ] Confirm all tests pass (257 transition_gate + 184 workflow_engine)

**Done when:** All engine module tests pass. These confirm the modules the hook now depends on are healthy.

**Files:** None (read-only)

**Parallel with:** Task 2.1 (no dependency between 2.1 and 2.2)

---

## Phase 3: Manual Verification Checkpoint (AC-8 — Required Gate)

### Task 3.1: Execute AC-8 manual verification

**Why:** Proves the engine path (not fallback) produces correct next-phase derivation — the only way to verify the primary code path since existing tests exercise only the fallback (plan Task 3.1, spec AC-8).

**Depends on:** Tasks 2.1 and 2.2

**This is a required gate task** — it must pass before the feature can be marked complete.

- [ ] Ensure `ENTITY_DB_PATH` points to a valid database (default: `~/.claude/iflow/entities/entities.db`)
- [ ] Verify the feature entity exists: `sqlite3 $ENTITY_DB_PATH "SELECT type_id FROM entities WHERE type_id = 'feature:014-hook-migration-yolo-stopsh-and'"`. If missing, register via: `sqlite3 $ENTITY_DB_PATH "INSERT INTO entities (type_id, entity_type, entity_id, name, status) VALUES ('feature:014-hook-migration-yolo-stopsh-and', 'feature', '014-hook-migration-yolo-stopsh-and', 'hook-migration-yolo-stopsh-and', 'active')"`
- [ ] Set up the test state: ensure the feature's `.meta.json` at `docs/features/014-hook-migration-yolo-stopsh-and/.meta.json` has `"lastCompletedPhase": "specify"` (it should already — if not, temporarily set it)
- [ ] Run the hook from the project root with stdin pipe (the hook reads stdin via `INPUT=$(cat)` on line 17 — without stdin it hangs): `OUTPUT=$(echo '{"stop_hook_active":false}' | bash plugins/iflow/hooks/yolo-stop.sh); echo "$OUTPUT"`
- [ ] Parse and inspect the JSON output: `echo "$OUTPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('reason','NO REASON FIELD'))"` — confirm the reason field contains `"Invoke /iflow:design"`

**Done when:** Parsed `reason` field contains `"Invoke /iflow:design"` — confirming the engine path derived `specify → design` via PHASE_SEQUENCE index lookup. If the output shows a different phase, uses the fallback path, or has no reason field, investigate before proceeding.

**Files:** None (read-only verification)
