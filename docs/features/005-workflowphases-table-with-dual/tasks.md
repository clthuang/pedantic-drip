# Tasks: WorkflowPhases Table with Dual-Dimension Status Model

## Phase 1: Migration 3 — Schema Creation

No dependencies on other phases.

### Task 1.1: Write tests for migration table schema [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Depends on**: none
- **AC**: AC-1
- [ ] Test `workflow_phases` table exists after migration 3
- [ ] Test columns: `type_id` (PK), `workflow_phase`, `kanban_column` (NOT NULL DEFAULT 'backlog'), `last_completed_phase`, `mode`, `backward_transition_reason`, `updated_at` (NOT NULL)
- [ ] Test FK from `type_id` → `entities(type_id)` via PRAGMA
- [ ] Test schema_version = 3 after migration
- [ ] Use `PRAGMA table_info(workflow_phases)` pattern from existing tests
- **Done when**: All schema assertion tests written and fail (RED) because migration 3 doesn't exist yet

### Task 1.2: Write tests for indexes and trigger [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Depends on**: none (parallel with 1.1)
- **AC**: AC-2
- [ ] Test index `idx_wp_kanban_column` exists via `PRAGMA index_list`
- [ ] Test index `idx_wp_workflow_phase` exists
- [ ] Test trigger `enforce_immutable_wp_type_id` exists via `sqlite_master`
- [ ] Test trigger prevents UPDATE of `type_id` (INSERT row, attempt UPDATE, expect error)
- **Done when**: All index/trigger tests written and fail (RED)

### Task 1.3: Write tests for CHECK constraints [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Depends on**: none (parallel with 1.1, 1.2)
- **AC**: AC-4
- [ ] Test invalid `workflow_phase` value → IntegrityError
- [ ] Test invalid `kanban_column` value → IntegrityError
- [ ] Test invalid `last_completed_phase` value → IntegrityError
- [ ] Test invalid `mode` value → IntegrityError
- [ ] Test NULL for nullable columns (`workflow_phase`, `last_completed_phase`, `mode`, `backward_transition_reason`) → succeeds
- [ ] Test valid enum values → succeeds
- **Done when**: All CHECK constraint tests written and fail (RED)

### Task 1.4: Write test for fresh DB migration safety [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Depends on**: none (parallel with 1.1-1.3)
- **AC**: AC-3
- [ ] Test creates brand-new `EntityDatabase(tmp_path / "fresh.db")`
- [ ] Test verifies all 3 migrations ran (schema_version = 3)
- [ ] Test both `entities` and `workflow_phases` tables exist
- **Done when**: Fresh DB test written and fails (RED)

### Task 1.5: Write tests for FK enforcement [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Depends on**: none (parallel with 1.1-1.4)
- **AC**: AC-16
- [ ] Test INSERT with non-existent `type_id` → IntegrityError
- [ ] Test DELETE entity that has `workflow_phases` row → IntegrityError (ON DELETE NO ACTION) using raw SQL `db._conn.execute('DELETE FROM entities WHERE type_id = ?', ...)`
- **Note**: After migration 2, entities PK is `uuid`; `type_id` is UNIQUE. DELETE WHERE type_id = ? is valid because type_id is UNIQUE.
- **Done when**: FK enforcement tests written and fail (RED)

### Task 1.6: Implement migration 3 function [impl]
- **File**: `plugins/iflow/hooks/lib/entity_registry/database.py`
- **Depends on**: 1.1, 1.2, 1.3, 1.4, 1.5 (all Phase 1 tests)
- **AC**: AC-1, AC-2, AC-3, AC-4, AC-16
- [ ] Implement `_create_workflow_phases_table(conn)` with self-managed transaction pattern (copy migration 2 structure)
- [ ] DDL from `docs/features/004-status-taxonomy-design-and-sch/design.md` section "Interface 1: Migration Function" (CREATE TABLE block ~line 129)
- [ ] CREATE TABLE with columns, CHECK constraints, FK, DEFAULT values
- [ ] CREATE INDEX for `idx_wp_kanban_column` and `idx_wp_workflow_phase`
- [ ] CREATE TRIGGER `enforce_immutable_wp_type_id`
- [ ] Register as `MIGRATIONS[3]` — target version is `max(MIGRATIONS)`
- **Done when**: `_create_workflow_phases_table` function exists in database.py and registered in MIGRATIONS dict

