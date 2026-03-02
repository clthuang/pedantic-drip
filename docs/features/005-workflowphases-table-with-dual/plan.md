# Plan: WorkflowPhases Table with Dual-Dimension Status Model

## Implementation Order

Three phases, ordered by dependency: schema first (no deps), CRUD second (depends on schema), backfill third (depends on CRUD + schema).

```
Phase 1: Migration 3 (Schema)
  └── Tests → Implementation → Verify
       No dependencies on other phases.

Phase 2: CRUD Methods
  └── Tests → Implementation → Verify
       Depends on: Phase 1 (table must exist)

Phase 3: Backfill Function
  └── Tests → Implementation → Verify
       Depends on: Phase 1 (table), Phase 2 (for test fixtures)
```

## Phase 1: Migration 3 — Schema Creation

**Goal**: Add `_create_workflow_phases_table` to `MIGRATIONS[3]` in `database.py`.

**File**: `plugins/iflow/hooks/lib/entity_registry/database.py`
**Test file**: `plugins/iflow/hooks/lib/entity_registry/test_database.py` (following existing pattern — migration and CRUD tests co-located)

### Step 1.1: Test — Migration creates table with correct schema

Write tests that verify:
- Table `workflow_phases` exists after migration 3
- Columns: `type_id` (PK), `workflow_phase`, `kanban_column` (NOT NULL DEFAULT 'backlog'), `last_completed_phase`, `mode`, `backward_transition_reason`, `updated_at` (NOT NULL)
- FK from `type_id` → `entities(type_id)`
- Schema version = 3 after migration
- Use `PRAGMA table_info(workflow_phases)` pattern from existing tests

### Step 1.2: Test — Migration creates indexes and trigger

Write tests that verify:
- Index `idx_wp_kanban_column` exists (verify via `PRAGMA index_list`)
- Index `idx_wp_workflow_phase` exists
- Trigger `enforce_immutable_wp_type_id` exists (verify via `sqlite_master`)
- Trigger prevents UPDATE of `type_id` (INSERT row, attempt UPDATE type_id, expect error)

### Step 1.3: Test — CHECK constraints enforce enums

Write tests that verify:
- Invalid `workflow_phase` value → IntegrityError
- Invalid `kanban_column` value → IntegrityError
- Invalid `last_completed_phase` value → IntegrityError
- Invalid `mode` value → IntegrityError
- NULL for nullable columns → succeeds
- Valid enum values → succeeds

### Step 1.4: Test — Migration safe on fresh DB

Write test that:
- Creates a brand-new `EntityDatabase(tmp_path / "fresh.db")`
- Verifies all 3 migrations ran (schema_version = 3)
- Both `entities` and `workflow_phases` tables exist

### Step 1.5: Test — FK enforcement

Write tests that verify:
- INSERT with non-existent `type_id` → IntegrityError
- DELETE entity that has `workflow_phases` row → IntegrityError (ON DELETE NO ACTION)
  - Note: Use raw SQL `db._conn.execute('DELETE FROM entities WHERE type_id = ?', ...)` since no `delete_entity()` method exists. This is consistent with how migration tests use raw connections.

### Step 1.6: Implement — Migration function

Implement `_create_workflow_phases_table(conn)`:
- Self-managed transaction pattern (copy migration 2 structure)
- DDL from ADR-004 Appendix E adapted for migration 3
- Register in `MIGRATIONS[3]` — the target version is `max(MIGRATIONS)` (no separate SCHEMA_VERSION constant exists; adding `3: _create_workflow_phases_table` to the dict is sufficient)

### Step 1.7: Verify Phase 1

- Run full test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- Confirm zero regressions in existing tests
- Confirm all new Phase 1 tests pass

## Phase 2: CRUD Methods

**Goal**: Add 5 CRUD methods to `EntityDatabase` class.

