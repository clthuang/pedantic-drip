# Plan: Feature 109 — Polymorphic Taxonomy and Event-Sourced State

- **Project:** P003-entity-system-redesign
- **Feature:** 109-polymorphic-taxonomy-and-event
- **Mode:** full
- **Status:** Draft
- **Created:** 2026-05-12
- **Spec:** `docs/features/109-polymorphic-taxonomy-and-event/spec.md` (revision 4)
- **Design:** `docs/features/109-polymorphic-taxonomy-and-event/design.md` (revision 4)

## 1. Implementation Strategy

This plan maps directly to the 16-step NFR-3 commit sequence in spec.md. Each step becomes a "Group" of atomic tasks. Groups execute strictly sequentially because most steps depend on prior schema state; within a Group, sub-tasks may run in parallel where noted.

**TDD discipline:** every Group that produces code or schema includes (a) a RED test commit that fails against pre-migration state, (b) a GREEN implementation commit that makes the test pass. Schema-only Groups bundle RED+GREEN into one commit when the schema-introspection test cannot be written without the schema (per codebase precedent in existing migrations — `test_database.py` follows this pattern).

**Migration scope:** all schema changes ship as a single migration function `_migration_12_polymorphic_taxonomy_and_events` in `database.py`. The 16 Groups are logical chunks WITHIN that migration plus the supporting Python-layer changes. The migration's sub-step order matches design §1.

## 2. Dependency Graph

```
Group 0 (prep) ──┬── Group 1 (collision audit)
                 └── Group 2 (type/kind/lifecycle_class columns + backfill)
                       │
                       ▼
                 Group 3 (composite CHECK via copy-rename)
                       │
                       ▼
                 Group 4 (idx_entities_type_kind)
                       │
                       ▼
                 Group 5 (FTS5 rebuild) ◄─── MUST precede Group 7 (column drop)
                       │
                       ▼
                 Group 6 (entity_type reader rewrite, per-file commits)
                       │
                       ▼
                 Group 7 (DROP entity_type column)
                       │
                       ▼
                 Group 8 (phase_events copy-rename: CHECK 4→7 + phase null + metadata)
                       │
                       ▼
                 Group 9 (append_phase_event helper) ◄─── extends existing insert_phase_event
                       │
                       ▼
                 Group 10 (Python-layer enforcement test + doctor check)
                       │
                       ▼
                 Group 11 (Drop both immutable triggers: 12 sites + runtime DROP)
                       │
                       ▼
                 Group 12 (promote_entity + PromotionConflictError)
                       │
                       ▼
                 Group 13 (Split register_entity / upsert_entity + EntityExistsError)
                       │
                       ▼
                 Group 14 (Re-route SQL line-3451 + line-5525)
                       │
                       ▼
                 Group 15 (Python-caller audit + per-caller routing)
                       │
                       ▼
                 Group 16 (Doctor health check integration)
                       │
                       ▼
                  FINISH (integration tests pass, FK check clean)
```

**Parallelizable opportunities:**
- Group 6 per-file commits (entity_type reader rewrite) can run in parallel via the `.pd-worktrees/` mechanism for ~6-10 affected files, **after** Group 5 (FTS5 rebuild) lands.
- Group 15 per-caller commits (Python-caller audit) for the ~17 production callers can also parallelize, **after** Group 13 (register/upsert split) lands.

All other Groups are strictly sequential due to schema dependencies.

## 3. Group-by-Group Plan

### Group 0: Pre-Migration Setup

**Goal:** Establish baseline state and create the migration scaffold.

**Tasks:** 0.1 (test_helpers `make_v12_db`), 0.2 (migration 12 stub registration).

**Dependencies:** none.

**DoD:** `MIGRATIONS[12]` registered; `make_v12_db()` exists but returns the same state as `make_v11_db()` (migration 12 is a stub that does nothing yet); `pytest plugins/pd/hooks/lib/entity_registry/test_database.py::test_v12_stub` passes.

### Group 1: Pre-Flight Collision Audit (AC-1.10)

**Goal:** Identify any pre-existing `(workspace_uuid, backlog:N + feature:N)` collisions that would later block promotion.

**Tasks:** 1.1 (write collision-audit RED test), 1.2 (implement audit query inside migration 12, logging only — non-blocking).

**Dependencies:** Group 0.

**DoD:** test asserts the audit query returns rows for a synthetic 2-row collision setup; migration logs the collision rows but does not abort.