### Task 1.7: Verify Phase 1 — all tests pass [verify]
- **Depends on**: 1.6
- [ ] Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- [ ] Zero regressions in existing tests
- [ ] All new Phase 1 tests pass (GREEN)
- **Done when**: Full test suite passes with zero failures

## Phase 2: CRUD Methods

Depends on: Phase 1 (table must exist)

### Task 2.1: Write tests for create_workflow_phase [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Depends on**: 1.7 (Phase 1 verified)
- **AC**: AC-5
- [ ] Test create for existing entity → returns dict with all 7 columns
- [ ] Test create for non-existent entity → ValueError
- [ ] Test create duplicate (PK conflict) → ValueError
- [ ] Test CHECK constraint violation (invalid kanban_column) → ValueError
- [ ] Test default values applied (kanban_column='backlog', others NULL)
- **Done when**: All create tests written and fail (RED)

### Task 2.2: Write tests for get_workflow_phase [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Depends on**: 1.7 (parallel with 2.1)
- **AC**: AC-6
- [ ] Test get existing → returns dict
- [ ] Test get non-existent → returns None
- [ ] Test all 7 columns present in returned dict
- **Done when**: All get tests written and fail (RED)

### Task 2.3: Write tests for update_workflow_phase [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Depends on**: 1.7 (parallel with 2.1, 2.2)
- **AC**: AC-7
- [ ] Test update single field → only that field changes, `updated_at` refreshed
- [ ] Test update multiple fields → all change
- [ ] Test pass None explicitly → field set to NULL
- [ ] Test omit field (not provided) → field unchanged (sentinel `_UNSET` behavior)
- [ ] Test update non-existent → ValueError
- [ ] Test invalid enum value → ValueError (CHECK constraint)
- [ ] Test update with no optional fields (only type_id) → only `updated_at` refreshes
- [ ] Test pass kanban_column=None explicitly → ValueError (NOT NULL constraint violation)
- **Done when**: All update tests written and fail (RED)

### Task 2.4: Write tests for delete_workflow_phase [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Depends on**: 1.7 (parallel with 2.1-2.3)
- **AC**: AC-8
- [ ] Test delete existing → row removed
- [ ] Test delete non-existent → ValueError
- [ ] Test get returns None after delete
- **Done when**: All delete tests written and fail (RED)

### Task 2.5: Write tests for list_workflow_phases [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Depends on**: 1.7 (parallel with 2.1-2.4)
- **AC**: AC-9
- [ ] Test list all → returns all rows
- [ ] Test filter by kanban_column → filtered results
- [ ] Test filter by workflow_phase → filtered results
- [ ] Test both filters → AND logic
- [ ] Test empty result → empty list
- **Done when**: All list tests written and fail (RED)

### Task 2.6: Implement _UNSET sentinel and CRUD methods [impl]
- **File**: `plugins/iflow/hooks/lib/entity_registry/database.py`
- **Depends on**: 2.1, 2.2, 2.3, 2.4, 2.5 (all Phase 2 tests)
- **AC**: AC-5, AC-6, AC-7, AC-8, AC-9
- [ ] Add `_UNSET = object()` module-level sentinel (above EntityDatabase class)
- [ ] Implement `create_workflow_phase(type_id, ...)` — FK check SELECT, INSERT, SELECT-back
- [ ] IntegrityError message inspection: "UNIQUE constraint failed" → ValueError("Workflow phase already exists for: {type_id}"), "CHECK constraint failed" → ValueError("Invalid value: {detail}"), other → re-raise as ValueError with original message (ref: design.md Component 2)
- [ ] Implement `get_workflow_phase(type_id)` — SELECT WHERE PK, return dict or None
- [ ] Implement `update_workflow_phase(type_id, ...)` — set_parts/params dynamic builder with `_UNSET` checks, always include `updated_at = _now_iso()`, SELECT-back; IntegrityError → ValueError
- [ ] Implement `delete_workflow_phase(type_id)` — SELECT check, DELETE; raise ValueError if not found
- [ ] Implement `list_workflow_phases(kanban_column=None, workflow_phase=None)` — SELECT with optional WHERE clauses, AND logic
- **Done when**: All 5 CRUD methods implemented in EntityDatabase class

### Task 2.7: Verify Phase 2 — all tests pass [verify]
- **Depends on**: 2.6
- [ ] Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- [ ] Zero regressions in existing tests
- [ ] All Phase 1 + Phase 2 tests pass (GREEN)
- **Done when**: Full test suite passes with zero failures