**File**: `plugins/iflow/hooks/lib/entity_registry/database.py`
**Test file**: `plugins/iflow/hooks/lib/entity_registry/test_database.py` (same file as Phase 1 tests)

### Step 2.1: Test — create_workflow_phase

Write tests:
- Create for existing entity → returns dict with all 7 columns
- Create for non-existent entity → ValueError
- Create duplicate (PK conflict) → ValueError
- CHECK constraint violation (invalid kanban_column) → ValueError
- Default values applied (kanban_column='backlog', others NULL)

### Step 2.2: Test — get_workflow_phase

Write tests:
- Get existing → returns dict
- Get non-existent → returns None
- Verify all 7 columns present in returned dict

### Step 2.3: Test — update_workflow_phase

Write tests:
- Update single field → only that field changes, `updated_at` refreshed
- Update multiple fields → all change
- Pass None explicitly → field set to NULL
- Omit field (not provided) → field unchanged
- Update non-existent → ValueError
- Invalid enum value → ValueError (CHECK constraint)
- Verify `_UNSET` sentinel behavior: omitted vs None
- Update with no optional fields (only type_id) → only `updated_at` refreshes, all other fields unchanged (valid no-op that exercises the always-present `updated_at = ?` SET clause)
- Pass kanban_column=None explicitly → ValueError (NOT NULL constraint violation via IntegrityError catch — validates sentinel vs NOT NULL column interaction)

### Step 2.4: Test — delete_workflow_phase

Write tests:
- Delete existing → row removed
- Delete non-existent → ValueError
- Verify get returns None after delete

### Step 2.5: Test — list_workflow_phases

Write tests:
- List all → returns all rows
- Filter by kanban_column → filtered results
- Filter by workflow_phase → filtered results
- Both filters → AND logic
- Empty result → empty list

### Step 2.6: Implement — _UNSET sentinel and CRUD methods

Implement in order:
1. `_UNSET = object()` module-level sentinel
2. `create_workflow_phase` — FK check SELECT, INSERT, SELECT-back
3. `get_workflow_phase` — SELECT WHERE PK
4. `update_workflow_phase` — set_parts/params dynamic builder with `_UNSET` checks, SELECT-back
5. `delete_workflow_phase` — SELECT check, DELETE
6. `list_workflow_phases` — SELECT with optional WHERE clauses

IntegrityError handling per design: catch, inspect message, re-raise as ValueError.

### Step 2.7: Verify Phase 2

- Run full test suite
- Confirm zero regressions
- Confirm all Phase 1 + Phase 2 tests pass

## Phase 3: Backfill Function

**Goal**: Add `backfill_workflow_phases()` to `backfill.py` with helpers.

**Files**:
- `plugins/iflow/hooks/lib/entity_registry/backfill.py` (main)
- Test file alongside existing backfill tests

### Step 3.1: Test — Status-to-kanban mapping

Write tests for `STATUS_TO_KANBAN` constant:
- planned → backlog
- active → wip
- completed → completed
- abandoned → completed
- Unmapped status value (e.g., "draft") → default to "planned" (backlog) with warning logged. The backfill function must handle `STATUS_TO_KANBAN.get(status, "backlog")` with a warning for unknown values.

### Step 3.2: Test — Phase derivation

Write tests for `_derive_next_phase`:
- "specify" → "design"
- "design" → "create-plan"
- "implement" → "finish"
- "finish" → "finish" (terminal state — spec D-5 says "If lastCompletedPhase is finish, set to finish")
- NULL → None
- Unrecognized value → None

### Step 3.3: Test — Meta path resolution

Write tests for `_resolve_meta_path`:
- Entity with artifact_path (directory) → `{artifact_path}/.meta.json` if file exists
- Entity with artifact_path (file, e.g. brainstorm .prd.md) → derived path doesn't exist, falls through to convention fallback
- Entity without artifact_path → convention fallback `{artifacts_root}/{entity_type}s/{entity_id}/.meta.json`
- Neither path exists → returns None