### Group 2: Add type/kind/lifecycle_class columns + backfill (AC-1.1, AC-1.2, AC-1.9)

**Goal:** Schema-level addition of the 3 new columns, populated via backfill.

**Tasks:**
- 2.1 (write column-existence + NOT NULL RED test)
- 2.2 (write backfill-mapping RED test — assert (feature→work/feature/feature_flow), etc.)
- 2.3 (implement `ALTER TABLE entities ADD COLUMN type NOT NULL DEFAULT 'work'` + same for kind, lifecycle_class)
- 2.4 (implement backfill UPDATEs — 5 statements per spec FR-1 mapping)
- 2.5 (write defensive-abort test — assert migration raises on unmapped entity_type)

**Dependencies:** Group 1.

**DoD:** all 5 tests pass; live DB migration produces correct backfill counts; defensive abort works for synthetic invalid row.

### Group 3: Composite CHECK Constraint via copy-rename (AC-1.3)

**Goal:** Add `CHECK ((type='work' AND kind IN (feature, backlog)) OR (type='container' AND kind='project') OR ...)`.

**Tasks:**
- 3.1 (write CHECK-rejection RED test — 5 valid + 1 invalid pair)
- 3.2 (implement copy-rename block: capture `PRAGMA table_info(entities)` runtime, capture `SELECT sql FROM sqlite_master WHERE tbl_name='entities'` for trigger list, build entities_new with CHECK, INSERT-SELECT preserving all columns including entity_type)
- 3.3 (recreate triggers MINUS the 2 immutable triggers; recreate indexes)
- 3.4 (verify post-rebuild row count == pre-rebuild)

**Dependencies:** Group 2.

**DoD:** CHECK rejection test passes; copy-rename verified row-count parity; sqlite_master shows correct trigger list.

### Group 4: Add idx_entities_type_kind (AC-1.6)

**Goal:** Composite index for polymorphic-query workloads.

**Tasks:**
- 4.1 (write EXPLAIN QUERY PLAN RED test — assert `USING INDEX idx_entities_type_kind`)
- 4.2 (implement `CREATE INDEX idx_entities_type_kind ON entities(type, kind)`)

**Dependencies:** Group 3.

**DoD:** EXPLAIN test passes.

### Group 5: FTS5 Virtual Table Rebuild (AC-1.8)

**Goal:** Rebuild `entities_fts` with `kind` replacing `entity_type` in the search column list.

**Tasks:**
- 5.1 (write FTS5-search-by-kind RED test — `entities_fts MATCH 'kind:work'` returns correct rows)
- 5.2 (write FTS5-grep-predicate RED test — `grep -nE "INSERT INTO entities_fts.*entity_type"` returns 0)
- 5.3 (implement DROP TABLE entities_fts + CREATE VIRTUAL TABLE entities_fts USING fts5 with `kind` instead of `entity_type`)
- 5.4 (implement Python backfill loop reading entities + INSERT INTO entities_fts using `kind`)
- 5.5 (update 3 production sync INSERT sites at database.py:3469, 3877, 5545 to write `kind`)

**Dependencies:** Group 4. **Must precede Group 7 (column drop).**

**DoD:** all 2 RED tests pass; the 3 sync INSERT sites updated; AC-1.8 grep predicate returns 0.

### Group 6: entity_type Reader Rewrite (AC-1.4) — PARALLELIZABLE

**Goal:** Update all reader code paths to use `kind`/`type` instead of `entity_type`.

**Tasks:**
- 6.0 (DISCOVERY task: `grep -rln '\bentity_type\b' plugins/pd/hooks/lib/ plugins/pd/mcp/ | grep -v _migrate | grep -v test_` — captures file list)
- 6.1 through 6.N (one per-file commit, parallelizable via worktrees): rewrite each file's `entity_type` reads to use `kind` (or `type` where appropriate) and update associated tests.

**Dependencies:** Group 5. **Must precede Group 7.**

**DoD:** `grep -rn '\bentity_type\b' plugins/pd/hooks/lib/ plugins/pd/mcp/` returns 0 production references (allowed exceptions per AC-1.4); all updated files' tests pass.

### Group 7: DROP entity_type Column (AC-1.4 final step + AC-1.5)

**Goal:** Remove `entity_type` column; remove `FIVE_D_ENTITY_TYPES` frozenset.

