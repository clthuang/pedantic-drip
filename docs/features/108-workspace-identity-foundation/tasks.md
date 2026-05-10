# Tasks: Feature 108 — Workspace Identity Foundation

- **Project:** P003-entity-system-redesign
- **Feature:** 108-workspace-identity-foundation
- **Phase:** Plan (atomic task breakdown)
- **Status:** Draft (revised, iteration 2)
- **Created:** 2026-05-10
- **Plan:** [`plan.md`](plan.md)
- **Spec:** [`spec.md`](spec.md)
- **Design:** [`design.md`](design.md)

**Total tasks:** 78 across 8 phases (A=6, B=16, C=8, D=8, E=10, F=12, G=7, H=11). Tasks numbered `N.M` where `N` is phase index (1–8) and `M` is task index within phase. Task IDs in plan.md (`T-A0`, `T-B1`, …) map to `(N=1,M=0)`, `(N=2,M=1)`, … Each task: 5–15 minute scope, single concrete edit or test addition, verifiable DoD. Each task body includes a "**Why:**" line tracing to the plan item / FR / AC / design component (per SUGGESTION 11).

**TDD note:** Schema-touching implementation tasks pair with explicit RED test tasks **scheduled BEFORE the implementation task** (per WARNING 18). Test tasks state expected RED state and the implementation task that turns them GREEN.

**Path conventions:** Database paths use `~/.claude/pd/entities/entities.db` for the live DB and `tmp/migration-test.db` for synthetic test DBs. Project root is the repo root (`/Users/terry/projects/pedantic-drip`).

**`make_v10_db()` shared helper:** Defined ONCE in Task 2.0 (per task-reviewer BLOCKER 1). All schema-touching tests reference this helper.

---

## Phase 1 (A): Schema Bootstrap

### Task 1.0: Capture pre-change baseline (PRE_SHA + PRE_EPOCH)

**Why:** plan T-A0; rollback anchor (§6.1); BLOCKER 7 (Stage 0 baseline missing).

**Files:**
- `docs/features/108-workspace-identity-foundation/baseline.json` (new file)

**DoD:**
- Run `git rev-parse HEAD` and `date +%s` and capture into JSON: `{"pre_sha": "<sha>", "pre_epoch": <epoch>}`.
- File committed before any code change.
- `git log -1 --format='%H' baseline.json` returns a commit predating any source-code edit for feature 108.

**Depends on:** none

**Estimated:** 5 minutes

---

### Task 1.1: Add `_UNKNOWN_WORKSPACE_UUID` constant + import-time assertion + byte-equality test

Pin the deterministic UUID for `__unknown__` rows in `database.py` per design §6.5, with a paired test for the pinned literal and RFC 4122 v4 conformance.

**Why:** plan T-A1; FR-4 §"Pinned literal value"; AC for `_UNKNOWN_WORKSPACE_UUID` byte-equality (spec line 116).

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (add module-level constants)
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_unknown_workspace_uuid_pinned_literal`)

**DoD:**
- Module defines `_UNKNOWN_WORKSPACE_UUID_SEED`, `_compute_unknown_workspace_uuid()`, `_UNKNOWN_WORKSPACE_UUID`, plus the import-time assertion `_UNKNOWN_WORKSPACE_UUID == "6250c8a6-5306-443f-b225-477a040016ea"`.
- New test asserts byte-equality (NOT recompute), `version == 4`, `variant == uuid.RFC_4122`.
- `pytest plugins/pd/hooks/lib/entity_registry/test_database.py::test_unknown_workspace_uuid_pinned_literal -xvs` passes.

**Depends on:** 1.0

**Estimated:** 10 minutes

---

### Task 1.2: Extract `_compute_legacy_project_id` private helper

**Why:** plan T-A2; FR-3 ("git-SHA computation moves into a private helper"); design §3.4.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/project_identity.py` (add private function)

**DoD:**
- `_compute_legacy_project_id(working_dir: str) -> str` defined, NOT cached.
- Reuses git-SHA chain (root commit → HEAD → path hash) from existing `detect_project_id`.
- `python -c "from entity_registry.project_identity import _compute_legacy_project_id; print(_compute_legacy_project_id('.'))"` returns 12-char lowercase hex.
- New unit test `test_compute_legacy_project_id_returns_12char_hex` passes.

**Depends on:** 1.0

**Estimated:** 10 minutes

---

### Task 1.3: Add `workspaces` DDL constants + read-helper stubs

**Why:** plan T-A3; FR-4 schema; design §6.2.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (add DDL constants + EntityDatabase methods)

**DoD:**
- `_WORKSPACES_TABLE_DDL` and `_WORKSPACES_INDEX_DDL` constants defined per FR-4.
- `EntityDatabase.query_workspace_by_uuid`, `query_workspace_by_legacy`, `query_workspace_by_root` defined; raise `RuntimeError` if `workspaces` table missing (pre-Migration-11 callers are illegal).
- `python -c "from entity_registry.database import _WORKSPACES_TABLE_DDL; assert 'project_id_legacy' in _WORKSPACES_TABLE_DDL"` passes.

**Depends on:** 1.1

**Estimated:** 15 minutes

---

### Task 1.4: Create `test_helpers.py` with `get_test_workspace_uuid()`

**Why:** plan T-A4; design Decision 12 (test helpers must NOT recompute); consumed by every Phase F fixture rewrite.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_helpers.py` (new file)

**DoD:**
- `test_helpers.py` exports `get_test_workspace_uuid() -> str` returning `_UNKNOWN_WORKSPACE_UUID`.
- Module imports `_UNKNOWN_WORKSPACE_UUID` from `entity_registry.database` (NO recompute).
- `from entity_registry.test_helpers import get_test_workspace_uuid` succeeds in fresh Python process.

**Depends on:** 1.1

**Estimated:** 10 minutes

---

### Task 1.5: Unit test — `get_test_workspace_uuid()` returns pinned literal

**Why:** plan T-A5; design test deliverable D1 (helper returns byte-equal pinned literal).

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_test_helpers.py` (new file)

**DoD:**
- `test_test_helpers.py::test_get_test_workspace_uuid_returns_pinned_literal` asserts the return value byte-equals `"6250c8a6-5306-443f-b225-477a040016ea"`.
- `pytest plugins/pd/hooks/lib/entity_registry/test_test_helpers.py -xvs` exits 0.

**Depends on:** 1.4

**Estimated:** 5 minutes

---

## Phase 2 (B): Migration 11 Forward

### Task 2.0: Define `make_v10_db()` shared test helper (BLOCKER 1 prerequisite)

**Why:** task-reviewer BLOCKER 1 (`make_v10_db()` previously undefined; referenced by 2.1, 2.2, 2.3, 3.3, 3.6, 4.5).

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add helper function near top of file)

**DoD:**
- `make_v10_db(tmp_path) -> sqlite3.Connection` defined.
- Helper creates an in-memory `sqlite3.Connection` (or `tmp_path/migration-test.db`) and applies all DDL up to and including schema_version=10 using the pre-11 DDL constants extracted from `database.py` (NO migration 11 applied).
- Helper sets `_metadata.schema_version='10'` (string).
- Helper documented with docstring explaining: "Builds a SQLite DB at exactly schema_version=10 to support Migration 11 RED tests; do NOT use for live-DB testing."
- All later test tasks (2.1, 2.2, 2.7, 2.8, 2.9, 2.10, 2.11, 3.4, 3.7) import and call this helper.

**Depends on:** 1.0

**Estimated:** 15 minutes

---

### Task 2.1: RED — schema-shape + UNIQUE-constraint tests for entities post-Migration-11

**Why:** plan T-B1; AC-1, 2, 3, 4, 5, 6, 28; TDD precedence per WARNING 18.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_migration_11_table_shape`, `test_migration_11_unique_constraint`)

**DoD:**
- `test_migration_11_table_shape`: builds v10 DB via `make_v10_db()` (Task 2.0); runs `_migrate(conn, 11)`; asserts entities has 12 columns with `workspace_uuid` at index 1; asserts `project_id` and `parent_type_id` absent; asserts `_metadata.schema_version='11'`.
- `test_migration_11_unique_constraint`: same workspace+type_id raises IntegrityError; different workspace+same type_id succeeds.
- Both tests currently FAIL (Migration 11 not yet implemented) — captured in implementation log as RED.

**Depends on:** 2.0

**Estimated:** 15 minutes

**Tests:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-28.

---

### Task 2.2: RED — trigger-shape, immutability, and index-shape tests

**Why:** plan T-B2; AC-9, 10; TDD precedence.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_no_parent_type_id_triggers`, `test_workspace_uuid_immutable_trigger`, `test_indexes_after_migration_11`)

