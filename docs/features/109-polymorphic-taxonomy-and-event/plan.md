# Plan: Feature 109 — Polymorphic Taxonomy and Event-Sourced State

- **Project:** P003-entity-system-redesign
- **Feature:** 109-polymorphic-taxonomy-and-event
- **Mode:** full
- **Status:** Draft (revision 2 after plan-reviewer iteration 1)
- **Created:** 2026-05-12
- **Spec:** `docs/features/109-polymorphic-taxonomy-and-event/spec.md` (revision 4)
- **Design:** `docs/features/109-polymorphic-taxonomy-and-event/design.md` (revision 4)

## 1. Implementation Strategy

This plan maps directly to the 16-step NFR-3 commit sequence in spec.md. Each step becomes a "Group" of atomic tasks. Groups execute strictly sequentially because most steps depend on prior schema state; within a Group, sub-tasks may run in parallel where noted.

**TDD discipline:** every Group that produces code or schema includes (a) a RED test commit that fails against pre-migration state, (b) a GREEN implementation commit that makes the test pass. **Schema-introspection RED tests assert against BOTH versioned baselines** — `make_v11_db()` (assert old state) AND `make_v12_db()` (assert new state). The latter assertion is RED until the implementing Group lands. This pattern catches schema regressions in either direction.

**Bisect non-locality acknowledgement:** all 16 Groups modify the same `_migration_12_polymorphic_taxonomy_and_events` function body inside `database.py`. Commit-level bisect is preserved (one commit per Group), but within-migration regressions require inspecting each Group's diff range. Mitigation: each Group's RED test asserts a specific invariant; bisecting test failures pinpoints the responsible Group.

**Migration scope:** all schema changes ship as a single migration function `_migration_12_polymorphic_taxonomy_and_events` in `database.py`. The 16 Groups are logical chunks WITHIN that migration plus the supporting Python-layer changes. The migration's sub-step order matches design §1.

## 2. Dependency Graph

```
Group 0 (prep: migration stub + FK check inside transaction from day 1)
       │
       ▼
Group 0.5 (pure rename: insert_phase_event → append_phase_event, signature unchanged)
       │
       ▼
Group 1 (collision audit)
       │
       ▼
Group 2 (type/kind/lifecycle_class columns + backfill)
       │
       ▼
Group 3 (composite CHECK via copy-rename + DROP both immutable triggers + remove 12 source-code trigger definitions)  ◄── CONSOLIDATED trigger work
       │
       ▼
Group 4 (idx_entities_type_kind)
       │
       ▼
Group 5 (FTS5 rebuild) ◄─── MUST precede Group 7 (column drop)
       │
       ▼
Group 6 (entity_type reader rewrite, per-file commits — see Group 6.0 DISCOVERY for exact count)
       │
       ▼
Group 7 (DROP entity_type column)
       │
       ▼
Group 8 (phase_events copy-rename: CHECK 4→7 + phase null + metadata)
       │
       ▼
Group 9 (append_phase_event signature extension — workspace_uuid + metadata + timestamp + _VALID_PARAMS/_REQUIRED_PARAMS)
       │
       ▼
Group 10 (Python-layer enforcement test + doctor check — see Group 10.0 DISCOVERY for doctor registry)
       │
       ▼
Group 11 (REMOVED — work consolidated into Group 3)
       │
       ▼
Group 12 (promote_entity + PromotionConflictError)
       │
       ▼
Group 13 (Split register_entity / upsert_entity + EntityExistsError + pytest skip markers for affected callers — see Group 13.0 PRE-AUDIT)
       │
       ▼
Group 14 (Re-route line-5525 register_entities_batch only — line-3451 already done in Group 13)
       │
       ▼
Group 15 (Python-caller audit + per-caller routing + skill/command MD audit)
       │
       ▼
Group 16 (Doctor health check integration + final verify)
       │
       ▼
  FINISH (integration tests pass, FK check clean)
```

**Parallelizable opportunities:**
- Group 6 per-file commits (entity_type reader rewrite) can run in parallel via the `.pd-worktrees/` mechanism. **Verified empirical scope (2026-05-12):** `grep -rln '\bentity_type\b' plugins/pd/hooks/lib/ plugins/pd/mcp/ | grep -vE '(test_|_migrate)'` returns ~18-21 production files. With `max_concurrent_agents=5`, expect 4-5 wall-clock batches.
- Group 15 per-caller commits (Python-caller audit) for the ~17 production callers can also parallelize, **after** Group 13 (register/upsert split) lands. Add Group 15.8 sub-task for skill/command MD audit (separate from .py callers).