**Tasks:**
- 7.1 (write DROP-COLUMN RED test — `PRAGMA table_info(entities)` does NOT include entity_type)
- 7.2 (write FIVE_D removal RED test — `grep -rn 'FIVE_D_ENTITY_TYPES' plugins/pd/` returns 0)
- 7.3 (verify SQLite version >= 3.35 — log capability)
- 7.4 (if SQLite >= 3.35: implement `ALTER TABLE entities DROP COLUMN entity_type`; else fall back to copy-rename)
- 7.5 (remove FIVE_D_ENTITY_TYPES from entity_engine.py + re-key the 2 call sites at lines 151, 251 on `type='container'`)

**Dependencies:** Group 5 (FTS5 must be rebuilt), Group 6 (all readers updated).

**DoD:** both RED tests pass; PRAGMA table_info no longer lists entity_type.

### Group 8: phase_events Copy-Rename (AC-2.4, AC-2.5)

**Goal:** Expand `event_type` CHECK from 4 → 7; relax `phase NOT NULL` to NULL-able; add `metadata` TEXT column.

**Tasks:**
- 8.1 (write CHECK-accepts-7-values RED test)
- 8.2 (write phase-NULL-able RED test)
- 8.3 (write metadata-column RED test)
- 8.4 (implement phase_events_new build via copy-rename: expanded CHECK, phase nullable, metadata TEXT)
- 8.5 (INSERT INTO phase_events_new SELECT ... FROM phase_events with NULL as metadata for legacy rows)
- 8.6 (DROP TABLE phase_events; ALTER TABLE phase_events_new RENAME TO phase_events)
- 8.7 (recreate indexes: idx_pe_lookup, idx_pe_project, idx_pe_timestamp, phase_events_backfill_dedup)

**Dependencies:** Group 7.

**DoD:** all 3 RED tests pass; 7-value CHECK acceptance verified; legacy rows preserved.

### Group 9: append_phase_event Helper (AC-2.1, AC-2.2, AC-2.7, AC-2.8)

**Goal:** Rename `insert_phase_event` to `append_phase_event`; extend signature with new event types + `workspace_uuid` kwarg; implement deterministic operation order.

**Tasks:**
- 9.1 (write per-event-type validation RED test — all 7 event_types, _VALID_PARAMS and _REQUIRED_PARAMS enforcement)
- 9.2 (write entity_created emission RED test — exactly 1 event row + NO redundant entities UPDATE)
- 9.3 (write entity_status_changed emission RED test — workspace-scoped UPDATE + 1 event row)
- 9.4 (write atomicity RED test — monkey-patch step 2 to raise; assert ROLLBACK + no event row visible)
- 9.5 (rename `insert_phase_event` → `append_phase_event` at database.py:4630 + update signature with workspace_uuid + metadata + timestamp kwargs + _VALID_PARAMS/_REQUIRED_PARAMS validation)
- 9.6 (update 4 production callers in plugins/pd/mcp/workflow_state_server.py:729,737,949,2030)
- 9.7 (update ~28 test callers in plugins/pd/mcp/test_workflow_state_server.py)

**Dependencies:** Group 8.

**DoD:** all 4 RED tests pass; rename + production caller updates land in one commit; tests in workflow_state_server pass post-rename.

### Group 10: Python-Layer Enforcement Test + Doctor Check (AC-2.1, NFR-2)

**Goal:** Static-grep CI test for "no direct UPDATE entities SET status" + doctor session-start audit.