**DoD:**
- `test_no_parent_type_id_triggers`: post-mig `SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='entities'` returns exactly the 7 names from FR-6.
- `test_workspace_uuid_immutable_trigger`: `UPDATE entities SET workspace_uuid=...` raises with message `'workspace_uuid is immutable'`.
- `test_indexes_after_migration_11`: post-mig has `idx_workspace_uuid` and `idx_workspace_entity_type`; lacks `idx_project_id`, `idx_project_entity_type`, `idx_parent_type_id`.
- All three tests currently FAIL (RED).

**Depends on:** 2.0, 2.1

**Estimated:** 10 minutes

**Tests:** AC-9, AC-10.

---

### Task 2.3: RED — `wp_autofill_workspace_uuid` + `wp_reject_orphaned_insert` trigger pair tests

**Why:** plan T-B3; spec FR-7 step 11 (revised; both triggers); design Decision 8.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_workflow_phases_autofill_trigger`, `test_workflow_phases_orphan_insert_rejected`)

**DoD:**
- `test_workflow_phases_autofill_trigger`: builds v10 DB via `make_v10_db()`; migrates to 11; registers entity with `type_id='feature:043-foo'`; INSERT into workflow_phases with `workspace_uuid=NULL` and matching `type_id`; asserts AFTER trigger fills `workspace_uuid` from `entities.workspace_uuid`.
- `test_workflow_phases_orphan_insert_rejected`: builds v10 DB via `make_v10_db()`; migrates to 11; INSERT into workflow_phases with `type_id='feature:no-such-entity'` (no matching entity row); asserts BEFORE INSERT trigger raises `sqlite3.IntegrityError`.
- Both tests currently FAIL (RED).

**Depends on:** 2.0, 2.1

**Estimated:** 10 minutes

**Tests:** workflow_phases invariant AC.

---

### Task 2.4: Implement Migration 11 envelope (steps 1–3) — scaffold + concurrent re-check guard

**Why:** plan T-B4; FR-7 steps 1–3; design Decision 9 (re-check guard mirrors `database.py:1396-1418`).

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (add new function + register in MIGRATIONS dict)

**DoD:**
- `_migration_11_workspace_identity(conn)` defined with `PRAGMA foreign_keys = OFF` outside transaction + `BEGIN IMMEDIATE` block.
- First in-tx statement: re-check `_metadata.schema_version`; ROLLBACK + return if `>= 11` (per design Decision 9, replicating `database.py:1396-1418`).
- Function registered in `MIGRATIONS[11]`.
- `pytest test_migration_11_table_shape` makes progress past "no migration registered" stage.

**Depends on:** 2.1, 2.2, 2.3, 1.3

**Estimated:** 15 minutes

---

### Task 2.5: Implement Migration 11 step 0 (workspace mapping audit + JSON emit + `__unknown__` WARN + empty-table edge case)

**Why:** plan T-B5; FR-7 step 0; AC-36, AC-41; WARNING 19 (empty entities edge case).

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity`)
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_migration_11_workspace_bootstrap`, `test_workspace_mapping_audit_emitted`, `test_migration_11_unknown_project_id`, `test_migration_11_empty_entities_table`)

**DoD:**
- Pre-tx: `SELECT DISTINCT project_id FROM entities`; for each id assign `_UNKNOWN_WORKSPACE_UUID` if `__unknown__` else fresh UUID.
- **Edge case (WARNING 19):** When entities table is empty (e.g., fresh DB), step 0 emits an empty-mapping JSON `{"workspaces": []}` and proceeds; no abort.
- Atomic-write `<workspace_root>/.claude/pd/migrations/migration-11-workspace-mapping.json` (mkdir parent + tempfile + os.replace).
- Emit one WARN log per `__unknown__` count: `"Migration 11: N entities with project_id='__unknown__' attributed to canonical unknown-workspace UUID; review with claim_unknown_entities post-migration."`
- Four new tests assert: bootstrap row count matches distinct project_id count; mapping JSON file emitted with valid UUIDs matching `workspaces` rows; `__unknown__` injection produces correct mapping entry + WARN substring + `_metadata.schema_version='11'`; empty-entities case emits empty-mapping JSON + completes successfully.

**Depends on:** 2.4, 1.1

**Estimated:** 15 minutes

**Tests:** AC-36, AC-41.

---

### Task 2.6: Implement Migration 11 step 4 (pre-migration FK check)

**Why:** plan T-B6; FR-7 step 4; AC-35 (atomicity).

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity`)

**DoD:**
- After re-check guard but before workspaces creation: execute `PRAGMA foreign_key_check`.
- If non-empty: ROLLBACK and raise `RuntimeError(f"pre-migration FK check non-empty: {rows}")`.
- Synthetic test injecting an FK violation pre-mig confirms abort + `schema_version='10'` retained.

**Depends on:** 2.4

**Estimated:** 10 minutes

**Tests:** AC-35.

---

### Task 2.7: Implement Migration 11 step 5 (workspaces table create + bootstrap insert one row per pre-mig project_id)

**Why:** plan T-B7; FR-7 step 5; FR-4 schema; design §6.2.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity`)

**DoD:**
- `CREATE TABLE workspaces` per FR-4 DDL (5 columns + PK).
- `CREATE INDEX idx_workspaces_legacy ON workspaces(project_id_legacy)`.
- Insert one row per distinct pre-mig project_id (uuid + legacy + project_root from JOIN with `projects`).
- Synthetic test confirms post-step COUNT(*) workspaces matches distinct project_id count.

**Depends on:** 2.5

**Estimated:** 10 minutes

**Tests:** FR-4 ACs (line 97-99).

---

### Task 2.8: Implement Migration 11 step 6 (pre-migration parent_type_id orphan assertion)

**Why:** plan T-B8; FR-7 step 6 (separate from step 7 data copy per design §7.1, BLOCKER 2).

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity`)
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_migration_11_aborts_on_parent_type_id_orphan`)

**DoD:**
- After step 5 (workspaces exist) but before step 7 (data copy): execute `SELECT COUNT(*) AS n, GROUP_CONCAT(uuid) AS offenders FROM entities WHERE parent_uuid IS NULL AND parent_type_id IS NOT NULL`.
- If `n > 0`: ROLLBACK and raise with message listing offender UUIDs.
- New test injects a synthetic offender row in v10 DB; asserts migration aborts cleanly with offender UUID in error message; asserts `_metadata.schema_version='10'` retained.

**Depends on:** 2.7

**Estimated:** 15 minutes

**Tests:** AC for FR-7 §"Pre-migration assertion" (spec line 218).

---

### Task 2.9: Implement Migration 11 steps 7–8 (entities_new create + JOIN backfill + DROP/RENAME)

**Why:** plan T-B9; FR-5 DDL; FR-7 steps 7, 8; turns Task 2.1 GREEN.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity`)

**DoD:**
- `CREATE TABLE entities_new` per FR-5 DDL (12 cols, `workspace_uuid` at index 1, UNIQUE(workspace_uuid, type_id)).
- `INSERT INTO entities_new ... SELECT ... FROM entities e JOIN workspaces w ON e.project_id = w.project_id_legacy`; assert `COUNT(*) entities_new == COUNT(*) entities` pre-mig.
- `DROP TABLE entities`; `ALTER TABLE entities_new RENAME TO entities`.
- `test_migration_11_table_shape` (Task 2.1) now PASSES (GREEN).
- `test_migration_11_unique_constraint` (Task 2.1) now PASSES (GREEN).

**Depends on:** 2.7, 2.8

**Estimated:** 15 minutes

**Tests:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-6.

---

### Task 2.10: Implement Migration 11 steps 9–10 (recreate 7 triggers + 5 indexes)