All other Groups are strictly sequential due to schema dependencies.

## 3. Group-by-Group Plan

### Group 0: Pre-Migration Setup

**Goal:** Establish baseline state and create the migration scaffold WITH in-transaction FK check from day 1.

**Tasks:** 0.1 (test_helpers `make_v12_db`), 0.2 (migration 12 stub registration WITH in-transaction `PRAGMA foreign_key_check` immediately before COMMIT — present from this commit forward; per design §3.3 reference impl; addresses Group 16.2 placement warning).

**Dependencies:** none.

**DoD:** `MIGRATIONS[12]` registered with FK check in body; `make_v12_db()` exists but returns the same state as `make_v11_db()` (migration 12 is a stub that does nothing yet other than the safety guards); `pytest plugins/pd/hooks/lib/entity_registry/test_database.py::test_v12_stub` passes.

### Group 0.5: Pure Rename `insert_phase_event` → `append_phase_event`

**Goal:** Rename the method with byte-identical signature so all subsequent Group RED tests can reference the new name without invalidating earlier-Group tests. **No signature change yet** — that lands in Group 9.

**Tasks:**
- 0.5.1 (write rename-only RED test — `grep -rn 'insert_phase_event(' plugins/pd/ | grep -v 'def insert_phase_event' | grep -v test_` returns 0)
- 0.5.2 (rename method at `database.py:4630`)
- 0.5.3 (mechanical rename at 4 production caller sites in `plugins/pd/mcp/workflow_state_server.py` lines 729, 737, 949, 2030 — verify line numbers at implement time)
- 0.5.4 (mechanical rename across ~46 test callers in 3 files: `plugins/pd/mcp/test_workflow_state_server.py` (~28), `plugins/pd/hooks/lib/entity_registry/test_phase_events.py` (~6), `plugins/pd/hooks/lib/entity_registry/test_phase_events_adversarial.py` (~12) — verified empirical count)

**Dependencies:** Group 0.

**DoD:** all RED tests pass; `grep` for old name returns 0 production matches; all renamed tests still pass.

**Rationale for splitting from Group 9:** memory-flagged TDD anti-pattern would result if the rename landed after Groups 2-8 because earlier-Group RED tests would either reference the soon-to-be-renamed old name (rewriting required at Group 9) or reference the new name pre-rename (RED tests permanently red until Group 9). Splitting the pure rename into Group 0.5 eliminates this anti-pattern.

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

### Group 3: Composite CHECK Constraint via copy-rename + CONSOLIDATED Trigger Removal (AC-1.3, AC-3.1)

**Goal:** Add `CHECK ((type='work' AND kind IN (feature, backlog)) OR (type='container' AND kind='project') OR ...)` AND remove both immutable triggers in one atomic Group (consolidating prior Group 11 work to preserve atomic-commit-per-step discipline).