## Phase 3: Backfill Function

Depends on: Phase 1 (table), Phase 2 (for test fixtures)

### Task 3.1: Write tests for STATUS_TO_KANBAN mapping [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_backfill.py`
- **Depends on**: 2.7 (Phase 2 verified)
- **AC**: AC-10, AC-11
- [ ] Test planned → backlog
- [ ] Test active → wip
- [ ] Test completed → completed
- [ ] Test abandoned → completed
- [ ] Test unmapped status (e.g., "draft") → default to "planned" (backlog) with warning logged (two-step: warn → default → map)
- **Done when**: STATUS_TO_KANBAN tests written and fail (RED)

### Task 3.2: Write tests for _derive_next_phase [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_backfill.py`
- **Depends on**: 2.7 (parallel with 3.1)
- **AC**: AC-10, AC-14, AC-17
- [ ] Test "specify" → "design"
- [ ] Test "design" → "create-plan"
- [ ] Test "implement" → "finish"
- [ ] Test "finish" → "finish" (terminal state per D-5)
- [ ] Test NULL → None
- [ ] Test unrecognized value → None
- **Done when**: _derive_next_phase tests written and fail (RED)

### Task 3.3: Write tests for _resolve_meta_path [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_backfill.py`
- **Depends on**: 2.7 (parallel with 3.1, 3.2)
- **AC**: AC-14, AC-18
- [ ] Test entity with artifact_path (directory) → `{artifact_path}/.meta.json` if file exists
- [ ] Test entity with artifact_path (file, e.g. brainstorm .prd.md) → derived path doesn't exist, falls through to convention fallback
- [ ] Test entity without artifact_path → convention fallback `{artifacts_root}/{entity_type}s/{entity_id}/.meta.json` — note: `entity_id` here is the slug portion (e.g., `005-workflowphases-table-with-dual`), NOT the full `type_id` (e.g., `feature:005-workflowphases-table-with-dual`). The entity dict from the DB query has both columns; use `entity_id` for path construction.
- [ ] Test neither path exists → returns None
- **Done when**: _resolve_meta_path tests written and fail (RED)

### Task 3.3b: Write tests for 3-tier status resolution fallback chain [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_backfill.py`
- **Depends on**: 2.7 (parallel with 3.1-3.3)
- **AC**: AC-10, AC-14, AC-18
- [ ] Test entity with `.meta.json` status="active" and entities.status=NULL → uses "active" from .meta.json
- [ ] Test entity with no `.meta.json` and entities.status="completed" → uses "completed" from DB
- [ ] Test entity with no `.meta.json` and entities.status=NULL → defaults to "planned" → kanban="backlog"
- [ ] Test entity with `.meta.json` status="active" AND entities.status="completed" → .meta.json wins (priority 1)
- [ ] Test entity with unmapped status value (e.g., "draft") → default to "planned" with warning logged
- **Done when**: Status resolution fallback tests written and fail (RED)

### Task 3.4: Write integration tests for backfill feature entities [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_backfill.py`
- **Depends on**: 2.7 (parallel with 3.1-3.3b)
- **AC**: AC-10, AC-14, AC-17
- [ ] Test active feature with .meta.json → correct kanban_column, workflow_phase, last_completed_phase, mode
- [ ] Test completed feature → kanban_column=completed, workflow_phase=finish
- [ ] Test planned feature → kanban_column=backlog, workflow_phase=NULL
- [ ] Test abandoned feature with lastCompletedPhase → kanban_column=completed, workflow_phase=next-after-last
- **Done when**: Feature entity backfill integration tests written and fail (RED)

### Task 3.5: Write tests for backfill brainstorm/backlog entities [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_backfill.py`
- **Depends on**: 2.7 (parallel with 3.1-3.4)
- **AC**: AC-11
- [ ] Test brainstorm entity → workflow_phase=NULL, kanban_column from status
- [ ] Test backlog entity → workflow_phase=NULL, kanban_column from status
- **Done when**: Brainstorm/backlog backfill tests written and fail (RED)

### Task 3.6: Write test for backfill excludes project entities [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_backfill.py`
- **Depends on**: 2.7 (parallel with 3.1-3.5)
- **AC**: AC-12
- [ ] Test register project entity, run backfill → no workflow_phases row created
- **Done when**: Project exclusion test written and fails (RED)