**Why:** plan T-B10; FR-6 trigger list; FR-7 steps 9, 10; turns Task 2.2 GREEN.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity`)

**DoD:**
- `DROP TRIGGER IF EXISTS` for `enforce_no_self_parent`, `enforce_no_self_parent_update`, `enforce_immutable_project_id`.
- `CREATE` 7 triggers from FR-6 including new `enforce_immutable_workspace_uuid` raising `RAISE(ABORT, 'workspace_uuid is immutable — use re-attribution API')`.
- `CREATE` 5 indexes (`idx_entity_type`, `idx_status`, `idx_parent_uuid`, `idx_workspace_uuid`, `idx_workspace_entity_type`).
- `DROP IF EXISTS` for `idx_project_id`, `idx_project_entity_type`, `idx_parent_type_id`.
- `test_no_parent_type_id_triggers`, `test_workspace_uuid_immutable_trigger`, `test_indexes_after_migration_11` (Task 2.2) all GREEN.

**Depends on:** 2.9

**Estimated:** 10 minutes

**Tests:** AC-9, AC-10.

---

### Task 2.11: Implement Migration 11 step 11 (`workflow_phases.workspace_uuid` ALTER + backfill + autofill + reject trigger pair + idx)

**Why:** plan T-B11; FR-7 step 11 (revised — BOTH triggers per spec edit); design Decision 8; turns Task 2.3 GREEN.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity`)

**DoD:**
- `ALTER TABLE workflow_phases ADD COLUMN workspace_uuid TEXT REFERENCES workspaces(uuid)`.
- `UPDATE workflow_phases SET workspace_uuid = (SELECT e.workspace_uuid FROM entities e WHERE e.type_id = workflow_phases.type_id)`.
- `CREATE INDEX idx_wp_workspace_uuid ON workflow_phases(workspace_uuid)`.
- `CREATE TRIGGER wp_autofill_workspace_uuid AFTER INSERT ON workflow_phases WHEN NEW.workspace_uuid IS NULL BEGIN UPDATE workflow_phases SET workspace_uuid = (SELECT e.workspace_uuid FROM entities e WHERE e.type_id = NEW.type_id) WHERE rowid = NEW.rowid; END;`.
- `CREATE TRIGGER wp_reject_orphaned_insert BEFORE INSERT ON workflow_phases WHEN NEW.workspace_uuid IS NULL AND NOT EXISTS (SELECT 1 FROM entities e WHERE e.type_id = NEW.type_id) BEGIN SELECT RAISE(ABORT, 'workflow_phases insert references unknown entity type_id'); END;`.
- `test_workflow_phases_autofill_trigger` and `test_workflow_phases_orphan_insert_rejected` (Task 2.3) both GREEN.

**Depends on:** 2.9

**Estimated:** 15 minutes

**Tests:** workflow_phases invariant AC.

---

### Task 2.12: Implement Migration 11 step 12 (rebuild `sequences` keyed on workspace_uuid)

**Why:** plan T-B12; FR-7 step 12.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity`)
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_migration_11_sequences_keyed_on_workspace`)

**DoD:**
- `CREATE TABLE sequences_new` with `(workspace_uuid, entity_type)` PK + FK to workspaces.
- `INSERT INTO sequences_new (workspace_uuid, entity_type, next_val) SELECT w.uuid, s.entity_type, s.next_val FROM sequences s JOIN workspaces w ON s.project_id = w.project_id_legacy`.
- `DROP TABLE sequences`; `ALTER TABLE sequences_new RENAME TO sequences`.
- New test asserts `PRAGMA table_info(sequences)` shows `(workspace_uuid, entity_type, next_val)` columns and PK is `(workspace_uuid, entity_type)`.

**Depends on:** 2.7

**Estimated:** 10 minutes

---

### Task 2.13: Implement Migration 11 step 13 (rebuild `projects` with workspace_uuid NOT NULL)

**Why:** plan T-B13; FR-4 step (e); FR-7 step 13.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity`)
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_migration_11_projects_workspace_not_null`)

**DoD:**
- `CREATE TABLE projects_new` mirroring 13 existing cols + `workspace_uuid TEXT NOT NULL REFERENCES workspaces(uuid)`.
- `INSERT INTO projects_new SELECT p.*, w.uuid FROM projects p JOIN workspaces w ON p.project_id = w.project_id_legacy`.
- `DROP TABLE projects`; `ALTER TABLE projects_new RENAME TO projects`; recreate any indexes/triggers.
- New test asserts `workspace_uuid` is NOT NULL in `projects` and FK enforced.

**Depends on:** 2.7

**Estimated:** 10 minutes

---

### Task 2.14: Implement Migration 11 steps 14–17 (entities_fts rebuild + in-tx schema stamp + commit + post-FK check)

**Why:** plan T-B14; FR-7 steps 14, 15, 16, 17; design Decision 1 (in-tx stamp); AC-28.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity`)
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_migration_11_in_transaction_stamp`)

**DoD:**
- Step 14: `DROP TABLE entities_fts`; `CREATE VIRTUAL TABLE entities_fts USING fts5(...)`; `INSERT INTO entities_fts SELECT ... FROM entities` (mirrors Migration 7).
- Step 15: `INSERT OR REPLACE INTO _metadata(key,value) VALUES ('schema_version','11')` INSIDE the transaction (per design Decision 1 + `database.py:1604-1618`).
- Step 16: `COMMIT`.
- Step 17: `PRAGMA foreign_keys = ON`; `PRAGMA foreign_key_check` empty (else raise).
- `test_migration_11_in_transaction_stamp` simulates rollback after stamp; asserts `_metadata.schema_version='10'` (full tx rolled back).
- Full forward Migration 11 GREEN suite passes: `pytest -k migration_11 plugins/pd/hooks/lib/entity_registry/ -xvs` exits 0.

**Depends on:** 2.9, 2.10, 2.11, 2.12, 2.13

**Estimated:** 15 minutes

**Tests:** AC-28.

---

### Task 2.15: Idempotency + concurrent-runners + partial-failure rollback tests

**Why:** plan T-B15; AC-35; design test deliverables D4 + D5 + D6.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_migration_11_forward_idempotent`, `test_migration_11_concurrent_runners`, `test_migration_11_partial_failure_rollback`)

**DoD:**
- `test_migration_11_forward_idempotent`: second `_migrate()` call is no-op (re-check guard exits early).
- `test_migration_11_concurrent_runners`: `multiprocessing.Pool(2)` racing `_migrate`; both exit 0; exactly one row per distinct project_id; no duplicates.
- `test_migration_11_partial_failure_rollback`: monkeypatch step 8 to raise; assert `schema_version='10'`, `entities` shape unchanged, `workspaces` table absent, all 9 pre-up triggers + 8 indexes intact.
- All three pass.

**Depends on:** 2.14

**Estimated:** 15 minutes

**Tests:** AC-35.

---

## Phase 3 (C): Migration 11 Reverse + `MIGRATIONS_DOWN`

### Task 3.1: Add `MIGRATIONS_DOWN` dict + `_migrate_down` dispatcher

**Why:** plan T-C1; design §6.6; out-of-scope item "Reversibility for Migrations 1–10".

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (add module-level dict + helper)
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_migrate_down_dispatcher_unknown_target`)

**DoD:**
- `MIGRATIONS_DOWN: dict[int, Callable] = {}` defined.
- `_migrate_down(conn, target_version)`: descending iteration; `NotImplementedError(f"Reverse migration for schema_version {v} not implemented")` for unknown target.
- Per-step BEGIN IMMEDIATE + re-check guard + in-tx stamp pattern matches forward.
- `test_migrate_down_dispatcher_unknown_target` asserts `NotImplementedError` for `target_version=9`.

**Depends on:** 1.0

**Estimated:** 15 minutes

---

### Task 3.2: SQLite ≥3.35 assertion + reverse stub `_migration_11_workspace_identity_down`

**Why:** plan T-C2; FR-8 (DROP COLUMN requires SQLite 3.35); design §7.2.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (add reverse function + register in MIGRATIONS_DOWN)

**DoD:**
- `_migration_11_workspace_identity_down(conn)` defined.
- Pre-tx assertion: `assert sqlite3.sqlite_version_info >= (3, 35, 0)` with message naming current version.
- Body stubbed (raises `NotImplementedError("steps 3-15 pending")`).
- Registered: `MIGRATIONS_DOWN[11] = _migration_11_workspace_identity_down`.

**Depends on:** 3.1

**Estimated:** 10 minutes

---