**Tasks:**
- 3.1 (write CHECK-rejection RED test — 5 valid + 1 invalid pair)
- 3.2 (write source-code trigger-zero RED test for `enforce_immutable_entity_type` — grep returns 0)
- 3.3 (write source-code trigger-zero RED test for `enforce_immutable_type_id` — grep returns 0)
- 3.4 (write runtime-trigger-zero RED test — `SELECT name FROM sqlite_master WHERE name IN (immutable triggers)` returns 0 rows post-migration)
- 3.5 (remove 6 `CREATE TRIGGER ... enforce_immutable_entity_type` source-code definitions at lines 136, 254, 655, 1101, 1988, 2414)
- 3.6 (remove 6 `CREATE TRIGGER ... enforce_immutable_type_id` source-code definitions at lines 130, 249, 650, 1096, 1983, 2409)
- 3.7 (implement copy-rename block: capture `PRAGMA table_info(entities)` runtime, capture `SELECT sql FROM sqlite_master WHERE tbl_name='entities'` for trigger list, build entities_new with CHECK, INSERT-SELECT preserving all columns including entity_type)
- 3.8 (recreate triggers MINUS the 2 immutable triggers — the source removal in 3.5/3.6 means they aren't in the captured list to recreate; defensive `DROP TRIGGER IF EXISTS` statements added in migration body for runtime orphan-trigger safety)
- 3.9 (recreate indexes)
- 3.10 (verify post-rebuild row count == pre-rebuild)

**Dependencies:** Group 2.

**DoD:** CHECK rejection test passes; both source-grep tests return 0; runtime trigger query returns 0; copy-rename verified row-count parity; sqlite_master shows correct trigger list (4 non-immutable triggers preserved).

**Note:** Prior plan revision had Group 11 separately handling trigger removal. Per reviewer iteration 1, splitting trigger-drop across non-adjacent Groups violated atomic-commit discipline. Consolidated here. Group 11 is now REMOVED.

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

**Empirical scope (2026-05-12):** `grep -rln '\bentity_type\b' plugins/pd/hooks/lib/ plugins/pd/mcp/ | grep -vE '(test_|_migrate)'` returns ~18-21 production files. NOT "~6-10" as the iteration-1 plan revision stated — that was an undercount per reviewer feedback. Group 6.0 DISCOVERY pins the exact count at implement time.

**Tasks:**
- 6.0 (DISCOVERY task: run the empirical grep + commit the file list to `.review-history.md` for traceability)
- 6.1 through 6.N (one per-file commit, parallelizable via worktrees): rewrite each file's `entity_type` reads to use `kind` (or `type` where appropriate) and update associated tests. **Expected N ≈ 18-21.**

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
- 10.0 (DISCOVERY task: `ls plugins/pd/hooks/lib/doctor/ && grep -rn 'register_check\|CHECKS\b\|def check_' plugins/pd/hooks/lib/doctor/` — enumerate the doctor registry mechanism. Commit the registry location to `.review-history.md`. Per plan-reviewer iter-1 warning, registry location was deferred to implement-time without discovery; this task closes that gap.)
- 10.1 (write static-grep test — `test_no_direct_status_updates` asserts grep returns 0 production matches)
- 10.2 (write doctor-check RED test — spike violating UPDATE into a fixture, run doctor, assert warning emitted)
- 10.3 (implement `check_status_write_path()` per Group 10.0's discovered registry mechanism)

**Dependencies:** Group 9.

**DoD:** Group 10.0 commits the registry mechanism location; static-grep test passes against current codebase (already 0 violations); doctor-check test passes; new check registered in doctor registry.

### Group 11: REMOVED — Consolidated into Group 3

The trigger-removal work originally planned for Group 11 was split across two non-adjacent Groups (3 + 11), violating atomic-commit-per-step discipline per memory entry "Atomic commit discipline in schema migrations" (high). The plan-reviewer iteration 1 flagged this as a blocker.

**Resolution:** all trigger-removal work moved into Group 3 (the entities copy-rename), so the source-code definition removal AND runtime DROP TRIGGER guards land in the same commit that rebuilds the entities table without recreating the immutable triggers. See Group 3 tasks 3.5, 3.6, 3.8 for the consolidated work.

Group 11 is preserved as a placeholder for backward reference but ships no new commits.

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

**Goal:** Remove INSERT OR IGNORE from register_entity (raises); introduce upsert_entity. **Includes pytest skip-marker strategy to prevent broken-window CI** between this Group and Group 15 caller-migration completion.

**Broken-window strategy (memory: cascade failure between API change and caller migration):** Group 13 ships with `@pytest.mark.skip(reason="F12 caller-migration pending in feature 109 Group 15")` markers on every test that exercises the affected ~17 production callers + ~100 test callers expecting silent-no-op semantics. Each Group 15 sub-task (15.1-15.7) removes the corresponding skip marker as the caller is migrated. This keeps CI green at every commit boundary.

**Tasks:**
- 13.0 (PRE-AUDIT: enumerate affected test sites — `grep -rn 'register_entity(' plugins/pd/ | grep test_ > /tmp/affected_tests.txt`; cross-reference with the 7-file production caller list from design FR-4 audit table; commit the pre-audit output to `.review-history.md`)
- 13.1 (write EntityExistsError-raised RED test)
- 13.2 (write upsert insert-branch RED test)
- 13.3 (write upsert conflict + status-change RED test)
- 13.4 (write upsert conflict + no-status-change RED test — verify no UPDATE and no event)
- 13.5 (implement `EntityExistsError(ValueError)` class)
- 13.6 (modify `register_entity` at database.py:3443-3493 to remove `INSERT OR IGNORE`, raise on IntegrityError, REMOVE the on-duplicate parent_uuid fixup block at lines 3479-3493 — **includes the line-3451 SQL change**; Group 14 no longer duplicates this work)
- 13.7 (implement `upsert_entity` per design TD-5 pseudocode — workspace-scoped lookup, three-branch event semantics, byte-identical signature to register_entity)
- 13.8 (apply `@pytest.mark.skip(reason="F12 caller-migration pending in feature 109 Group 15")` to all affected tests identified in 13.0; CI must pass at this commit)

**Dependencies:** Group 12.

**DoD:** all 4 RED tests pass; CI green at commit boundary (skip markers protect the ~100+ pending-migration tests).

### Group 14: Re-route SQL line-5525 register_entities_batch (AC-4.5, AC-4.6)

**Goal:** Replace the remaining production `INSERT OR IGNORE INTO entities` SQL site at line 5525 with `upsert_entity` calls. The line-3451 site is handled by Group 13.6 (no separate work here).

**Tasks:**
- 14.1 (write production-INSERT-OR-IGNORE-INTO-entities-returns-0 RED test — note: at end of Group 13, this test is RED only against line 5525; Group 13.6 already eliminated line 3451)
- 14.2 (write register_entities_batch upsert RED test — idempotent re-run produces N events on first, 0 on second)
- 14.3 (re-route line-5525 `register_entities_batch` to call `upsert_entity` per row in the batch loop)

**Dependencies:** Group 13.

**DoD:** both RED tests pass; AC-4.5 grep returns 0 production hits.

### Group 15: Python-Caller Audit + Skill/Command MD Audit (AC-4.7, AC-4.8) — PARALLELIZABLE

**Goal:** Visit each of 17 production register_entity callers; route to register (catch EntityExistsError) or upsert_entity per design audit table. **Additionally audit skill/command MD callers** flagged by plan-reviewer iteration 1.

**Tasks:**
- 15.0 (DISCOVERY task: re-run grep to confirm 17 sites; commit the audit table to `.review-history.md` for traceability)
- 15.1 (backfill.py [5 calls→upsert] + remove relevant skip markers from Group 13.8)
- 15.2 (server_helpers.py [2 calls→register, EntityExistsError handled] + remove skip markers)
- 15.3 (feature_lifecycle.py [2 calls→register] + remove skip markers)
- 15.4 (task_promotion.py [1 call→register] + remove skip markers)
- 15.5 (entity_status.py [2 calls→upsert] + remove skip markers)
- 15.6 (entity_server.py [3 calls→register, surface MCP error per §3.5] + remove skip markers)
- 15.7 (write `test_f12_audit_one_to_one_coverage` — zip register/upsert call sites with `F12 audit` comments; assert 1-to-1)
- 15.8 (Skill/Command MD audit: `grep -rln 'register_entity' plugins/pd/skills/ plugins/pd/commands/` enumerates MD files that reference register_entity in prose. For each: either (a) update prose to add "on EntityExistsError, fall back to upsert_entity" instruction, OR (b) verify the MD prose routes through MCP entity_server which already translates the error per design §3.5. Pin the chosen routing per file in this task's commit. Expected files: SKILL.md files in brainstorming, decomposing; create-project.md, create-feature.md, add-to-backlog.md commands)

**Dependencies:** Group 14.

**DoD:** every .py call site has a preceding `# F12 audit:` comment; all skip markers from Group 13.8 are removed (CI passes without skips); skill/command MD audit committed with chosen routing per file; AC-4.8 1-to-1 coverage assertion passes.

### Group 16: Doctor Integration + Final Verification

**Goal:** Wire the doctor check into session start; verify the FK checks added in Group 0 are operational; integration + down-migration tests.

**Tasks:**
- 16.1 (verify doctor check from Group 10 is registered in session-start hook flow via the Group 10.0-discovered registry mechanism)
- 16.2 (VERIFY-ONLY task: confirm in-transaction `PRAGMA foreign_key_check` is present in migration 12 from Group 0.2; no new code. Per plan-reviewer iter-1 warning, this check is in migration 12 from day-1 commit, not "added" at Group 16.)
- 16.3 (VERIFY-ONLY task: confirm post-commit defensive FK check outside transaction is present from Group 0.2; no new code.)
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
| Migration aborts mid-transaction leaving partial state | Single `BEGIN IMMEDIATE` wraps all sub-steps; in-transaction FK check before COMMIT (present from Group 0.2). |
| FTS5 rebuild Python loop fails | Wrapped in same transaction as schema changes; ROLLBACK covers both. |
| `entity_type` reader rewrite misses a call site | AC-1.4 grep at completion catches; Group 6.0 DISCOVERY task pre-enumerates (~18-21 files). |
| 17 Python callers expose unexpected raise behavior | Group 15 explicit audit + per-call comment; AC-4.7 catches integrity-error-handler sites. |
| SQLite version < 3.35 for DROP COLUMN | Group 7.3 version check; fall back to copy-rename. |
| `parent_uuid` fixup removal breaks callers | Group 13.6 + AC-4.7 audit; documented in design §3.1. |
| **CI cascade failure between Group 13 (register_entity raises) and Group 15 (caller migration complete)** | Group 13.8 applies `@pytest.mark.skip(reason="F12 caller-migration pending")` to ~100+ affected tests; each Group 15 sub-task removes the corresponding skip marker. CI passes at every commit boundary. |
| **FTS5 rebuild memory cost grows with row count** | Live DB has ~700 rows today; if grows to 50K+ in future, batch INSERTs in chunks of 1000 rows within the single transaction. Group 5 test adds a 10K-row synthetic-DB scaling assertion. |
| Skill/command MD prose contracts reference old register_entity semantics | Group 15.8 audits MD files; either updates prose with EntityExistsError handling or verifies MCP routing translates the error. |

## 8. Complexity Estimate

Per plan-reviewer guidance, no wall-clock time estimates. Complexity per Group cluster:

- **Groups 0, 0.5, 1 (prep + rename + audit):** Simple — mechanical refactor and audit query.
- **Groups 2-4 (column additions + CHECK + index):** Medium — copy-rename pattern with new constraint surface.
- **Group 5 (FTS5 rebuild):** Medium — Python backfill loop + 6 source-code CREATE sites + 3 sync INSERT sites.
- **Group 6 (entity_type reader rewrite):** Complex — ~18-21 production files, parallel execution via worktrees.
- **Group 7 (DROP entity_type column):** Simple — single ALTER TABLE (or fallback copy-rename) + FIVE_D removal.
- **Group 8 (phase_events copy-rename):** Medium — schema change + legacy row preservation.
- **Group 9 (append_phase_event signature extension):** Medium — validation logic + workspace_uuid plumbing + operation order discipline.
- **Group 10 (Python-layer enforcement + doctor):** Simple — static-grep test + doctor registration.
- **Group 12 (promote_entity):** Medium — atomic UPDATE + event + UNIQUE-safety pre-flight.
- **Group 13 (register/upsert split + skip markers):** Complex — API change with cascade impact mitigation.
- **Group 14 (re-route line-5525):** Simple — single batch-helper rewrite.
- **Group 15 (Python-caller audit + MD audit):** Complex — 17+ callers across 7 .py files + 5+ MD files, parallel.
- **Group 16 (doctor integration + verify):** Simple — verification tasks.

Overall feature complexity: **Complex**. The plan and tasks files have been reviewed for completeness in this create-plan phase.

## 9. Memory Influence

Memory hints applied:
- **"Phase merge requires exhaustive cross-codebase sweep"** — Groups 6 and 15 use explicit DISCOVERY tasks (6.0, 15.0) to enumerate every file before per-file commits.
- **"Integration tasks need mock pattern + algorithm + assertion shape"** — every task in tasks.md specifies these three elements explicitly.
- **"For 40+ Task Features Create-Tasks Is the Bottleneck"** — this feature has ~50-60 tasks; the plan groups them by commit step to keep create-plan review focused on Group-level coherence, not per-task fragility.
- **"create-plan Double Cap Predicts Three Simultaneous Blocker Categories"** — the plan front-loads explicit DISCOVERY tasks and trigger ordering to reduce blocker categories.