**Tasks:**
- 10.1 (write static-grep test — `test_no_direct_status_updates` asserts grep returns 0 production matches)
- 10.2 (write doctor-check RED test — spike violating UPDATE into a fixture, run doctor, assert warning emitted)
- 10.3 (implement `check_status_write_path()` in plugins/pd/hooks/lib/doctor/ + register in doctor's check registry)

**Dependencies:** Group 9.

**DoD:** static-grep test passes against current codebase (already 0 violations); doctor-check test passes; new check registered in doctor registry.

### Group 11: Drop Both Immutable Triggers (AC-3.1)

**Goal:** Remove `enforce_immutable_entity_type` (6 source-code sites) + `enforce_immutable_type_id` (6 source-code sites) + runtime DROP TRIGGER.

**Tasks:**
- 11.1 (write trigger-source-zero RED test — `grep -n 'enforce_immutable_entity_type' database.py` returns 0)
- 11.2 (write trigger-source-zero RED test for `enforce_immutable_type_id`)
- 11.3 (write trigger-runtime-zero RED test — `SELECT name FROM sqlite_master WHERE name IN (...) ` returns 0 rows)
- 11.4 (remove 6 `CREATE TRIGGER ... enforce_immutable_entity_type` definitions at lines 136, 254, 655, 1101, 1988, 2414)
- 11.5 (remove 6 `CREATE TRIGGER ... enforce_immutable_type_id` definitions at lines 130, 249, 650, 1096, 1983, 2409)
- 11.6 (add `DROP TRIGGER IF EXISTS enforce_immutable_entity_type` AND `DROP TRIGGER IF EXISTS enforce_immutable_type_id` to migration 12 — idempotent guard against orphans from the Group 3 entities rebuild)

**Dependencies:** Group 10.

**DoD:** all 3 RED tests pass; both grep counts return 0.

### Group 12: promote_entity + PromotionConflictError (AC-3.2, AC-3.3, AC-3.4, AC-3.5, AC-3.6, AC-3.7)

**Goal:** Implement atomic backlog→feature promotion.

**Tasks:**
- 12.1 (write promotion-preserves-uuid RED test)
- 12.2 (write promotion-emits-event RED test)
- 12.3 (write FK-preservation RED test)
- 12.4 (write rollback-under-partial-failure RED test)
- 12.5 (write PromotionConflictError RED test — UNIQUE collision raises typed exception)
- 12.6 (implement `PromotionConflictError(ValueError)` class)
- 12.7 (implement `promote_entity(uuid, new_kind, new_lifecycle_class, *, project_id=None)` per design TD-6 pseudocode)
- 12.8 (verify type_id split rule for colons-in-suffix — `type_id.split(":", 1)`)

**Dependencies:** Group 11 (both triggers must be dropped first).

**DoD:** all 5 RED tests pass.

### Group 13: Split register_entity / upsert_entity (AC-4.1, AC-4.2, AC-4.3, AC-4.4)

**Goal:** Remove INSERT OR IGNORE from register_entity (raises); introduce upsert_entity.

**Tasks:**
- 13.1 (write EntityExistsError-raised RED test)
- 13.2 (write upsert insert-branch RED test)
- 13.3 (write upsert conflict + status-change RED test)
- 13.4 (write upsert conflict + no-status-change RED test — verify no UPDATE and no event)
- 13.5 (implement `EntityExistsError(ValueError)` class)
- 13.6 (modify `register_entity` at database.py:3443-3493 to remove `INSERT OR IGNORE`, raise on IntegrityError, REMOVE the on-duplicate parent_uuid fixup block at lines 3479-3493)
- 13.7 (implement `upsert_entity` per design TD-5 pseudocode — workspace-scoped lookup, three-branch event semantics, byte-identical signature to register_entity)

**Dependencies:** Group 12.

**DoD:** all 4 RED tests pass.

### Group 14: Re-route SQL line-3451 and line-5525 (AC-4.5, AC-4.6)

**Goal:** Replace the 2 production `INSERT OR IGNORE INTO entities` SQL sites with the new API contracts.

**Tasks:**
- 14.1 (write production-INSERT-OR-IGNORE-INTO-entities-returns-0 RED test)
- 14.2 (write register_entities_batch upsert RED test — idempotent re-run produces N events on first, 0 on second)
- 14.3 (replace line-3451 with plain INSERT — already done by Group 13.6, verify here)
- 14.4 (re-route line-5525 `register_entities_batch` to call `upsert_entity` per row)

**Dependencies:** Group 13.

**DoD:** both RED tests pass; AC-4.5 grep returns 0 production hits.

### Group 15: Python-Caller Audit (AC-4.7, AC-4.8) — PARALLELIZABLE

**Goal:** Visit each of 17 production register_entity callers; route to register (catch EntityExistsError) or upsert_entity per design audit table.

**Tasks:**
- 15.0 (DISCOVERY task: re-run grep to confirm 17 sites; commit the audit table to `.review-history.md` for traceability)
- 15.1 through 15.7 (one commit per file from the audit table — backfill.py [5 calls→upsert], server_helpers.py [2 calls→register], feature_lifecycle.py [2 calls→register], task_promotion.py [1 call→register], entity_status.py [2 calls→upsert], database.py [2 calls per Groups 13/14], entity_server.py [3 calls→register, surface MCP error per §3.5])

**Dependencies:** Group 14.

**DoD:** every call site has a preceding `# F12 audit:` comment; AC-4.8 1-to-1 coverage assertion passes.

### Group 16: Doctor Health Check Integration + Final Migration Wiring

**Goal:** Wire the doctor check into session start; final FK check inside migration 12.

**Tasks:**
- 16.1 (verify doctor check from Group 10 is registered in session-start hook flow)
- 16.2 (add in-transaction `PRAGMA foreign_key_check` to migration 12 just before COMMIT)
- 16.3 (add post-commit defensive FK check outside transaction)
- 16.4 (integration test: run migration 12 on `make_v11_db()`, assert post-state has all expected schema changes + FK clean + schema_version=12)
- 16.5 (down-migration test: run migration 12 down, assert runtime trigger restoration + schema reversion)

**Dependencies:** Group 15.

**DoD:** all integration tests pass; full migration 12 + down runs without FK violations.

## 4. Risk-Driven Sequencing Rationale

**Why this order matters:**
1. **Trigger drops (Group 11) must precede promote_entity (Group 12)** — promote_entity's UPDATE on `entity_type` (now `kind`) and `type_id` would be blocked by the existing triggers.
2. **FTS5 rebuild (Group 5) must precede column drop (Group 7)** — FTS5 reads `entity_type` during the rebuild backfill loop.
3. **Reader rewrite (Group 6) must precede column drop (Group 7)** — readers must use `kind` before the column disappears.
4. **register_entity split (Group 13) must precede SQL/Python audits (Groups 14, 15)** — auditing depends on the new API surface.
5. **Doctor check (Group 16.1) needs the migration's transaction commit step to be final** — check fires at session start after migration runs.

## 5. Test Plan Summary

Per spec §9, one test file per FR:
- `test_polymorphic_taxonomy.py` — Groups 2, 3, 4, 6, 7
- `test_event_sourced_state.py` — Groups 8, 9, 10
- `test_atomic_promotion.py` — Groups 11, 12
- `test_register_upsert_split.py` — Groups 13, 14, 15
- `test_migration_safety.py` — Groups 0, 1, 16 + cross-group integration

All tests use the `EntityDatabase(':memory:')` fixture pattern (existing precedent) and `make_v11_db()` / `make_v12_db()` for versioned baselines.

## 6. Parallel Execution Plan

For the 2 parallelizable Groups (6 and 15), use `.pd-worktrees/` to fan out per-file work. Sequential constraint: Group 6 must complete before Group 7; Group 15 must complete before Group 16.

Suggested concurrency: `max_concurrent_agents=5` (default). With ~6-10 reader files in Group 6 and ~7 caller files in Group 15, expect 2-3 wall-clock batches per Group.

## 7. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Migration aborts mid-transaction leaving partial state | Single `BEGIN IMMEDIATE` wraps all sub-steps; in-transaction FK check before COMMIT (Group 16.2). |
| FTS5 rebuild Python loop fails | Wrapped in same transaction as schema changes; ROLLBACK covers both. |
| `entity_type` reader rewrite misses a call site | AC-1.4 grep at completion catches; Group 6.0 DISCOVERY task pre-enumerates. |
| 17 Python callers expose unexpected raise behavior | Group 15 explicit audit + per-call comment; AC-4.7 catches integrity-error-handler sites. |
| SQLite version < 3.35 for DROP COLUMN | Group 7.3 version check; fall back to copy-rename. |
| `parent_uuid` fixup removal breaks callers | Group 13.6 + AC-4.7 audit; documented in design §3.1. |

## 8. Time Budget Estimate

- Groups 0-7 (schema migration + readers): ~6 hours
- Groups 8-11 (event sourcing + trigger drops): ~5 hours
- Groups 12-15 (promotion + register split + audits): ~6 hours
- Group 16 (doctor + integration): ~2 hours
- Reviewer iterations: ~3 hours

Total estimated: ~22 hours for implement phase. The plan and tasks files have already been reviewed for completeness in this create-plan phase.

## 9. Memory Influence

Memory hints applied:
- **"Phase merge requires exhaustive cross-codebase sweep"** — Groups 6 and 15 use explicit DISCOVERY tasks (6.0, 15.0) to enumerate every file before per-file commits.
- **"Integration tasks need mock pattern + algorithm + assertion shape"** — every task in tasks.md specifies these three elements explicitly.
- **"For 40+ Task Features Create-Tasks Is the Bottleneck"** — this feature has ~50-60 tasks; the plan groups them by commit step to keep create-plan review focused on Group-level coherence, not per-task fragility.
- **"create-plan Double Cap Predicts Three Simultaneous Blocker Categories"** — the plan front-loads explicit DISCOVERY tasks and trigger ordering to reduce blocker categories.