### Task 3.3: Implement reverse steps 1–2 (envelope + reverse re-check guard)

**Why:** plan T-C3; design §7.2 mirror of forward envelope.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity_down`)

**DoD:**
- `PRAGMA foreign_keys = OFF`; `BEGIN IMMEDIATE`.
- Reverse re-check guard: `SELECT value FROM _metadata WHERE key='schema_version'`; if `int(v) <= 10`: ROLLBACK; return.

**Depends on:** 3.2

**Estimated:** 10 minutes

---

### Task 3.4: Implement reverse steps 3–7 (pre-down assertion + entities_old rebuild + parent_type_id JOIN backfill + DROP/RENAME)

**Why:** plan T-C4; FR-8 §"Pre-down assertion"; AC-11, AC-12.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity_down`)

**DoD:**
- Step 3: pre-down assertion per FR-8; abort with `RuntimeError` if cross-workspace `parent_uuid` edges exist.
- Step 4: `CREATE TABLE entities_old` with the pre-11 schema (13 cols: `project_id`, `parent_type_id`, `UNIQUE(project_id, type_id)`).
- Step 5: `INSERT INTO entities_old ... SELECT ... FROM entities e JOIN workspaces w ON e.workspace_uuid = w.uuid` (restores `project_id`).
- Step 6: `UPDATE entities_old SET parent_type_id = (SELECT type_id FROM entities_old AS p WHERE p.uuid = entities_old.parent_uuid) WHERE parent_uuid IS NOT NULL`.
- Step 7: `DROP TABLE entities`; `ALTER RENAME entities_old → entities`.

**Depends on:** 3.3

**Estimated:** 15 minutes

**Tests:** AC-11, AC-12.

---

### Task 3.5: Implement reverse steps 8–13 (recreate 9 pre-11 triggers + 6 indexes; reverse workflow_phases/sequences/projects/fts)

**Why:** plan T-C5; FR-8 §steps 7–9; design §7.2.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity_down`)

**DoD:**
- Step 8: recreate the 9 pre-11 triggers (incl. `parent_type_id` triggers + `enforce_immutable_project_id`).
- Step 9: recreate the 6 pre-11 indexes (`idx_entity_type`, `idx_status`, `idx_parent_type_id`, `idx_parent_uuid`, `idx_project_id`, `idx_project_entity_type`).
- Step 10: DROP TRIGGER `wp_autofill_workspace_uuid`, `wp_reject_orphaned_insert`; DROP INDEX `idx_wp_workspace_uuid`; ALTER TABLE workflow_phases DROP COLUMN workspace_uuid.
- Step 11: rebuild sequences (mirror of forward step 12).
- Step 12: rebuild projects (mirror of forward step 13).
- Step 13: rebuild entities_fts (mirror of forward step 14).

**Depends on:** 3.4

**Estimated:** 15 minutes

---

### Task 3.6: Implement reverse steps 14–16 (DROP workspaces + 11→10 stamp + commit + post-FK check)

**Why:** plan T-C6; FR-8 step 10–12.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` (extend `_migration_11_workspace_identity_down`)

**DoD:**
- Step 14: `DROP TABLE workspaces`; `DROP INDEX IF EXISTS idx_workspaces_legacy`.
- Step 15: `INSERT OR REPLACE INTO _metadata(key,value) VALUES ('schema_version','10')` INSIDE the transaction.
- Step 16: COMMIT; `PRAGMA foreign_keys = ON`; post-FK check empty.

**Depends on:** 3.5

**Estimated:** 10 minutes

---

### Task 3.7: AC-13 round-trip checksum test (up → down → up byte-identical)

**Why:** plan T-C7; AC-11, AC-12, AC-13, AC-35.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_migration_11_round_trip_checksum`, `test_migration_11_up_and_down`)

**DoD:**
- Synthetic v10 DB (via `make_v10_db()`) with ≥10 representative rows (mix of `parent_uuid`-only and both-set; no `parent_type_id`-only).
- Up → checksum1; down → assert pre-up schema match; up → checksum2; assert checksum1 == checksum2.
- `test_migration_11_up_and_down` runs the full round-trip on a copy of the live `~/.claude/pd/entities/entities.db`; asserts row counts and `entities` content match (modulo `workspaces.created_at`). **Guard:** test skips when `_metadata.schema_version != 10` in live DB (per SUGGESTION 12).
- Both pass; AC-13 verified.

**Depends on:** 3.6, 2.14

**Estimated:** 15 minutes

**Tests:** AC-11, AC-12, AC-13.

---

### Task 3.8: Capture pre-up + post-down `sqlite3 .schema` diff and commit as artifact

**Why:** plan T-C8; WARNING 10.

**Files:**
- `docs/features/108-workspace-identity-foundation/migration-11-schema-diff.txt` (new file)

**DoD:**
- Build v10 DB via `make_v10_db()`; capture `sqlite3 db.sqlite '.schema'` → `pre-up.sql`.
- Apply migration 11 then `_migrate_down(conn, 10)`; capture `.schema` → `post-down.sql`.
- `diff -u pre-up.sql post-down.sql` captured into `migration-11-schema-diff.txt` (expected: empty diff modulo whitespace).
- File committed as artifact.

**Depends on:** 3.7

**Estimated:** 10 minutes

---

## Phase 4 (D): `resolve_workspace_uuid` + `fcntl.flock`

### Task 4.1: Rename `detect_project_id` → `resolve_workspace_uuid` (no alias) + remove `ENTITY_PROJECT_ID`

**Why:** plan T-D1; FR-3; AC-17 (no alias kept).

**Files:**
- `plugins/pd/hooks/lib/entity_registry/project_identity.py` (rename function in-place; update docstring per design §6.1)

**DoD:**
- `def detect_project_id` no longer exists in `project_identity.py`.
- `resolve_workspace_uuid(working_dir: str | None = None) -> str` defined with `@functools.lru_cache(maxsize=1)`.
- Docstring matches design §6.1 contract.
- All `ENTITY_PROJECT_ID` references removed: `grep -rn 'ENTITY_PROJECT_ID' plugins/pd/` returns 0 hits.

**Depends on:** 1.0

**Estimated:** 10 minutes

---

### Task 4.2: RED — corrupted file + extra-keys + wrong-schema-version tests

**Why:** plan T-D2; AC-22, AC-23; TDD precedence.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_project_identity.py` (add `test_ensure_workspace_uuid_corrupted`, `_wrong_schema_version`, `_extra_keys`)

**DoD:**
- Three new tests asserting:
  - Corrupted JSON in `.claude/pd/workspace.json` → `WorkspaceCorruptedError` exit code 2.
  - `schema_version=99` → `WorkspaceCorruptedError`.
  - Extra unknown top-level key → WARN log emitted; resolver still returns valid UUID.
- All three currently FAIL (resolver step 2 not implemented).

**Depends on:** 4.1

**Estimated:** 10 minutes

---

### Task 4.3: Implement FR-3 step 1 (`ENTITY_WORKSPACE_UUID` env var) with format validation

**Why:** plan T-D3; FR-3 step 1.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/project_identity.py` (modify `resolve_workspace_uuid` body)
- `plugins/pd/hooks/lib/entity_registry/test_project_identity.py` (add `test_resolve_workspace_uuid_env_var_precedence`)

**DoD:**
- Function reads `os.environ.get('ENTITY_WORKSPACE_UUID')`; if set, validate (36-char lowercase hyphenated) and return.
- Bad-format raises `ValueError`.
- Test asserts env-var value returned when valid; bad value raises `ValueError`.

**Depends on:** 4.1

**Estimated:** 10 minutes

---

### Task 4.4: Add `_atomic_workspace_json_write` with `fcntl.flock(LOCK_EX)`

**Why:** plan T-D4; FR-2 §"fcntl.flock-based cross-process synchronization"; design §6.3.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/project_identity.py` (add private function)

**DoD:**
- `_atomic_workspace_json_write(target_path, uuid_value) -> str` per design §6.3.
- Uses `fcntl.flock(LOCK_EX)` on `<target_path>.lock` sentinel.
- Inside critical section: re-check existence (loser case returns existing UUID); else tempfile in same dir + `os.replace`; re-read content for return.
- `os.makedirs(parent, exist_ok=True)`.
- No shell-level mktemp ever invoked from this code path.

**Depends on:** 4.1