### Task 3.7: Write tests for backfill idempotency [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_backfill.py`
- **Depends on**: 2.7 (parallel with 3.1-3.6)
- **AC**: AC-13
- [ ] Test run backfill twice → second run creates 0, skips all, no errors
- [ ] Test existing rows not modified on re-run
- [ ] Test return dict has created/skipped/errors keys
- **Done when**: Idempotency tests written and fail (RED)

### Task 3.8: Write tests for .meta.json error tolerance [test]
- **File**: `plugins/iflow/hooks/lib/entity_registry/test_backfill.py`
- **Depends on**: 2.7 (parallel with 3.1-3.7)
- **AC**: AC-18
- [ ] Test malformed JSON → warning logged, defaults used
- [ ] Test missing .meta.json → defaults used, no error
- [ ] Test invalid lastCompletedPhase → NULL, warning logged
- [ ] Test invalid mode → NULL, warning logged
- **Done when**: Error tolerance tests written and fail (RED)

### Task 3.9: Implement constants and helper functions [impl]
- **File**: `plugins/iflow/hooks/lib/entity_registry/backfill.py`
- **Depends on**: 3.1, 3.2, 3.3, 3.3b (tests for constants/helpers)
- **AC**: AC-10, AC-14
- [ ] Implement `PHASE_SEQUENCE` tuple constant
- [ ] Implement `STATUS_TO_KANBAN` dict constant
- [ ] Implement `VALID_MODES` frozenset constant
- [ ] Implement `_derive_next_phase(last_completed)` → str | None
- [ ] Implement `_read_meta_json(path)` → dict | None — wraps existing `_read_json` in backfill.py. **Pre-check**: grep for `def _read_json` in backfill.py to confirm it exists before implementing; if missing, implement `_read_json` first.
- [ ] Implement `_resolve_meta_path(entity, artifacts_root)` → str | None
- **Done when**: All 6 constants/helpers implemented in backfill.py

### Task 3.10: Implement backfill_workflow_phases main function [impl]
- **File**: `plugins/iflow/hooks/lib/entity_registry/backfill.py`
- **Depends on**: 3.9, 3.4, 3.5, 3.6, 3.7, 3.8 (helpers + all remaining tests)
- **AC**: AC-10, AC-11, AC-12, AC-13, AC-14, AC-17, AC-18
- [ ] Query entities (exclude projects)
- [ ] Per-entity: resolve meta path → read meta → resolve status (3-tier: .meta.json → entities.status → "planned")
- [ ] For unmapped status: log warning THEN default to "planned" THEN map via STATUS_TO_KANBAN (two-step: warn → default → map)
- [ ] Derive fields: kanban_column, workflow_phase, last_completed_phase, mode
- [ ] INSERT OR IGNORE via `db._conn.execute()` per design TD-10
- [ ] Track created/skipped/errors counters
- [ ] Return summary dict `{"created": int, "skipped": int, "errors": list[str]}`
- **Done when**: backfill_workflow_phases function implemented

### Task 3.11: Verify Phase 3 — all tests pass [verify]
- **Depends on**: 3.10
- [ ] Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- [ ] Zero regressions in existing tests (AC-15)
- [ ] All Phase 1 + Phase 2 + Phase 3 tests pass (GREEN)
- **Done when**: Full test suite passes with zero failures

## Dependency Graph

```
Phase 1 (parallel test writing):
  1.1 ─┐
  1.2 ─┤
  1.3 ─┼──→ 1.6 ──→ 1.7
  1.4 ─┤
  1.5 ─┘

Phase 2 (parallel test writing, blocked by Phase 1):
  1.7 ──→ 2.1 ─┐
          2.2 ─┤
          2.3 ─┼──→ 2.6 ──→ 2.7
          2.4 ─┤
          2.5 ─┘

Phase 3 (parallel test writing, blocked by Phase 2):
  2.7 ──→ 3.1 ─┐
          3.2 ─┤
          3.3 ─┼──→ 3.9 ──→ 3.10 ──→ 3.11
          3.3b─┤          ↑
          3.4 ─┤          │
          3.5 ─┤          │
          3.6 ─┼──────────┘
          3.7 ─┤
          3.8 ─┘
```

## Summary

- **Total tasks**: 25
- **Phases**: 3
- **Parallel groups**: 3 (within each phase, tests run in parallel; impl blocks on all tests)
- **Files modified**: 3 (`database.py`, `test_database.py`, `backfill.py` + test file)
