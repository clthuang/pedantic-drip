---
last-invoked: 2026-04-18
feature: 084-structured-execution-data
---

# Plan: Structured Workflow Execution Data

## Implementation Order

```
Phase 0: Baselines (test counts, validate warnings)
    ↓
Phase 1: database.py — migration 10 + insert_phase_event + query_phase_events (TDD)
    ↓
Phase 2: workflow_state_server.py — dual-write + record_backward_event + query_phase_analytics (TDD)
    ↓
Phase 3: Docs + final verification
```

**Parallelism:** None needed — feature is ~280 LOC across 2 files. Sequential within each phase. Phase 3 (docs) runs last.

## Phase 0: Baselines

**Why:** Capture pre-change state for Phase 3 regression gate.
**Complexity:** Low

### Task-level breakdown:
- Task 0.1: Capture `validate.sh` warning count + entity registry test count + workflow_state_server test count to `agent_sandbox/084-baselines.txt`.

**Done when:** Baselines file exists with all counts.

## Phase 1: database.py additions (C-1 + C-2 + C-3)

**Why:** Migration 10 + insert/query methods must exist before dual-write can reference them.
**Why this order:** Dependency root — Phase 2 calls `db.insert_phase_event` and `db.query_phase_events`.
**Complexity:** Medium (migration with backfill + 2 new methods)

### Task-level breakdown:
- Task 1.1: Write migration 10 tests [TDD red] — AC-1 (table exists), AC-2 (schema correct), AC-3 (3 indexes exist), AC-8 (backfill populates from metadata), AC-9 (malformed metadata skipped), AC-10 (source='backfill' tag), AC-18 (idempotent via schema_version).
- Task 1.2: Implement `_migration_10_phase_events` [TDD green] — per design I-1. Add to MIGRATIONS dict as key 10. CREATE TABLE + 3 composite indexes + backfill loop + schema_version upsert.
- Task 1.3: Write `insert_phase_event` tests [TDD red] — verify INSERT with all columns, verify None return, verify event_type CHECK constraint.
- Task 1.4: Implement `EntityDatabase.insert_phase_event` [TDD green] — per design I-2. Keyword-only params, simple INSERT.
- Task 1.5: Write `query_phase_events` tests [TDD red] — verify filtering by type_id, project_id, phase, event_type; verify limit cap at 500; verify ORDER BY timestamp DESC.
- Task 1.6: Implement `EntityDatabase.query_phase_events` [TDD green] — per design I-3. Dynamic WHERE, LIMIT, dict conversion.

**Done when:** All Phase 1 tests green; existing entity registry tests pass unchanged.

## Phase 2: workflow_state_server.py additions (C-4 + C-5 + C-6)

**Why:** Dual-write wiring + new MCP tools. Depends on Phase 1 (insert/query methods).
**Complexity:** Medium (dual-write inside transactions + 2 new MCP tools + _compute_durations helper)

### Task-level breakdown:
- Task 2.1: Write dual-write tests [TDD red] — AC-4 (transition_phase inserts started event), AC-5 (complete_phase inserts completed event with iterations), AC-6 (skipped phases get skipped events), AC-16 (INSERT failure doesn't break transition), AC-19 (metadata JSON still written).
- Task 2.2: Implement dual-write in `_process_transition_phase` + `_process_complete_phase` [TDD green] — per design I-4/I-5. Refactor inline `_iso_now()` to capture-once `ts` variable. try/except around INSERT.
- Task 2.3: Write `record_backward_event` tests [TDD red] — AC-7 (backward event with source_phase/target_phase/reason).
- Task 2.4: Implement `record_backward_event` MCP tool [TDD green] — per design I-6. Accepts project_id as parameter.
- Task 2.5: Write `query_phase_analytics` tests [TDD red] — AC-11 (phase_duration), AC-11b (multi-cycle pairing), AC-12 (iteration_summary), AC-13 (backward_frequency), AC-14 (raw_events), AC-15 (project_id filter).
- Task 2.6: Implement `query_phase_analytics` MCP tool + `_compute_durations` [TDD green] — per design I-7. Z-normalization in `_compute_durations`. 4 query types.

**Done when:** All Phase 2 tests green; existing workflow_state_server tests pass unchanged (AC-17).

## Phase 3: Docs + final verification (C-7)

**Why:** Ship gate.
**Complexity:** Low

### Task-level breakdown:
- Task 3.1: Update README_FOR_DEV.md with phase_events table + query_phase_analytics tool note (AC-20).
- Task 3.2: Run full entity registry test suite — count ≥ baseline + ~10 new.
- Task 3.3: Run full workflow_state_server test suite — count ≥ baseline + ~10 new.
- Task 3.4: Run `./validate.sh` — 0 errors, warnings ≤ baseline.
- Task 3.5: Delete `agent_sandbox/084-baselines.txt`.

**Done when:** All gates green; README updated; baselines file removed.

## Risks

- **R-1 Backfill data quality** — old entities may have incomplete metadata. Mitigated by `source='backfill'` tag + AC-9 malformed-metadata handling.
- **R-2 Dual-write failure inside transaction** — mitigated by try/except at INSERT call site (AC-16).
- **R-3 Timestamp format inconsistency** — mitigated by Z-normalization in `_compute_durations` (design I-7).

## Deliverables Summary

**Edited files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` — migration 10 + 2 new methods + MIGRATIONS dict
- `plugins/pd/hooks/lib/entity_registry/test_database.py` OR new `test_phase_events.py` — migration + insert + query tests
- `plugins/pd/mcp/workflow_state_server.py` — dual-write + 2 new MCP tools + helper
- `plugins/pd/mcp/test_workflow_state_server.py` — dual-write + MCP tool tests
- `README_FOR_DEV.md` — brief note

**Test delta:** ≥15 new tests covering AC-1 through AC-20 + AC-11b.