**Estimated:** 15 minutes

---

### Task 4.5: Isolated unit tests for `_atomic_workspace_json_write` (loser case + exception cleanup)

**Why:** plan T-D8; SUGGESTION 13 (harden helper before integration race test).

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_project_identity.py` (add `test_atomic_workspace_json_write_loser_case`, `test_atomic_workspace_json_write_exception_cleans_tempfile`)

**DoD:**
- `test_atomic_workspace_json_write_loser_case`: pre-write a workspace.json file; call `_atomic_workspace_json_write` with a different UUID; assert returned value equals the existing file's UUID (not the candidate); assert mtime preserved.
- `test_atomic_workspace_json_write_exception_cleans_tempfile`: monkeypatch `os.replace` to raise mid-flight; assert no orphan tempfiles in `.claude/pd/`; assert lock released.
- Both pass.

**Depends on:** 4.4

**Estimated:** 10 minutes

---

### Task 4.6: Implement FR-3 step 2 (file read with strict schema validation)

**Why:** plan T-D5; FR-3 step 2; AC-22, AC-23; turns Task 4.2 GREEN.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/project_identity.py` (modify `resolve_workspace_uuid` body; add new exceptions)

**DoD:**
- Build `target_path = <working_dir>/.claude/pd/workspace.json`.
- If file exists: parse JSON; assert `schema_version == 1` (else raise `WorkspaceCorruptedError` with exit code 2 + structured stderr via `safe_emit_hook_json`).
- Validate `workspace_uuid` is 36-char lowercase hyphenated.
- Tolerate extra unknown top-level keys with WARN log; do not abort.
- Three tests in Task 4.2 now GREEN.

**Depends on:** 4.1, 4.3, 4.4

**Estimated:** 15 minutes

**Tests:** AC-22, AC-23.

---

### Task 4.7: Implement FR-3 step 2.5 (DB recovery — single match / NULL / ambiguous) + step 3 (fresh write)

**Why:** plan T-D6; FR-3 step 2.5 + step 3; AC-7, AC-8, AC-38, AC-39.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/project_identity.py` (extend `resolve_workspace_uuid` body)
- `plugins/pd/hooks/lib/entity_registry/test_project_identity.py` (add `test_fr3_step25_single_match`, `_no_match`, `_ambiguous`, `test_resolve_workspace_uuid_fresh_write`)

**DoD:**
- After step 2 returns no file: open DB read-only; query `SELECT uuid, project_id_legacy FROM workspaces WHERE project_root = ?` with `os.path.abspath(working_dir)`.
- Exactly one row → regenerate workspace.json with that row's UUID + legacy; return it; NO WARN.
- 0 rows OR `project_root IS NULL` → fall through to step 3.
- Multiple rows → fall through to step 3 with ambiguity-named WARN log.
- Step 3: fresh UUID via `uuid_mod.uuid4()` (or `_new_uuid()` if F6 lands); build payload `{workspace_uuid, schema_version:1, created_at, created_by:"session-start.sh"}`; call `_atomic_workspace_json_write`.
- Emit WARN log on populated DB (no match): `"No workspace_uuid match in workspaces table; generated fresh UUID — entities may be orphaned, run claim_unknown_entities to reattribute"`.
- Four new tests pass. Tests for AC-8/AC-38/AC-39 require workspaces table → depend on 2.14.

**Depends on:** 4.6, 2.14

**Estimated:** 15 minutes

**Tests:** AC-7, AC-8, AC-38, AC-39.

---

### Task 4.8: AC-37 multiprocessing race test with `os.fork` barrier

**Why:** plan T-D7; AC-15, AC-37; design test deliverable D8.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_project_identity.py` (add `test_workspace_resolve_concurrent`)

**DoD:**
- `multiprocessing.Pool(2)` against empty `.claude/pd/`.
- `multiprocessing.Barrier(2)` (or `Event`) forces both workers to hit flock acquire within the same millisecond.
- Each worker calls `resolve_workspace_uuid(tmp_workspace_root)` and returns result.
- Asserts `race_results[0] == race_results[1]`; both equal on-disk file content; on-disk file is well-formed JSON with valid UUID.

**Depends on:** 4.7

**Estimated:** 15 minutes

**Tests:** AC-15, AC-37.

---

## Phase 5 (E): Hook + MCP Boundary Updates

### Task 5.1: Audit `--project-root` call sites + capture as artifact

**Why:** plan T-E0; WARNING 13 (enumerate before adding flag).

**Files:**
- `agent_sandbox/2026-05-10/108-cli-audit/cli-audit.txt` (new file)

**DoD:**
- Run `grep -rnE '\--project-root|args\.project_root' plugins/pd/hooks/ plugins/pd/mcp/ --include='*.py'` and capture full output.
- File committed with one-line header documenting command + date.
- Audit lists ≥1 call site; each row enumerates file:line.

**Depends on:** 1.0

**Estimated:** 5 minutes

---

### Task 5.2: Add `ensure_workspace_uuid` shell helper to `lib/session-start-helpers.sh`

**Why:** plan T-E1; FR-2; FR-11; AC-40 (no shell-level mktemp).

**Files:**
- `plugins/pd/hooks/lib/session-start-helpers.sh` (add new function)

**DoD:**
- `ensure_workspace_uuid` shells out: `plugins/pd/.venv/bin/python -c "from entity_registry.project_identity import resolve_workspace_uuid; print(resolve_workspace_uuid())" 2>/dev/null`; captures into `WORKSPACE_UUID`; exports it; routes errors via `safe_emit_hook_json`.
- No `mktemp` in this function: `grep -n 'mktemp.*workspace' plugins/pd/hooks/` returns 0.

**Depends on:** 4.7

**Estimated:** 15 minutes

**Tests:** AC-40.

---

### Task 5.3: Update `session-start.sh` to call `ensure_workspace_uuid` pre-DB-read + replace project_id reads

**Why:** plan T-E2; FR-11; AC-40.

**Files:**
- `plugins/pd/hooks/session-start.sh`

**DoD:**
- `session-start.sh` calls `ensure_workspace_uuid` BEFORE any DB read.
- `session-start.sh:119` Python snippet replaces `meta.get("project_id")` with `meta.get("workspace_uuid")`.
- `session-start.sh:453,461,474-475` slug-render block uses `${workspace_uuid_short}-${project_slug}` (first 8 hex chars of UUID, no hyphens).

**Depends on:** 5.2

**Estimated:** 10 minutes

**Tests:** AC-40.

---

### Task 5.4: Add `--workspace-uuid` CLI flag to Python entry points enumerated in 5.1

**Why:** plan T-E3; FR-12; supports test override.

**Files:**
- Files identified by Task 5.1 audit (e.g., `plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py` and any other entry points containing `--project-root`).

**DoD:**
- Each entry point's argparse adds `--workspace-uuid` (default `None`).
- When set, entry point uses it directly (skips `resolve_workspace_uuid` call).
- When unset, entry point calls `resolve_workspace_uuid(args.project_root)`.
- New unit test `test_workspace_uuid_cli_flag_precedence` exercises both paths.

**Depends on:** 5.1, 4.7

**Estimated:** 15 minutes

---

### Task 5.5: Add lazy global `_workspace_uuid` to `mcp/entity_server.py`

**Why:** plan T-E4; design §6.9 lazy global pattern.

**Files:**
- `plugins/pd/mcp/entity_server.py` (modify `_resolve_project_id` → `_resolve_workspace_uuid`, `_project_id` → `_workspace_uuid`)

**DoD:**
- Module-level lazy global `_workspace_uuid: str | None = None`.
- Helper `_resolve_workspace_uuid()` populates `_workspace_uuid` on first call via `resolve_workspace_uuid()`.
- Existing `_resolve_project_id` and `_project_id` removed.
- All existing call sites within `entity_server.py` reference the new symbol.

**Depends on:** 4.7

**Estimated:** 10 minutes

---

### Task 5.6: Rewrite `register_entity` MCP signature — drop `parent_type_id`, accept `workspace_uuid`

**Why:** plan T-E5; FR-9, FR-10; AC-31; AC-19 (idempotency).

**Files:**
- `plugins/pd/mcp/entity_server.py` (modify `_process_register_entity`)
- `plugins/pd/mcp/test_entity_server.py` (update existing tests; add `test_register_entity_rejects_parent_type_id_kwarg`, `test_register_entity_idempotent`)