Note: No file-vs-directory special casing needed. The function tries `os.path.isfile()` on the derived path — if artifact_path is a file, `{file_path}/.meta.json` naturally doesn't exist.

### Step 3.3b: Test — Status resolution fallback chain

Write dedicated tests for the 3-tier status resolution:
- Entity with `.meta.json` status="active" and entities.status=NULL → uses "active" from .meta.json
- Entity with no `.meta.json` and entities.status="completed" → uses "completed" from DB
- Entity with no `.meta.json` and entities.status=NULL → defaults to "planned" → kanban="backlog"
- Entity with `.meta.json` status="active" AND entities.status="completed" → .meta.json wins (priority 1)
- Entity with unmapped status value (e.g., "draft") → default to "planned" with warning logged

### Step 3.4: Test — Backfill feature entities

Write integration tests:
- Active feature with .meta.json → correct kanban_column, workflow_phase, last_completed_phase, mode
- Completed feature → kanban_column=completed, workflow_phase=finish
- Planned feature → kanban_column=backlog, workflow_phase=NULL
- Abandoned feature with lastCompletedPhase → kanban_column=completed, workflow_phase=next-after-last

### Step 3.5: Test — Backfill brainstorm/backlog entities

Write tests:
- Brainstorm entity → workflow_phase=NULL, kanban_column from status
- Backlog entity → workflow_phase=NULL, kanban_column from status

### Step 3.6: Test — Backfill excludes project entities

Write test:
- Register project entity, run backfill → no workflow_phases row created

### Step 3.7: Test — Backfill idempotency

Write tests:
- Run backfill twice → second run creates 0, skips all, no errors
- Existing rows not modified on re-run
- Return dict has created/skipped/errors keys

### Step 3.8: Test — .meta.json error tolerance

Write tests:
- Malformed JSON → warning logged, defaults used
- Missing .meta.json → defaults used, no error
- Invalid lastCompletedPhase → NULL, warning logged
- Invalid mode → NULL, warning logged

### Step 3.9: Implement — Constants and helpers

Implement:
1. `PHASE_SEQUENCE` tuple constant
2. `STATUS_TO_KANBAN` dict constant
3. `VALID_MODES` frozenset constant
4. `_derive_next_phase(last_completed)` → str | None
5. `_read_meta_json(path)` → dict | None (calls co-located `_read_json` in same backfill.py module — no cross-module import needed)
6. `_resolve_meta_path(entity, artifacts_root)` → str | None

### Step 3.10: Implement — backfill_workflow_phases

Implement main function:
1. Query entities (exclude projects)
2. Per-entity: resolve meta path → read meta → resolve status → derive fields → INSERT OR IGNORE via `db._conn.execute()` (per design TD-10 — bypasses CRUD for idempotent bulk insert, acceptable within same package)
3. For unmapped status values: log warning THEN default to "planned" before mapping via STATUS_TO_KANBAN (two-step: warn → default → map, not silent .get() fallthrough)
4. Track created/skipped/errors counters
5. Return summary dict

### Step 3.11: Verify Phase 3

- Run full test suite
- Confirm zero regressions
- Confirm all Phase 1 + Phase 2 + Phase 3 tests pass

## Final Verification

- `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v` — all tests pass
- Manual smoke test: construct EntityDatabase on existing DB, verify migration runs, verify CRUD methods work
- Verify schema_version = 3 after construction

## Risk Mitigations

| Risk | Mitigation in Plan |
|------|-------------------|
| R-1: Self-managed transaction | Phase 1 tests verify both success and rollback paths |
| R-2: .meta.json inconsistencies | Phase 3 tests cover malformed, missing, and invalid data |
| R-3: Sentinel complexity | Phase 2 tests explicitly verify _UNSET vs None behavior |
| R-4: Path resolution failures | Phase 3 tests cover all path scenarios including None returns |