**DoD:**
- Signature: `register_entity(entity_type, entity_id, name, *, workspace_uuid: str | None = None, artifact_path=None, status=None, parent_uuid=None, metadata=None)` per design §6.9.
- `parent_type_id` parameter REMOVED.
- When `workspace_uuid=None`, server resolves via lazy global `_workspace_uuid`.
- `test_register_entity_rejects_parent_type_id_kwarg` asserts `TypeError` raised.
- `test_register_entity_idempotent` (AC-19) asserts double-call with same args returns same UUID + no duplicate row.

**Depends on:** 5.5

**Estimated:** 15 minutes

**Tests:** AC-31, AC-19.

---

### Task 5.7: Rewrite `_upsert_project` caller + `db.upsert_project` signature

**Why:** plan T-E6; design §6.10.

**Files:**
- `plugins/pd/mcp/entity_server.py` (line 124 region: `_upsert_project` helper)
- `plugins/pd/hooks/lib/entity_registry/database.py` (modify `upsert_project` signature ~line 3951)
- `plugins/pd/mcp/test_entity_server.py` (lines 318, 373 test callers updated)

**DoD:**
- `db.upsert_project` signature requires `workspace_uuid: str` parameter (per design §6.10); raises `sqlite3.IntegrityError` if `workspace_uuid` doesn't match a `workspaces` row.
- `_upsert_project` caller passes `workspace_uuid=_workspace_uuid` (the lazy global).
- Test callers at `test_entity_server.py:318, 373` updated to pass `workspace_uuid=get_test_workspace_uuid()`.

**Depends on:** 5.6, 1.4

**Estimated:** 10 minutes

---

### Task 5.8: Update `reconciliation_orchestrator/__main__.py` + `entity_status.py`

**Why:** plan T-E7; AC-30; FR-12.

**Files:**
- `plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py`
- `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`

**DoD:**
- `__main__.py`: import `from entity_registry.project_identity import resolve_workspace_uuid` (was `detect_project_id`).
- `__main__.py:88` region: `resolve_workspace_uuid(args.project_root)`.
- `entity_status.py:21,29,47,72,80,87,110`: every `project_id` parameter renamed to `workspace_uuid`; default removed (caller must supply).
- All downstream `update_entity`/`query_entities` calls accept `workspace_uuid=`.
- `grep -n 'from .* import .*resolve_workspace_uuid' plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py` returns ≥1 hit.

**Depends on:** 4.1

**Estimated:** 15 minutes

**Tests:** AC-30.

---

### Task 5.9: Update `meta-json-guard.sh` to read workspace.json + export `WORKSPACE_UUID`

**Why:** plan T-E8; AC-29 (env var inheritance into subprocesses).

**Files:**
- `plugins/pd/hooks/meta-json-guard.sh`
- `plugins/pd/hooks/tests/test-hooks.sh` (add subprocess test case asserting `WORKSPACE_UUID` exported)

**DoD:**
- Hook sources `lib/session-start-helpers.sh::ensure_workspace_uuid` (or fail-soft equivalent).
- Hook exports `WORKSPACE_UUID` env var into any subprocess.
- Failure to read workspace.json produces structured WARN via `safe_emit_hook_json`; does NOT block.
- New test case spawns subprocess; asserts `bash -c 'echo $WORKSPACE_UUID'` returns expected UUID.

**Depends on:** 5.2

**Estimated:** 15 minutes

**Tests:** AC-29.

---

### Task 5.10: Add `.gitignore` entries + doctor `check_workspace_uuid_consistency`

**Why:** plan T-E9 + doctor extension; AC-27, AC-20, AC-21.

**Files:**
- `.gitignore` (project root)
- `plugins/pd/hooks/lib/doctor/checks.py` (add new check function)
- `plugins/pd/hooks/lib/doctor/test_checks.py` (add 4 tests)

**DoD:**
- `.gitignore` contains literal lines `.claude/pd/workspace.json` and `.claude/pd/workspace.json.lock`.
- New `check_workspace_uuid_consistency(db) -> CheckResult` function defined.
- Returns `Severity.OK` if file exists, parses, matches a `workspaces` row.
- Returns `Severity.ERROR` if file missing AND `entities` has rows OR `project_id_legacy` mismatch.
- Returns `Severity.WARN` if file missing AND `entities` empty (fresh checkout).
- Tests `_ok`, `_missing_file_with_rows`, `_empty_db`, `_legacy_mismatch` all pass.

**Depends on:** 4.7, 2.14

**Estimated:** 15 minutes

**Tests:** AC-20, AC-21, AC-27.

---

## Phase 6 (F): Test Fixture Migration

### Task 6.1: FR-9 form-enumeration grep

**Why:** plan T-F1; design §3.5; WARNING 4 mitigation; SUGGESTION 10 (run grep at spec time).

**Files:** None for this task — grep run only.

**DoD:**
- Run `grep -nE "project_id\s*=\s*['\"]__unknown__['\"]|['\"]project_id['\"]\s*:\s*['\"]__unknown__['\"]|f['\"][^'\"]*__unknown__|register_entity\([^)]*['\"]__unknown__['\"]" plugins/pd/`.
- Output piped into Task 6.2's audit artifact.
- 4 form categories (kwarg, dict-key, f-string, positional) captured with file:line per match.
- Total match count ≥ 17.

**Depends on:** 1.0

**Estimated:** 5 minutes

---

### Task 6.2: Commit grep output as audit artifact

**Why:** plan T-F2; BLOCKER 6 (commit grep output as audit artifact).

**Files:**
- `agent_sandbox/2026-05-10/108-fixture-migration/forms-audit.txt` (new file)

**DoD:**
- Audit file contains: header (date + grep command), full output, 4-category summary table.
- Total match count documented.
- File committed.

**Depends on:** 6.1

**Estimated:** 5 minutes

---

### Task 6.3: Audit existing test fixtures for `workflow_phases` inserts that lack matching entity row; reorder fixture setup to register entity first

**Why:** plan T-F3; BLOCKER 4 (`wp_reject_orphaned_insert` cross-phase ordering hazard).

**Files:**
- `agent_sandbox/2026-05-10/108-fixture-migration/wp-orphan-audit.txt` (new file)
- Each test file flagged by audit (in-place edit reordering setup).

**DoD:**
- Run `grep -rnE 'INSERT INTO workflow_phases|set_workflow_phase\(' plugins/pd/hooks/lib/ --include='*.py'`.
- For each match: trace back ≥10 lines for matching `register_entity(` or fixture `INSERT INTO entities`. If absent, mark file:line as offender.
- For each offender: edit fixture to register the entity BEFORE the phase insert.
- Audit log committed; final list of offenders has 0 entries (every fixture has entity registration before phase insert).

**Depends on:** 6.2, 2.11

**Estimated:** 15 minutes

---

### Task 6.4: Apply kwarg-form sed pattern to 17 test files (FR-9)

**Why:** plan T-F4; FR-9; AC-17.

**Files:** All 17 test files in spec FR-9 §"Test files" table.

**DoD:**
- Kwarg form: `project_id='__unknown__'` and `project_id="__unknown__"` → `workspace_uuid=get_test_workspace_uuid()`.
- Each file gains import `from entity_registry.test_helpers import get_test_workspace_uuid` (only if not already present).
- Pytest gates each file commit: `pytest <file>` exits 0; phased rollout per design Decision 10.

**Depends on:** 6.2, 6.3, 1.4

**Estimated:** 15 minutes

---

### Task 6.5: Apply dict-key-form sed to same 17 test files

**Why:** plan T-F5; FR-9; AC-17.

**Files:** Same 17 files as Task 6.4.

**DoD:**
- Dict-key form: `'project_id': '__unknown__'` and `"project_id": "__unknown__"` → `'workspace_uuid': get_test_workspace_uuid()`.
- Pytest gate per file.

**Depends on:** 6.4

**Estimated:** 10 minutes

---

### Task 6.6: Manual rewrite f-string + positional cases

**Why:** plan T-F6; BLOCKER 6 (separate task for manual rewrite).

**Files:** Files flagged by Task 6.2 audit as containing f-string or positional `__unknown__` references.

**DoD:**
- Each f-string usage rewritten to use `get_test_workspace_uuid()` interpolation.
- Each positional `__unknown__` argument replaced.
- `grep -rn "__unknown__" plugins/pd/ --include='*.py'` returns hits ONLY in Migration 11 step 0 legacy mapping code path or `backfill.py:117,177`.
- Pytest gate per file.

**Depends on:** 6.5

**Estimated:** 10 minutes

**Tests:** AC-17.

---

### Task 6.7: Drop `parent_type_id` from `entity_registry/` package files (database.py, backfill.py, server_helpers.py, frontmatter_sync.py, frontmatter_inject.py)

**Why:** plan T-F7; FR-9 production list; AC-18.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py`
- `plugins/pd/hooks/lib/entity_registry/backfill.py`
- `plugins/pd/hooks/lib/entity_registry/server_helpers.py`
- `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py`
- `plugins/pd/hooks/lib/entity_registry/frontmatter_inject.py`

**DoD:**
- Each file's `parent_type_id` references removed.
- `register_entity` signature in `database.py` no longer accepts `parent_type_id`.
- `pytest plugins/pd/hooks/lib/entity_registry/` exits 0.

**Depends on:** 2.14

**Estimated:** 15 minutes

**Tests:** AC-18.

---

### Task 6.8: Drop `parent_type_id` from `workflow_engine/` package files (reconciliation.py, secretary_intelligence.py, task_promotion.py)

**Why:** plan T-F8; FR-9 production list; AC-18.

**Files:**
- `plugins/pd/hooks/lib/workflow_engine/reconciliation.py`
- `plugins/pd/hooks/lib/workflow_engine/secretary_intelligence.py`
- `plugins/pd/hooks/lib/workflow_engine/task_promotion.py`

**DoD:**
- Each file's `parent_type_id` references removed.
- `pytest plugins/pd/hooks/lib/workflow_engine/` exits 0.

**Depends on:** 6.7

**Estimated:** 10 minutes

**Tests:** AC-18.

---

### Task 6.9: Drop `parent_type_id` from `doctor/` package files (checks.py, fix_actions.py)

**Why:** plan T-F9; FR-9 production list; AC-18.

**Files:**
- `plugins/pd/hooks/lib/doctor/checks.py` (remove parent_type_id consistency checks ~lines 1565-1670)
- `plugins/pd/hooks/lib/doctor/fix_actions.py` (remove parent_type_id fixer ~line 36)
- `plugins/pd/hooks/lib/doctor/test_checks.py`, `test_fixer.py` (drop corresponding test cases)

**DoD:**
- 5 `parent_type_id` consistency checks removed.
- `parent_type_id` fixer removed.
- Test cases referencing dropped functionality removed.
- `grep -n 'parent_type_id' plugins/pd/hooks/lib/doctor/` returns 0 hits.
- `pytest plugins/pd/hooks/lib/doctor/` exits 0.

**Depends on:** 6.7

**Estimated:** 15 minutes

**Tests:** AC-18.

---

### Task 6.10: Drop `parent_type_id` from `mcp/entity_server.py`

**Why:** plan T-F10; FR-9 production list; AC-18.

**Files:**
- `plugins/pd/mcp/entity_server.py`

**DoD:**
- All `parent_type_id` references removed.
- `pytest plugins/pd/mcp/` exits 0.

**Depends on:** 6.7, 5.6

**Estimated:** 10 minutes

**Tests:** AC-18.

---

### Task 6.11: Drop `parent_type_id` from `ui/mermaid.py`; rewrite edge-label generator

**Why:** plan T-F11; FR-9 production list; AC-18.

**Files:**
- `plugins/pd/ui/mermaid.py`

**DoD:**
- `parent_type_id` references removed.
- `mermaid.py` generates edges from `parent_uuid` joined to `entities.type_id` for display labels only.
- `pytest plugins/pd/ui/` exits 0.
- `grep -rln 'parent_type_id' plugins/pd/ --include='*.py'` returns ONLY test files asserting the migration occurred (`test_database.py`, `test_backfill_parent_uuid.py`).

**Depends on:** 6.7

**Estimated:** 10 minutes

**Tests:** AC-18.

---

### Task 6.12: FR-18 markdown sweep — replace `project_id` in `plugins/pd/commands/*.md` and `plugins/pd/skills/*/SKILL.md`

**Why:** plan T-F12; task-reviewer BLOCKER 4 (FR-18 entirely unrepresented).

**Files:**
- `plugins/pd/commands/secretary.md`
- `plugins/pd/commands/create-project.md`
- `plugins/pd/commands/create-feature.md`
- `plugins/pd/skills/decomposing/SKILL.md`
- `plugins/pd/skills/brainstorming/SKILL.md`
- Any other `*.md` flagged by `grep -rn 'project_id' plugins/pd/commands/ plugins/pd/skills/ --include='*.md'`.

**DoD:**
- Run `grep -rn 'project_id' plugins/pd/commands/ plugins/pd/skills/ --include='*.md'` to enumerate hits.
- Replace each per FR-10 pattern (`project_id` → `workspace_uuid` in prose; preserve historical references when discussing migration audit trail).
- `grep -c 'project_id' plugins/pd/commands/ plugins/pd/skills/` returns 0 (or only matches in migration-history sections, documented).

**Depends on:** none (markdown-only, no code dependencies)

**Estimated:** 15 minutes

---

## Phase 7 (G): F6 Conditional Gate

### Task 7.1: Run F6 build-time gate; record outcome in implementation log

**Why:** plan T-G0; FR-15.

**Files:**
- `agent_sandbox/2026-05-10/108-f6-gate/gate-result.txt` (new file)
- `docs/features/108-workspace-identity-foundation/implementation-log.md` (new file or appended)

**DoD:**
- Run `plugins/pd/.venv/bin/python -c "import sys, uuid; assert sys.version_info >= (3, 14) and hasattr(uuid, 'uuid7'), 'F6 requires Python 3.14+ stdlib uuid7'"`.
- Capture exit code + Python version into `gate-result.txt`.
- Implementation log records: PASSES → proceed to Tasks 7.2–7.5; FAILS → proceed to Tasks 7.6–7.7.

**Depends on:** 1.0

**Estimated:** 5 minutes

---

### Task 7.2: Raise `pyproject.toml` `requires-python` floor + commit (PASSES path)

**Why:** plan T-G1; FR-15; BLOCKER 5.

**Files:**
- `plugins/pd/pyproject.toml`

**DoD:**
- (Run only if 7.1 exit == 0.)
- `requires-python = ">=3.14"`.
- Commit message references feature 108.

**Depends on:** 7.1 (PASSES)

**Estimated:** 5 minutes

---

### Task 7.3: Add `_new_uuid()` helper to `database.py` (PASSES path)

**Why:** plan T-G2; design §6.4; BLOCKER 5.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py`

**DoD:**
- (Run only if 7.1 exit == 0.)
- `def _new_uuid() -> str: return str(uuid_mod.uuid7())` defined; no fallback branch.

**Depends on:** 7.2

**Estimated:** 5 minutes

---

### Task 7.4: Substitute register sites + new tests (PASSES path)

**Why:** plan T-G3; FR-15 (Migration 1 unchanged); BLOCKER 5.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py`
- `plugins/pd/hooks/lib/entity_registry/test_database.py`

**DoD:**
- (Run only if 7.1 exit == 0.)
- Replace `uuid_mod.uuid4()` at `database.py:2145` (`register_entity`) and `database.py:3846` (`register_entities_batch`) with `_new_uuid()`.
- Leave `database.py:167` (Migration 1) UNCHANGED per spec FR-15.
- New tests `test_uuid7_when_available` (asserts `uuid.UUID(uuid_str).version == 7`) and `test_uuid_v4_v7_coexist` (mixed dataset queries cleanly via PK index).

**Depends on:** 7.3

**Estimated:** 10 minutes

**Tests:** AC-24, AC-25.

---

### Task 7.5: Capture EXPLAIN QUERY PLAN audit on mixed v4/v7 dataset and commit uuid-explain-plan.md plus CI matrix entry (PASSES path)

**Why:** plan T-G4 + T-G5; AC-33; RD-5 mitigation; BLOCKER 5.

**Files:**
- `docs/features/108-workspace-identity-foundation/uuid-explain-plan.md` (new)
- CI config (matrix entry: 3.12 must skip / 3.14 must pass)

**DoD:**
- (Run only if 7.1 exit == 0.)
- Generate ≥500 rows mixing v4 and v7 UUIDs; run EXPLAIN QUERY PLAN against both PK lookup and `idx_workspace_uuid` lookup; capture into `uuid-explain-plan.md`.
- CI matrix entry added: 3.12 must skip the F6 tests with explicit `pytest.skip` reason; 3.14 must pass.
- Implementation log updated: AC-24, AC-25, AC-33 marked LANDED.

**Depends on:** 7.4

**Estimated:** 15 minutes

**Tests:** AC-33.

---

### Task 7.6: Create backlog item with deferral rationale (FAILS path)

**Why:** plan T-G1'; BLOCKER 5; AC-33 (verified by backlog presence on FAILS path).

**Files:**
- `docs/backlog.md`
- `docs/features/108-workspace-identity-foundation/implementation-log.md`

**DoD:**
- (Run only if 7.1 exit != 0.)
- Run `/pd:add-to-backlog "Adopt uuid7 once Python 3.14+ is the venv default and pyproject.toml floor raised — feature 108 deferral"`.
- Implementation log records: F6 deferred; rationale = Python version gate failed; current floor `>=3.12`.

**Depends on:** 7.1 (FAILS)

**Estimated:** 5 minutes

**Tests:** AC-33.

---

### Task 7.7: Update spec FR-15 implementation log marking F6 deferred plus verify no _new_uuid references exist (FAILS path)

**Why:** plan T-G2'; BLOCKER 5 (negative grep on FAILS path).

**Files:**
- `docs/features/108-workspace-identity-foundation/implementation-log.md`
- `docs/features/108-workspace-identity-foundation/spec.md` (FR-15 implementation log subsection only)

**DoD:**
- (Run only if 7.1 exit != 0.)
- Spec FR-15 implementation log notes "F6 deferred (Python 3.14 gate failed)".
- `grep -rn '_new_uuid' plugins/pd/` returns 0 hits.
- Implementation log final entry records the negative-grep verification.

**Depends on:** 7.6

**Estimated:** 5 minutes

---

## Phase 8 (H): Validation + AC Sweep

### Task 8.1: Run pytest on `entity_registry/` package + capture log

**Why:** plan T-H1; AC-14 surface.

**Files:**
- `agent_sandbox/2026-05-10/108-validation/pytest-entity-registry.log` (new file)

**DoD:**
- Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/`.
- Exit 0; zero failures, zero errors.
- Output captured to log file.

**Depends on:** 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4, 6.5, 6.6, 6.7, 5.10, 4.8, 3.7

**Estimated:** 5 minutes

**Tests:** AC-14.

---

### Task 8.2: Run pytest on `doctor/` package + capture log

**Why:** plan T-H2; AC-14, AC-20, AC-21 surfaces.

**Files:**
- `agent_sandbox/2026-05-10/108-validation/pytest-doctor.log`

**DoD:**
- Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/`.
- Exit 0.
- Output captured.

**Depends on:** 6.9, 5.10, 5.4

**Estimated:** 5 minutes

**Tests:** AC-14, AC-20, AC-21.

---

### Task 8.3: Run pytest on `reconciliation_orchestrator/` package + capture log

**Why:** plan T-H3; AC-14, AC-30 surfaces.

**Files:**
- `agent_sandbox/2026-05-10/108-validation/pytest-recon-orch.log`

**DoD:**
- Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/reconciliation_orchestrator/`.
- Exit 0.

**Depends on:** 5.8, 5.4

**Estimated:** 5 minutes

**Tests:** AC-14, AC-30.

---

### Task 8.4: Run pytest on `workflow_engine/` package + capture log

**Why:** plan T-H4; AC-14 surface.

**Files:**
- `agent_sandbox/2026-05-10/108-validation/pytest-workflow-engine.log`

**DoD:**
- Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/`.
- Exit 0.

**Depends on:** 6.8, 5.4

**Estimated:** 5 minutes

**Tests:** AC-14.

---

### Task 8.5: Run pytest on `mcp/` package + capture log

**Why:** plan T-H5; AC-14, AC-31 surfaces.

**Files:**
- `agent_sandbox/2026-05-10/108-validation/pytest-mcp.log`

**DoD:**
- Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/`.
- Exit 0.

**Depends on:** 6.10, 5.7, 5.6, 5.4

**Estimated:** 5 minutes

**Tests:** AC-14, AC-31.

---

### Task 8.6: Run pytest on `ui/` package + capture log

**Why:** plan T-H6; AC-14 surface.

**Files:**
- `agent_sandbox/2026-05-10/108-validation/pytest-ui.log`

**DoD:**
- Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/ui/`.
- Exit 0.

**Depends on:** 6.11, 5.4

**Estimated:** 5 minutes

**Tests:** AC-14.

---

### Task 8.7: Run hook integration tests (`test-hooks.sh`) + bench-session-start

**Why:** plan T-H7; AC-14, AC-16, AC-29.

**Files:**
- `agent_sandbox/2026-05-10/108-validation/hooks.log`
- `agent_sandbox/2026-05-10/108-validation/bench.log`

**DoD:**
- `bash plugins/pd/hooks/tests/test-hooks.sh` exits 0.
- `bash plugins/pd/hooks/tests/bench-session-start.sh` exits 0; no broken-pipe; total time within prior NFR2 bounds.
- Output captured to log files.

**Depends on:** 5.9, 5.3, 5.2

**Estimated:** 5 minutes

**Tests:** AC-14, AC-16, AC-29.

---

### Task 8.8: Run `validate.sh`

**Why:** plan T-H8; AC-26.

**Files:**
- `agent_sandbox/2026-05-10/108-validation/validate.log`

**DoD:**
- `./validate.sh` exits 0; no plugin-portability violations.
- Output captured.

**Depends on:** 6.12, 6.10

**Estimated:** 5 minutes

**Tests:** AC-26.

---

### Task 8.9: Bash 3.2 verification + Migration 11 timing test

**Why:** plan T-H9; AC-32 (timing), AC-34 (bash 3.2 precondition).

**Files:**
- `plugins/pd/hooks/lib/entity_registry/test_database.py` (add `test_migration_11_runtime_under_2s`)
- `agent_sandbox/2026-05-10/108-validation/bash-version.log` (new file)

**DoD:**
- `bash --version` captured. If 3.2: `bash plugins/pd/hooks/tests/test-hooks.sh` exits 0. If 4+: log explicit skip message.
- New test creates synthetic ≥500-row v10 DB via `make_v10_db()`; wraps `_migrate(conn, 11)` in `time.perf_counter()`; warns >2s; fails >30s.
- Test passes.

**Depends on:** 5.3, 2.14, 2.0

**Estimated:** 10 minutes

**Tests:** AC-32, AC-34.

---

### Task 8.10: Sweep all 41 ACs into `.qa-gate.json`

**Why:** plan T-H10; spec §10.

**Files:**
- `docs/features/108-workspace-identity-foundation/.qa-gate.json` (new file)

**DoD:**
- New JSON file: `{"ac_results": [{"ac_id": "AC-1", "status": "pass|fail|deferred", "evidence": "..."}, ...]}`.
- All 41 spec ACs walked; each entry includes verification command output OR test name + result.
- Deferred ACs (e.g., AC-24, AC-25, AC-33 if F6 deferred) marked with rationale.
- Total entry count = 41.

**Depends on:** 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 7.5, 7.7

**Estimated:** 15 minutes

---

### Task 8.11: File residual issues + finalise implementation log

**Why:** plan T-H11; hygiene; spec §"residual" expectation.

**Files:**
- `docs/backlog.md` (append entries via `/pd:add-to-backlog`)
- `docs/features/108-workspace-identity-foundation/implementation-log.md` (append final summary)

**DoD:**
- For each AC marked `fail` or notable concern in `.qa-gate.json`, run `/pd:add-to-backlog` with feature 108 reference (AC number, failure mode, suggested follow-up).
- If no residuals: log `"No residual issues — all 41 ACs pass."`.
- Implementation log gets section "Implementation Summary" recording: task count completed, F6 outcome (landed/deferred), AC pass count, residuals filed.
- References `.qa-gate.json` for full evidence.
- Files staged for commit (do NOT commit yet — `/pd:wrap-up` handles that).

**Depends on:** 8.10

**Estimated:** 15 minutes

---
