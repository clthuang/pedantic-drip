# Tasks: Feature 109 — Polymorphic Taxonomy and Event-Sourced State

- **Project:** P003-entity-system-redesign
- **Feature:** 109-polymorphic-taxonomy-and-event
- **Mode:** full
- **Plan:** `docs/features/109-polymorphic-taxonomy-and-event/plan.md`
- **Spec:** `docs/features/109-polymorphic-taxonomy-and-event/spec.md`
- **Design:** `docs/features/109-polymorphic-taxonomy-and-event/design.md`
- **Format note:** tasks use the `### Task N.M:` heading convention per the implementing skill's parser regex `/^(#{3,4})\s+Task\s+(\d+(?:\.\d+)*):?\s*(.+)$/`. Each task includes (1) mock/algorithm pattern, (2) assertion shape, (3) DoD per memory heuristic "Integration tasks need mock pattern + algorithm + assertion shape".

**Revision 2 changes (plan-reviewer iteration 1 addressed):**
- Group 0.2 (migration stub) now includes in-transaction `PRAGMA foreign_key_check` from day 1 (was previously deferred to Group 16.2). Group 16.2/16.3 reframed as verify-only.
- **NEW Group 0.5** — pure rename `insert_phase_event` → `append_phase_event` with byte-identical signature, placed BEFORE Groups 2-8 so subsequent RED tests reference the new name without invalidating earlier tests.
- **Group 3 consolidated** to include trigger removal (source-code + runtime DROP) alongside the entities copy-rename — previously split between Groups 3 and 11.
- **Group 11 REMOVED** — work moved into Group 3 per atomic-commit-per-step discipline.
- **Group 14 narrowed** to line-5525 only — line-3451 work is now solely in Group 13.6 (no redundant verify task).
- **Group 13 expanded** with `@pytest.mark.skip` strategy to keep CI green during the Group 13 → Group 15 caller-migration window.
- **Group 15.8 added** — skill/command MD audit (skill MD prose may reference register_entity).
- **Group 6 / Group 9.7 / Group 15** call-site counts updated to empirical values (~18-21 reader files; ~46 test-caller sites in 3 files for insert_phase_event rename; 17 .py caller sites + ~5 MD caller files).
- **All schema-introspection RED tests now run against BOTH `make_v11_db()` AND `make_v12_db()`** to assert the introspection invariant in either direction (RED on the post-migration baseline until the implementing task lands).

---

## Group 0: Pre-Migration Setup

### Task 0.0: DISCOVERY — pre-existing FK violation check on live DB

- **File:** none (output captured to `.review-history.md`)
- **Action:** Run `sqlite3 ~/.claude/pd/entities/entities.db 'PRAGMA foreign_key_check'` against the current live DB. (Plan-reviewer iter-2 flagged risk: the PRD evidence notes 4 stale workflow_phases rows + 6 duplicate projects + 120 unsynced backlog rows — some may be FK violations that would block Group 0.2's stub migration at session start.)
- **Decision tree:**
  - If output is empty: proceed to Task 0.1.
  - If non-empty: (a) clean up violations via a prerequisite commit (pre-Group-0 stabilization); OR (b) document violations as expected pre-state and adjust the in-transaction FK check in Group 0.2 to log-warn rather than abort.
- **DoD:** live DB FK-check output committed to .review-history.md; recovery path chosen and applied.
- **Dependencies:** none (must run first).

### Task 0.1: Add `make_v12_db()` helper to test_helpers.py

- **File:** `plugins/pd/hooks/lib/entity_registry/test_helpers.py`
- **Action:** Add function `make_v12_db(path=None)` that calls `make_v11_db(path)` then `MIGRATIONS[12](conn)` (Migration 12 will be a stub at this point — it just stamps schema_version=12).
- **Pattern:** mirror `make_v11_db` at lines ~55-109.
- **Assertion shape:** `conn = make_v12_db(); assert conn.execute("SELECT value FROM _metadata WHERE key='schema_version'").fetchone()[0] == '12'`.
- **DoD:** `pytest plugins/pd/hooks/lib/entity_registry/test_helpers.py -k make_v12_db` passes (test added in this task).
- **Dependencies:** none.

### Task 0.2: Register migration 12 stub in MIGRATIONS dict WITH in-transaction FK check

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Action:** Add stub function `_migration_12_polymorphic_taxonomy_and_events(conn)` at appropriate location (after `_migration_11_workspace_identity`). Stub body: assert schema_version >= 11, PRAGMA foreign_keys OFF outside try, BEGIN IMMEDIATE inside try, **in-transaction `PRAGMA foreign_key_check` immediately before stamping schema_version=12**, stamp schema_version=12, COMMIT, finally PRAGMA foreign_keys = ON, post-commit defensive FK check. Register in `MIGRATIONS` dict at line 2620: `12: _migration_12_polymorphic_taxonomy_and_events`.
- **Pattern:** mirror `_migration_11_workspace_identity` skeleton in full, including the FK-check disciplines that Groups 16.2/16.3 would otherwise add later. The in-transaction FK check is critical safety from commit 0.2 onwards.
- **Assertion shape:** `db = EntityDatabase(':memory:'); assert db._conn.execute("SELECT value FROM _metadata WHERE key='schema_version'").fetchone()[0] == '12'` (full EntityDatabase init runs all migrations to current).
- **DoD:** existing tests in `test_database.py` continue to pass (stub does nothing harmful); `make_v12_db()` returns connection at version 12; FK check is verifiably present in migration body via source inspection.
- **Dependencies:** Task 0.1.

---

## Group 0.5: Pure Rename `insert_phase_event` → `append_phase_event`

**Rationale (per plan-reviewer iter-1 blocker):** the rename is mechanically separable from the signature extension. Moving the pure rename here (before any RED tests that touch event emission) avoids invalidating Groups 2-8 tests at Group 9 time.

### Task 0.5.1: Write rename-only RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_event_sourced_state.py`
- **Action:** Write `test_no_production_insert_phase_event_callers` — subprocess grep `insert_phase_event(` across `plugins/pd/` excluding `def insert_phase_event` and `test_` paths; assert 0 matches.
- **Algorithm:** subprocess + filter.
- **Assertion shape:** `assert len(production_matches) == 0`.
- **DoD:** RED — currently 4 production matches in workflow_state_server.py.
- **Dependencies:** Group 0.

### Task 0.5.2: Rename method definition at database.py:4630

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Action:** Rename `def insert_phase_event(...)` → `def append_phase_event(...)` at line 4630 (verify exact line at implement time). Signature UNCHANGED at this step — only the symbol name.
- **Algorithm:** single rename.
- **Assertion shape:** `grep -n 'def append_phase_event' database.py` returns 1; `grep -n 'def insert_phase_event' database.py` returns 0.
- **DoD:** definition renamed; tests at 0.5.4 must still pass after the caller renames.
- **Dependencies:** Task 0.5.1.

### Task 0.5.3: Rename 4 production callers in workflow_state_server.py

- **File:** `plugins/pd/mcp/workflow_state_server.py`
- **Action:** At lines 729, 737, 949, 2030 (verify at implement time), rename `insert_phase_event(` → `append_phase_event(`. No parameter changes.
- **Algorithm:** mechanical rename.
- **Assertion shape:** `grep -n 'insert_phase_event(' workflow_state_server.py` returns 0.
- **DoD:** 4 sites updated.
- **Dependencies:** Task 0.5.2.

### Task 0.5.4: Rename ~50 test callers across 3 test files

- **File:** `plugins/pd/mcp/test_workflow_state_server.py` (28 sites), `plugins/pd/hooks/lib/entity_registry/test_phase_events.py` (11 sites), `plugins/pd/hooks/lib/entity_registry/test_phase_events_adversarial.py` (11 sites). **Empirical count corrected per plan-reviewer iter-2 verification** (iter-1 listed ~6 for test_phase_events.py; actual is 11). Total: 50 test callers.
- **Action:** Mechanical rename in all 3 files.
- **Algorithm:** sed-style rename in 3 files.
- **Assertion shape:** Task 0.5.1 test passes; all 3 test files' existing tests still pass.
- **DoD:** all sites renamed; test suite green; Task 0.5.1 passes.
- **Dependencies:** Task 0.5.3.

---

## Group 1: Pre-Flight Collision Audit

### Task 1.1: Write collision-audit RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_migration_safety.py` (new file)
- **Action:** Write `test_collision_audit_detects_backlog_feature_collisions` — build v11 DB, insert 2 entities with same workspace_uuid and matching numeric suffixes (`backlog:42`, `feature:42`), run audit query, assert returns the collision.
- **Mock pattern:** use `make_v11_db(tmp_path / 'test.db')`, direct sqlite3 inserts via test helper.
- **Algorithm:** the audit query is `SELECT workspace_uuid, SUBSTR(type_id, INSTR(type_id, ':') + 1) AS suffix FROM entities WHERE type_id LIKE 'backlog:%' INTERSECT SELECT workspace_uuid, SUBSTR(type_id, INSTR(type_id, ':') + 1) FROM entities WHERE type_id LIKE 'feature:%'`.
- **Assertion shape:** `assert len(rows) == 1 and rows[0]['workspace_uuid'] == ws and rows[0]['suffix'] == '42'`.
- **DoD:** RED — test fails because migration 12 stub doesn't run the audit yet.
- **Dependencies:** Group 0.

### Task 1.2: Implement collision-audit logging in migration 12

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside `_migration_12_polymorphic_taxonomy_and_events`)
- **Action:** After BEGIN IMMEDIATE + pre-FK-check, before any schema change: run the audit query (from Task 1.1), log each result to stderr (`print(f"INFO: Migration 12 pre-flight collision: workspace={ws}, suffix={suffix}", file=sys.stderr)`). Non-blocking.
- **Algorithm:** execute the INTERSECT query; iterate `fetchall()`; print one line per row.
- **Assertion shape:** Task 1.1 test now passes; capsys captures stderr output.
- **DoD:** Task 1.1 test passes; migration runs without aborting on collisions.
- **Dependencies:** Task 1.1.

---

## Group 2: type/kind/lifecycle_class Columns + Backfill

### Task 2.1: Write column-existence RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_polymorphic_taxonomy.py` (new file)
- **Action:** Write `test_entities_has_type_kind_lifecycle_class_columns` — `db = EntityDatabase(':memory:')`; assert `PRAGMA table_info(entities)` lists all 3 new columns with `notnull=1`.
- **Mock pattern:** direct sqlite3 introspection.
- **Assertion shape:** `cols = {row[1]: row for row in db._conn.execute('PRAGMA table_info(entities)').fetchall()}; assert 'type' in cols and cols['type'][3] == 1  # notnull`.
- **DoD:** RED — fails because columns don't exist yet.
- **Dependencies:** Group 1.

### Task 2.2: Write backfill-mapping RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_polymorphic_taxonomy.py`
- **Action:** Write `test_backfill_maps_entity_type_correctly` — for each of 4 production entity_types (feature, backlog, brainstorm, project), register an entity at v11 schema, run migration 12, assert (type, kind, lifecycle_class) match the FR-1 mapping table.
- **Mock pattern:** `db = make_v11_db(); db.register_entity('feature', '001-test', 'Test Feature')` then upgrade to v12 via re-init.
- **Algorithm:** assert dict equality per row.
- **Assertion shape:** `for entity_type, (t, k, lc) in expected.items(): assert db.get_entity_by_uuid(uuid_map[entity_type])['kind'] == k`.
- **DoD:** RED — fails until Task 2.4 implements backfill.
- **Dependencies:** Task 2.1.

### Task 2.3: Implement column-add ALTER TABLE statements

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside migration 12)
- **Action:** After Group 1 audit, before backfill: `conn.execute("ALTER TABLE entities ADD COLUMN type TEXT NOT NULL DEFAULT 'work'")`, same for `kind` (DEFAULT 'feature'), `lifecycle_class` (DEFAULT 'feature_flow'). These defaults are placeholders fixed by Task 2.4.
- **Algorithm:** 3 sequential ALTER TABLE statements.
- **Assertion shape:** Task 2.1 test now passes.
- **DoD:** Task 2.1 passes.
- **Dependencies:** Task 2.2.

### Task 2.4: Implement backfill UPDATEs

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside migration 12, after Task 2.3)
- **Action:** Execute 5 UPDATE statements per spec FR-1 mapping table:
  - `UPDATE entities SET type='work', kind='feature', lifecycle_class='feature_flow' WHERE entity_type='feature'`
  - Same for backlog → work/backlog/work_flow
  - brainstorm → brainstorm/brainstorm/brainstorm_flow
  - project → container/project/container_flow
  - workspace → workspace/workspace/none (no-op on most DBs where workspace is in workspaces table)
- **Algorithm:** sequential UPDATEs; final SELECT COUNT(*) WHERE type IS NULL must return 0.
- **Assertion shape:** Task 2.2 test now passes; `assert db._conn.execute("SELECT COUNT(*) FROM entities WHERE type IS NULL OR kind IS NULL OR lifecycle_class IS NULL").fetchone()[0] == 0`.
- **DoD:** Task 2.2 test passes.
- **Dependencies:** Task 2.3.

### Task 2.5: Implement defensive abort test + impl

- **File:** `plugins/pd/hooks/lib/entity_registry/test_polymorphic_taxonomy.py` + `database.py`
- **Action:** Write `test_backfill_aborts_on_unmapped_entity_type` — insert row with `entity_type='unknown'`, run migration, assert it raises. Implementation: after Task 2.4 UPDATEs, run `SELECT COUNT(*) FROM entities WHERE type IS NULL`; if > 0, raise `RuntimeError("Migration 12: unmapped entity_type rows: {count}")`.
- **Mock pattern:** insert synthetic invalid row pre-migration.
- **Assertion shape:** `with pytest.raises(RuntimeError, match='unmapped entity_type'): _migration_12_...(db._conn)`.
- **DoD:** test passes; migration aborts cleanly on unmapped types.
- **Dependencies:** Task 2.4.

---

## Group 3: Composite CHECK Constraint via copy-rename + Consolidated Trigger Removal

**Note (plan-reviewer iter-1 blocker resolution):** Trigger removal work originally split between Groups 3 and 11 is consolidated here. Group 11 is REMOVED. Add tasks 3.5-3.8 below for the trigger-removal sub-work.

### Task 3.1: Write CHECK-rejection RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_polymorphic_taxonomy.py`
- **Action:** Write `test_check_constraint_rejects_invalid_pairs` — try inserting 5 valid pairs (workspace/workspace, brainstorm/brainstorm, container/project, work/feature, work/backlog) — all succeed. Then try `(type='work', kind='project')` — assert `sqlite3.IntegrityError` with "CHECK constraint failed".
- **Mock pattern:** `db.register_entity(...)` or direct INSERT bypassing API.
- **Assertion shape:** `with pytest.raises(sqlite3.IntegrityError, match='CHECK constraint failed'): db._conn.execute("INSERT INTO entities (...) VALUES (..., 'work', 'project', ...)")`.
- **DoD:** RED — CHECK doesn't exist yet.
- **Dependencies:** Group 2.

### Task 3.2: Implement copy-rename block

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside migration 12, after Group 2)
- **Action:** Capture column list via `PRAGMA table_info(entities)`; capture triggers via `SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='entities'`; build `entities_new` with the composite CHECK constraint; `INSERT INTO entities_new SELECT ...` preserving all columns; `DROP TABLE entities`; `ALTER TABLE entities_new RENAME TO entities`.
- **Algorithm:** follow `_expand_workflow_phase_check` (migration 5, database.py:464-577) as template. The composite CHECK clause: `CHECK ((type='workspace' AND kind='workspace') OR (type='brainstorm' AND kind='brainstorm') OR (type='container' AND kind='project') OR (type='work' AND kind IN ('feature','backlog')))`.
- **Assertion shape:** Task 3.1 test passes; pre/post row count parity verified.
- **DoD:** Task 3.1 passes.
- **Dependencies:** Task 3.1.

### Task 3.3: Recreate triggers minus the 2 immutable

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside migration 12, after Task 3.2)
- **Action:** From the trigger list captured in Task 3.2, recreate each trigger on the rebuilt `entities` table EXCEPT `enforce_immutable_entity_type` and `enforce_immutable_type_id` (those are dropped by F11+F3).
- **Algorithm:** loop over captured triggers; skip the 2 immutable ones by name; CREATE TRIGGER ... from the captured `sql` text (verbatim).
- **Assertion shape:** post-rebuild `SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='entities'` returns the expected list minus 2.
- **DoD:** trigger count matches expectation; the 4 non-immutable triggers (`enforce_immutable_uuid`, `enforce_immutable_created_at`, `enforce_no_self_parent*`) are present.
- **Dependencies:** Task 3.2.

### Task 3.4: Recreate indexes + verify row count

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside migration 12)
- **Action:** Recreate `idx_entity_type` (or its v12 equivalent), `idx_status`, `idx_parent_uuid`. Verify `SELECT COUNT(*) FROM entities` post-rebuild equals pre-rebuild count.
- **Algorithm:** capture pre-count, INSERT-SELECT (Task 3.2), post-count; assertEqual.
- **Assertion shape:** `assert pre_count == post_count`.
- **DoD:** row count parity confirmed.
- **Dependencies:** Task 3.3.

### Task 3.5: Write source-grep RED tests for both immutable triggers

- **File:** `plugins/pd/hooks/lib/entity_registry/test_atomic_promotion.py` (new file at this point)
- **Action:** Write `test_enforce_immutable_entity_type_source_removed` AND `test_enforce_immutable_type_id_source_removed` — each greps the respective trigger name in database.py and asserts 0 production matches.
- **Assertion shape:** subprocess grep + count == 0.
- **DoD:** RED — current code has 6 occurrences of each.
- **Dependencies:** Task 3.4.

### Task 3.6: Write runtime-trigger-zero RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_atomic_promotion.py`
- **Action:** Write `test_immutable_triggers_dropped_at_runtime` against `make_v12_db()` — `SELECT name FROM sqlite_master WHERE type='trigger' AND name IN ('enforce_immutable_entity_type', 'enforce_immutable_type_id')` returns empty.
- **Assertion shape:** empty result.
- **DoD:** RED — triggers still exist in v11→v12 transition state.
- **Dependencies:** Task 3.5.

### Task 3.7: Remove 6 enforce_immutable_entity_type source definitions

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Action:** Remove `CREATE TRIGGER ... enforce_immutable_entity_type ...` blocks at lines 136, 254, 655, 1101, 1988, 2414 (verify at implement time).
- **DoD:** Task 3.5 first assertion passes.
- **Dependencies:** Task 3.6.

### Task 3.8: Remove 6 enforce_immutable_type_id source definitions + add DROP TRIGGER guards

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Action:** Remove `CREATE TRIGGER ... enforce_immutable_type_id ...` blocks at lines 130, 249, 650, 1096, 1983, 2409 (verify at implement time). Inside migration 12 body (after the entities copy-rename block from Task 3.2), add `conn.execute("DROP TRIGGER IF EXISTS enforce_immutable_entity_type")` and `conn.execute("DROP TRIGGER IF EXISTS enforce_immutable_type_id")` as defensive guards against any orphan triggers.
- **DoD:** Task 3.5 second assertion + Task 3.6 pass; both triggers absent from runtime + source.
- **Dependencies:** Task 3.7.

---

## Group 4: idx_entities_type_kind

### Task 4.1: Write EXPLAIN QUERY PLAN RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_polymorphic_taxonomy.py`
- **Action:** Write `test_polymorphic_query_uses_index` — `db._conn.execute("EXPLAIN QUERY PLAN SELECT * FROM entities WHERE type = 'work' AND kind = 'feature'")` returns a row containing `USING INDEX idx_entities_type_kind`.
- **Mock pattern:** direct sqlite3 EXPLAIN.
- **Assertion shape:** `plan = ' '.join(row[3] for row in db._conn.execute('EXPLAIN QUERY PLAN ...').fetchall()); assert 'idx_entities_type_kind' in plan`.
- **DoD:** RED — index doesn't exist.
- **Dependencies:** Group 3.

### Task 4.2: Create idx_entities_type_kind

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside migration 12)
- **Action:** `conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_type_kind ON entities(type, kind)")`.
- **Assertion shape:** Task 4.1 test passes.
- **DoD:** Task 4.1 passes.
- **Dependencies:** Task 4.1.

---

## Group 5: FTS5 Virtual Table Rebuild

### Task 5.1: Write FTS5-search-by-kind RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_polymorphic_taxonomy.py`
- **Action:** Write `test_fts5_search_kind_matches_legacy_entity_type` — register 2 features and 1 backlog at v11 schema, upgrade to v12, assert `entities_fts MATCH 'kind:work'` returns 3 rows (all 3 are work-type post-mapping).
- **Mock pattern:** `db.register_entity('feature', '001-a', 'Foo'); db.register_entity('feature', '002-b', 'Bar'); db.register_entity('backlog', '00001', 'Baz')`.
- **Assertion shape:** `rows = db._conn.execute("SELECT entity_id FROM entities_fts WHERE entities_fts MATCH 'kind:work'").fetchall(); assert len(rows) == 3`.
- **DoD:** RED — FTS5 still keys on `entity_type:feature`, not `kind:work`.
- **Dependencies:** Group 4.

### Task 5.2: Write FTS5-grep-predicate RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_polymorphic_taxonomy.py`
- **Action:** Write `test_no_production_fts5_insert_references_entity_type` — runs `subprocess.run(['grep', '-nE', 'INSERT INTO entities_fts.*entity_type', 'plugins/pd/hooks/lib/entity_registry/database.py'])`, filters out `_migrate_*` and test paths, asserts 0 production matches.
- **Algorithm:** subprocess + line filter.
- **Assertion shape:** `production_matches = [l for l in grep_output.splitlines() if '_migrate_' not in l]; assert production_matches == []`.
- **DoD:** RED — production matches exist at database.py:3469, 3877, 5545.
- **Dependencies:** Task 5.1.

### Task 5.3: Implement FTS5 DROP + CREATE with kind

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside migration 12, after Group 4)
- **Action:** `DROP TABLE IF EXISTS entities_fts; CREATE VIRTUAL TABLE entities_fts USING fts5(name, entity_id, kind, status, metadata_text, content='entities', content_rowid='rowid')` (matches the pattern at migration 4 / database.py:421 but with `kind` instead of `entity_type`).
- **Algorithm:** template from `_create_fts_index`.
- **Assertion shape:** post-migration `SELECT sql FROM sqlite_master WHERE name='entities_fts'` contains `'kind'` and NOT `'entity_type'`.
- **DoD:** structural assertion passes; Task 5.1 still RED until Task 5.4 backfills FTS5 contents.
- **Dependencies:** Task 5.2.

### Task 5.4: Implement FTS5 backfill Python loop

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside migration 12, after Task 5.3)
- **Action:** Python loop reading each row from `entities`, INSERTing into `entities_fts` with `kind` instead of `entity_type` (e.g., `INSERT INTO entities_fts (rowid, name, entity_id, kind, status, metadata_text) VALUES (?, ?, ?, ?, ?, ?)`).
- **Algorithm:** `for row in conn.execute('SELECT rowid, name, entity_id, kind, status, metadata FROM entities'): conn.execute('INSERT INTO entities_fts ...', (row[0], row[1], row[2], row[3], row[4], flatten_metadata(row[5])))`.
- **Assertion shape:** Task 5.1 test passes.
- **DoD:** Task 5.1 passes.
- **Dependencies:** Task 5.3.

### Task 5.5: Update 3 production FTS5 sync sites

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Action:** Update INSERT INTO entities_fts statements at lines 3469 (register_entity FTS sync), 3877 (update-path resync), 5545 (register_entities_batch bulk) to write `kind` instead of `entity_type`. **Verify exact lines at implement time via grep — they may shift if earlier tasks reformatted code.**
- **Algorithm:** mechanical edit; change column name in each INSERT.
- **Assertion shape:** Task 5.2 test passes (grep predicate returns 0 production matches).
- **DoD:** Task 5.2 passes; 3 sites updated.
- **Dependencies:** Task 5.4.

---

## Group 6: entity_type Reader Rewrite (PARALLELIZABLE)

### Task 6.0: DISCOVERY — enumerate entity_type readers

- **File:** none (output captured to `.review-history.md` or temp file)
- **Action:** Run `grep -rln '\bentity_type\b' plugins/pd/hooks/lib/ plugins/pd/mcp/ | grep -v _migrate | grep -v test_`. Capture the file list to a working note.
- **Algorithm:** subprocess grep.
- **Assertion shape:** captured file count is documented; each file becomes a sub-task 6.1..6.N.
- **DoD:** file list captured; sub-tasks 6.1..6.N created with file paths.
- **Dependencies:** Group 5.

### Task 6.1: Rewrite entity_type readers — file 1 (placeholder, filled at implement time)

- **File:** TBD (one of the files from Task 6.0)
- **Action:** In each occurrence of `entity_type` (excluding test fixtures and migration scaffolding), rewrite to use `kind` (or `type` where the broader discriminator is needed). Update associated tests in the same file.
- **Algorithm:** mechanical search-and-replace, with semantic review per occurrence.
- **Assertion shape:** post-file-edit grep returns 0 for `\bentity_type\b` in this file (allowed exceptions: migration scaffolding).
- **DoD:** file-level grep returns 0; file's own tests pass.
- **Dependencies:** Task 6.0.

### Task 6.2 through 6.N: Same pattern as 6.1, one per file

(Plan-phase scope: file count and exact names captured by Task 6.0 at implement time. Expected ~6-10 files based on design TD-8.)

---

## Group 7: DROP entity_type Column

### Task 7.1: Write column-dropped RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_polymorphic_taxonomy.py`
- **Action:** Write `test_entity_type_column_dropped` — `cols = {row[1] for row in db._conn.execute('PRAGMA table_info(entities)').fetchall()}; assert 'entity_type' not in cols`.
- **Assertion shape:** column set membership check.
- **DoD:** RED — column still present.
- **Dependencies:** Group 6.

### Task 7.2: Write FIVE_D removal RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_polymorphic_taxonomy.py`
- **Action:** Write `test_five_d_entity_types_removed` — `subprocess` grep for `FIVE_D_ENTITY_TYPES` in `plugins/pd/hooks/lib/`, assert 0 matches.
- **Assertion shape:** grep count == 0.
- **DoD:** RED — frozenset still exists.
- **Dependencies:** Task 7.1.

### Task 7.3: Implement SQLite version check + DROP COLUMN

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside migration 12)
- **Action:** Check `sqlite3.sqlite_version_info >= (3, 35, 0)`. If yes: `conn.execute("ALTER TABLE entities DROP COLUMN entity_type")`. If no: fall back to a second copy-rename block dropping the column. Log which path is taken.
- **Algorithm:** conditional version check + branched DDL.
- **Assertion shape:** Task 7.1 test passes regardless of branch.
- **DoD:** Task 7.1 passes.
- **Dependencies:** Task 7.2.

### Task 7.4: Remove FIVE_D_ENTITY_TYPES + re-key 2 call sites

- **File:** `plugins/pd/hooks/lib/workflow_engine/entity_engine.py`
- **Action:** Remove the `FIVE_D_ENTITY_TYPES = frozenset({...})` definition at line 35-37. Re-key the 2 call sites at lines 151 and 251 to test `entities.type == 'container'` instead of `entity_type in FIVE_D_ENTITY_TYPES`.
- **Algorithm:** delete + 2 logic edits.
- **Assertion shape:** Task 7.2 grep passes; both call sites' surrounding tests still pass.
- **DoD:** Task 7.2 passes.
- **Dependencies:** Task 7.3.

---

## Group 8: phase_events Copy-Rename

### Task 8.1: Write CHECK-accepts-7-values RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_event_sourced_state.py` (new file)
- **Action:** Write `test_phase_events_check_accepts_7_event_types` — for each of 7 values (4 legacy + 3 new), attempt INSERT; all succeed. Then INSERT with `event_type='invalid'`; assert IntegrityError.
- **Mock pattern:** direct sqlite3 INSERT with workspace-scoped INSERT bypassing helper (allowed in test — see permitted exceptions in AC-2.1).
- **Assertion shape:** 7 successful inserts + 1 IntegrityError.
- **DoD:** RED — CHECK still restricts to 4 values.
- **Dependencies:** Group 7.

### Task 8.2: Write phase-NULL-able RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_event_sourced_state.py`
- **Action:** Write `test_phase_column_accepts_null_for_entity_events` — INSERT with `event_type='entity_created', phase=NULL`; assert succeeds.
- **Mock pattern:** direct INSERT.
- **DoD:** RED — phase is still NOT NULL.
- **Dependencies:** Task 8.1.

### Task 8.3: Write metadata-column RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_event_sourced_state.py`
- **Action:** Write `test_phase_events_has_metadata_column` — `PRAGMA table_info(phase_events)` lists `metadata` as TEXT NULL.
- **DoD:** RED — metadata column absent.
- **Dependencies:** Task 8.2.

### Task 8.4: Implement phase_events copy-rename

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside migration 12)
- **Action:** Build `phase_events_new` with: `event_type CHECK IN ('started','completed','skipped','backward','entity_created','entity_status_changed','entity_promoted')`, `phase TEXT` (NULL-able), `metadata TEXT` (NULL-able). INSERT-SELECT preserving existing rows with NULL metadata. DROP old; RENAME new.
- **Algorithm:** template from migration 5 / Group 3.
- **Assertion shape:** Tasks 8.1, 8.2, 8.3 pass; existing phase_events rows preserved.
- **DoD:** all 3 tests pass.
- **Dependencies:** Task 8.3.

### Task 8.5: Recreate phase_events indexes

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (inside migration 12)
- **Action:** Recreate `idx_pe_lookup`, `idx_pe_project`, `idx_pe_timestamp`, partial-UNIQUE `phase_events_backfill_dedup` (from database.py:1492-1518 originals).
- **Algorithm:** capture pre-migration index list via `SELECT sql FROM sqlite_master WHERE tbl_name='phase_events' AND type='index'`; recreate each on the new table.
- **Assertion shape:** `SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='phase_events'` returns the expected list.
- **DoD:** all phase_events indexes restored.
- **Dependencies:** Task 8.4.

---

## Group 9: append_phase_event Helper

### Task 9.1: Write _VALID_PARAMS / _REQUIRED_PARAMS RED tests

- **File:** `plugins/pd/hooks/lib/entity_registry/test_event_sourced_state.py`
- **Action:** Parameterized test covering all 7 event_types: (a) passing required params succeeds; (b) passing irrelevant discriminator param raises ValueError; (c) base params (project_id/source/timestamp) accepted for all types.
- **Mock pattern:** `pytest.parametrize` over 7 event_types × 3 sub-cases.
- **Assertion shape:** `with pytest.raises(ValueError, match='not valid for event_type'): db.append_phase_event('feature:001', 'entity_created', iterations=1)`.
- **DoD:** RED — helper doesn't exist yet (still named insert_phase_event with old shape).
- **Dependencies:** Group 8.

### Task 9.2: Write entity_created emission RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_event_sourced_state.py`
- **Action:** Write `test_entity_created_emits_one_event_no_redundant_update` — call `db.append_phase_event('feature:001', 'entity_created', workspace_uuid=ws, metadata={...})`; assert exactly 1 phase_events row; assert `entities.status` AND `entities.updated_at` unchanged from the value set by INSERT.
- **Mock pattern:** call helper directly.
- **Assertion shape:** before/after `updated_at` comparison.
- **DoD:** RED — helper doesn't have the skip rule for entity_created yet.
- **Dependencies:** Task 9.1.

### Task 9.3: Write entity_status_changed emission RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_event_sourced_state.py`
- **Action:** Write `test_entity_status_changed_emits_event_and_updates_status` — call helper with `event_type='entity_status_changed', workspace_uuid=ws, metadata={'old_status': 'planned', 'new_status': 'active'}`; assert 1 phase_events row; assert `entities.status` == 'active' AND `entities.updated_at` advanced.
- **Mock pattern:** call helper.
- **Assertion shape:** post-call SELECT verifies status + updated_at.
- **DoD:** RED.
- **Dependencies:** Task 9.2.

### Task 9.4: Write atomicity RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_event_sourced_state.py`
- **Action:** Write `test_append_phase_event_atomicity` — monkey-patch the step-2 UPDATE inside append_phase_event to raise; assert transaction rolls back; assert no phase_events row visible AND no entities.status change.
- **Mock pattern:** `mocker.patch.object(db, '_step2_update', side_effect=RuntimeError)` or equivalent.
- **Assertion shape:** post-call count assertions.
- **DoD:** RED.
- **Dependencies:** Task 9.3.

### Task 9.5: EXTEND append_phase_event signature (rename already happened in Group 0.5)

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (at `append_phase_event` definition — renamed in Group 0.5)
- **Action:** **The pure rename was already done in Group 0.5.** This task ADDS the new signature components:
  - Add `workspace_uuid: str | None = None` kwarg (required for entity_* event types).
  - Add `metadata: dict | None = None` kwarg.
  - Add `timestamp: str | None = None` kwarg (auto-generates _iso_now() when None).
  - Add `_VALID_PARAMS` and `_REQUIRED_PARAMS` module-level dicts (with base-param coverage note per design §3.1).
  - Implement validation logic (raise ValueError on shape mismatch).
  - Implement operation order per design §3.1:
    1. Validate per-event-type params.
    2. INSERT INTO phase_events (...) RETURNING id.
    3. If event_type in {entity_status_changed, entity_promoted}: UPDATE entities SET status, updated_at WHERE workspace_uuid = ? AND type_id = ?.
    4. If event_type='entity_created': skip step 3 (INSERT already wrote status).
    5. If event_type in {started, completed, skipped, backward}: UPDATE workflow_phases SET workflow_phase, updated_at WHERE type_id = ?.
- **Signature BEFORE/AFTER (per plan-reviewer iter-1 warning):**
  - **BEFORE (post-0.5 rename, pre-9.5 extension):** `def append_phase_event(self, type_id, event_type, *, project_id=None, phase, iterations=None, reviewer_notes=None, backward_reason=None, backward_target=None, source='live', timestamp=None)` — byte-identical to current insert_phase_event.
  - **AFTER (post-9.5):** same positional order, adds `workspace_uuid: str | None = None` and `metadata: dict | None = None` as keyword-only after the existing kwargs. **No positional reorder** — existing positional callers in workflow_state_server.py:729/737/949/2030 continue to work.
- **Algorithm:** see design TD-2 + §3.1.
- **Assertion shape:** Tasks 9.1, 9.2, 9.3, 9.4 all pass.
- **DoD:** all 4 RED tests pass; signature BEFORE/AFTER recorded in code docstring.
- **Dependencies:** Task 9.4.

### Task 9.6: Update production callers in workflow_state_server.py to pass workspace_uuid

- **File:** `plugins/pd/mcp/workflow_state_server.py`
- **Action:** At the 4 production sites (renamed to append_phase_event in Group 0.5), add `workspace_uuid=...` kwarg (callers already have workspace context via the MCP request).
- **Algorithm:** mechanical kwarg add.
- **Assertion shape:** existing workflow_state_server tests pass under new validation rules.
- **DoD:** all 4 sites pass workspace_uuid; tests pass.
- **Dependencies:** Task 9.5.

### Task 9.7: Update test callers to pass workspace_uuid for entity_* events

- **File:** ~46 test sites across `plugins/pd/mcp/test_workflow_state_server.py`, `plugins/pd/hooks/lib/entity_registry/test_phase_events.py`, `plugins/pd/hooks/lib/entity_registry/test_phase_events_adversarial.py`. **Per plan-reviewer iter-1 verified empirical count.**
- **Action:** For tests that exercise entity_* event types, add `workspace_uuid=...` kwarg. Tests exercising workflow event types (started/completed/skipped/backward) don't need the new kwarg (it's optional for those).
- **Algorithm:** identify entity_* event_type calls + add kwarg.
- **Assertion shape:** all 3 test files pass.
- **DoD:** tests pass; entity_* events get workspace_uuid; workflow events still work without it.
- **Dependencies:** Task 9.6.

---

## Group 10: Python-Layer Enforcement Test + Doctor Check

### Task 10.0: DISCOVERY — enumerate doctor check registry mechanism

- **File:** none (output captured to `.review-history.md`)
- **Action:** Run `ls plugins/pd/hooks/lib/doctor/ && grep -rn 'register_check\|CHECKS\b\|def check_' plugins/pd/hooks/lib/doctor/` to discover the doctor's check registry mechanism (whether checks are registered via decorator, list, dict, or convention).
- **Algorithm:** filesystem listing + grep.
- **Assertion shape:** registry mechanism documented (e.g., "checks are functions named `check_*` discovered via reflection in `__init__.py`").
- **DoD:** registry mechanism pinned; Task 10.3's implementation uses the discovered pattern.
- **Dependencies:** Group 9.

### Task 10.1: Implement static-grep enforcement test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_event_sourced_state.py`
- **Action:** Write `test_no_direct_status_updates` — subprocess grep for `UPDATE entities SET status` in plugins/pd/hooks/lib/ and plugins/pd/mcp/, filter out append_phase_event body and _migrate_* functions and test_ files, assert 0 production matches.
- **Algorithm:** subprocess + line filter.
- **Assertion shape:** filtered count == 0.
- **DoD:** test passes against current codebase.
- **Dependencies:** Group 9.

### Task 10.2: Write doctor-check RED test

- **File:** `plugins/pd/hooks/lib/doctor/test_check_status_write_path.py` (new file)
- **Action:** Write `test_doctor_detects_status_violations` — copy `database.py` to a temp dir, spike a violating `UPDATE entities SET status='active' WHERE type_id='x'` into a non-migration function, run `check_status_write_path()`, assert non-empty violation list.
- **Mock pattern:** file copy + injection.
- **Assertion shape:** `violations = check_status_write_path(); assert len(violations) > 0`.
- **DoD:** RED — check function doesn't exist.
- **Dependencies:** Task 10.1.

### Task 10.3: Implement check_status_write_path()

- **File:** `plugins/pd/hooks/lib/doctor/check_status_write_path.py` (new file)
- **Action:** Implement function per design §3.6. Register in doctor's check registry (verify exact registry location at implement time — likely `plugins/pd/hooks/lib/doctor/__init__.py`).
- **Algorithm:** subprocess grep + filter (matches design §3.6 reference impl).
- **Assertion shape:** Task 10.2 test passes; running doctor on clean codebase returns 0 violations.
- **DoD:** Task 10.2 passes.
- **Dependencies:** Task 10.2.

---

## Group 11: REMOVED — Consolidated into Group 3

Per plan-reviewer iteration 1 blocker, the trigger-removal work originally planned for Group 11 was split across two non-adjacent commits (Groups 3 + 11), violating atomic-commit discipline. All trigger-removal tasks are now in Group 3 (tasks 3.5-3.8).

This section is preserved for traceability. **No new tasks ship in Group 11.**

---

## Group 12: promote_entity + PromotionConflictError

### Task 12.1: Write promotion-preserves-uuid RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_atomic_promotion.py`
- **Action:** Write `test_promotion_preserves_uuid` — register backlog, capture uuid, call promote, assert uuid unchanged AND (kind, lifecycle_class, type_id) updated.
- **DoD:** RED — promote_entity doesn't exist.
- **Dependencies:** Group 11.

### Task 12.2: Write promotion-emits-event RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_atomic_promotion.py`
- **Action:** Write `test_promotion_emits_entity_promoted_event` — after promote, assert `SELECT COUNT(*) FROM phase_events WHERE event_type='entity_promoted' AND type_id=?` == 1 with the post-promotion type_id.
- **DoD:** RED.
- **Dependencies:** Task 12.1.

### Task 12.3: Write FK-preservation RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_atomic_promotion.py`
- **Action:** Write `test_promotion_preserves_dependencies` — create backlog + feature; add dependency edge; promote backlog; assert dependency count unchanged.
- **DoD:** RED.
- **Dependencies:** Task 12.2.

### Task 12.4: Write rollback RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_atomic_promotion.py`
- **Action:** Write `test_promotion_rollback_on_partial_failure` — monkey-patch append_phase_event to raise mid-promote; assert (kind, lifecycle_class, type_id) intact post-failure.
- **DoD:** RED.
- **Dependencies:** Task 12.3.

### Task 12.5: Write PromotionConflictError RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_atomic_promotion.py`
- **Action:** Write `test_promotion_conflict_raises` — pre-create `feature:42`, create `backlog:42`, attempt promote backlog → feature; assert PromotionConflictError raised; assert backlog row unchanged.
- **DoD:** RED.
- **Dependencies:** Task 12.4.

### Task 12.6: Implement PromotionConflictError

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Action:** Add `class PromotionConflictError(ValueError):` near other module-level definitions. Constructor takes (workspace_uuid, old_type_id, new_type_id) and exposes them as attributes.
- **DoD:** import works; instantiation works.
- **Dependencies:** Task 12.5.

### Task 12.7: Implement promote_entity method

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Action:** Implement `promote_entity(uuid, new_kind, new_lifecycle_class, *, project_id=None) -> dict` per design TD-6 pseudocode. Uses `get_entity_by_uuid` for the pre-flight read; uses `type_id.split(":", 1)` for prefix rewrite; emits `entity_promoted` event via `append_phase_event(new_type_id, ..., workspace_uuid=...)`.
- **Algorithm:** see design TD-6.
- **Assertion shape:** all 5 RED tests pass.
- **DoD:** Tasks 12.1-12.5 pass.
- **Dependencies:** Task 12.6.

---

## Group 13: Split register_entity / upsert_entity

### Task 13.1: Write EntityExistsError-raised RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_register_upsert_split.py` (new file)
- **Action:** Write `test_register_entity_raises_on_conflict` — register entity A; second register with same (workspace_uuid, type_id) raises EntityExistsError.
- **DoD:** RED — current behavior is silent ignore.
- **Dependencies:** Group 12.

### Task 13.2: Write upsert insert-branch RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_register_upsert_split.py`
- **Action:** Write `test_upsert_entity_inserts_when_new` — call upsert_entity for new (workspace_uuid, type_id); assert entity created + 1 entity_created event.
- **DoD:** RED — upsert_entity doesn't exist.
- **Dependencies:** Task 13.1.

### Task 13.3: Write upsert status-change RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_register_upsert_split.py`
- **Action:** Write `test_upsert_entity_emits_event_on_status_change` — upsert existing entity with different status; assert entity_status_changed event emitted.
- **DoD:** RED.
- **Dependencies:** Task 13.2.

### Task 13.4: Write upsert no-change RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_register_upsert_split.py`
- **Action:** Write `test_upsert_entity_noop_when_no_change` — upsert existing entity with same status; assert no UPDATE, no event, returns existing uuid.
- **DoD:** RED.
- **Dependencies:** Task 13.3.

### Task 13.5: Implement EntityExistsError

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Action:** Add `class EntityExistsError(ValueError):` constructor takes (workspace_uuid, type_id) exposes both as attributes.
- **DoD:** import works.
- **Dependencies:** Task 13.4.

### Task 13.0: PRE-AUDIT — enumerate affected test sites for skip-marker strategy (two-pass)

- **File:** none (output captured to `.review-history.md`)
- **Action:** Two-pass audit:
  - **Pass 1 (direct callers):** Run `grep -rn 'register_entity(' plugins/pd/ | grep test_` to capture explicit register_entity caller tests.
  - **Pass 2 (indirect catch):** Apply Task 13.6 + 13.7 implementations locally (in a scratch branch or staged commit), then run `pytest plugins/pd/` and collect EVERY failing test. The union of pass 1 + pass 2 is the full skip-marker target list. (Plan-reviewer iter-2 flagged that grep alone misses tests calling helpers that internally use register_entity.)
- **Algorithm:** grep + experimental pytest run + union.
- **Assertion shape:** captured union list documented.
- **DoD:** complete affected-test list committed to .review-history.md; both passes covered.
- **Dependencies:** Task 13.4.

### Task 13.6: Modify register_entity (remove INSERT OR IGNORE + parent_uuid fixup)

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` at line 3443+
- **Action:** Remove `OR IGNORE` from line 3451. Wrap INSERT in try/except sqlite3.IntegrityError → raise EntityExistsError. Remove the on-duplicate parent_uuid fixup block at lines 3479-3493 (becomes unreachable). Add the `entity_created` phase_events emission after successful INSERT + FTS5 sync. **This task includes the actual SQL line-3451 modification — Group 14 no longer duplicates this.**
- **Algorithm:** edit existing method per design §3.1.
- **Assertion shape:** Task 13.1 passes.
- **DoD:** Task 13.1 passes.
- **Dependencies:** Task 13.5.

### Task 13.7: Implement upsert_entity method

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Action:** Implement `upsert_entity(kind, entity_id, name, *, workspace_uuid, status, ...)` per design TD-5 pseudocode. Uses workspace-scoped direct SELECT for conflict-branch read; three-branch event semantics.
- **Algorithm:** see design TD-5.
- **Assertion shape:** Tasks 13.2, 13.3, 13.4 pass.
- **DoD:** all 4 RED tests pass.
- **Dependencies:** Task 13.6.

### Task 13.8: Apply pytest skip markers to affected tests (broken-window mitigation)

- **File:** affected test files identified in Task 13.0
- **Action:** For each test that exercises a register_entity caller from the 7-file production list, add `@pytest.mark.skip(reason="F12 caller-migration pending in feature 109 Group 15.{N}")` where N identifies the corresponding Group 15 sub-task that will remove the skip. CI must pass at this commit boundary.
- **Algorithm:** decorator add per affected test method.
- **Assertion shape:** `pytest plugins/pd/` exit code 0 (skipped tests do not fail).
- **DoD:** CI green at end of Group 13 commit; skip-marker count matches the affected-test list from Task 13.0.
- **Dependencies:** Task 13.7.

---

## Group 14: Re-route SQL line-5525 register_entities_batch only

**Note (plan-reviewer iter-1 blocker resolution):** Line-3451 work is solely in Task 13.6 — Group 14 no longer duplicates it.

### Task 14.1: Write INSERT-OR-IGNORE-INTO-entities-zero RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_register_upsert_split.py`
- **Action:** Write `test_no_production_insert_or_ignore_into_entities` — subprocess grep, assert 0 production matches.
- **DoD:** RED only against line-5525 at Group 14 start (line-3451 was already removed by Task 13.6). After Task 14.3, this test passes.
- **Dependencies:** Group 13.

### Task 14.2: Write register_entities_batch upsert RED test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_register_upsert_split.py`
- **Action:** Write `test_register_entities_batch_idempotent` — run once, assert N entity_created events; run again same input, assert 0 new events + same row count.
- **DoD:** RED — batch path still uses INSERT OR IGNORE.
- **Dependencies:** Task 14.1.

### Task 14.3: Re-route line 5525 to upsert_entity

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` at line 5525
- **Action:** Replace `INSERT OR IGNORE INTO entities ...` with a loop calling `self.upsert_entity(...)` per row in the batch.
- **Algorithm:** loop conversion.
- **Assertion shape:** Tasks 14.1 + 14.2 pass.
- **DoD:** both tests pass; AC-4.5 grep returns 0.
- **Dependencies:** Task 14.2.

---

## Group 15: Python-Caller Audit (PARALLELIZABLE)

### Task 15.0: DISCOVERY — confirm 17 caller sites

- **File:** none (output captured to working note)
- **Action:** Run `grep -rn 'register_entity(' plugins/pd/hooks/lib/ plugins/pd/mcp/ | grep -v 'def register_entity\|test_'`. Capture full list. Verify against design FR-4 audit table.
- **Assertion shape:** captured count documented.
- **DoD:** caller list locked.
- **Dependencies:** Group 14.

### Task 15.1: Update backfill.py callers (5 sites → upsert_entity)

- **File:** `plugins/pd/hooks/lib/entity_registry/backfill.py`
- **Action:** Each of 5 `register_entity(` calls — replace with `upsert_entity(` and add `# F12 audit: idempotent backfill → upsert_entity` comment line.
- **Algorithm:** mechanical.
- **Assertion shape:** `grep -B1 'upsert_entity\|register_entity' backfill.py | grep -c 'F12 audit'` == 5.
- **DoD:** backfill tests pass.
- **Dependencies:** Task 15.0.

### Task 15.2: Update server_helpers.py callers (2 sites → register_entity raise-handled)

- **File:** `plugins/pd/hooks/lib/entity_registry/server_helpers.py`
- **Action:** Each call — add `# F12 audit: conflict-is-error → register_entity, EntityExistsError handled` comment + ensure surrounding code catches EntityExistsError appropriately.
- **DoD:** server_helpers tests pass.
- **Dependencies:** Task 15.1.

### Task 15.3: Update feature_lifecycle.py callers (2 sites → register)

- **File:** `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py`
- **Action:** Same pattern as 15.2.
- **DoD:** feature_lifecycle tests pass.
- **Dependencies:** Task 15.2.

### Task 15.4: Update task_promotion.py caller (1 site → register)

- **File:** `plugins/pd/hooks/lib/workflow_engine/task_promotion.py`
- **Action:** Same pattern.
- **DoD:** task_promotion tests pass.
- **Dependencies:** Task 15.3.

### Task 15.5: Update entity_status.py callers (2 sites → upsert)

- **File:** `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`
- **Action:** Replace with upsert_entity (reconciliation is idempotent intent) + audit comment.
- **DoD:** entity_status tests pass.
- **Dependencies:** Task 15.4.

### Task 15.6: Update entity_server.py MCP callers (3 sites → register with MCP error translation)

- **File:** `plugins/pd/mcp/entity_server.py`
- **Action:** Each of 3 register_entity calls — add audit comment; ensure surrounding try/except translates EntityExistsError to the MCP JSON error shape from design §3.5.
- **Algorithm:** modify try/except blocks.
- **Assertion shape:** test_entity_server tests cover the MCP error translation.
- **DoD:** entity_server tests pass with the new JSON error shape.
- **Dependencies:** Task 15.5.

### Task 15.7: Verify AC-4.8 1-to-1 coverage assertion + remove Group 13.8 skip markers

- **File:** `plugins/pd/hooks/lib/entity_registry/test_register_upsert_split.py`
- **Action:** Write `test_f12_audit_one_to_one_coverage` — zip grep of all register_entity/upsert_entity production call sites with grep for `F12 audit` comments preceding them; assert 1-to-1 coverage. **Also remove ALL remaining `@pytest.mark.skip(reason="F12 caller-migration pending...")` markers added in Task 13.8** — by this point every caller has been migrated and tests should run.
- **Assertion shape:** counts match; `grep -rn 'F12 caller-migration pending' plugins/pd/` returns 0.
- **DoD:** test passes; no skip markers remain; CI green with full test surface.
- **Dependencies:** Task 15.6.

### Task 15.8.0: DISCOVERY — enumerate skill/command MD files referencing register_entity

- **File:** none (output captured to `.review-history.md`)
- **Action:** Run `grep -rln 'register_entity' plugins/pd/skills/ plugins/pd/commands/` to enumerate the actual MD files. Commit the empirical file list to `.review-history.md`. (Per plan-reviewer iter-2 warning: the iter-1 plan's "expected files" list was hedged; replace with verified list.)
- **DoD:** verified MD file list captured.
- **Dependencies:** Task 15.7.

### Task 15.8: Skill/Command MD audit (per plan-reviewer iter-1 blocker)

- **File:** files identified in Task 15.8.0
- **Action:** For each MD file from 15.8.0: either (a) update the prose to add explicit instruction "on EntityExistsError, fall back to upsert_entity or surface as user-facing error"; or (b) verify the MD prose routes through the MCP entity_server (which already translates EntityExistsError per design §3.5 to a JSON error), in which case no prose update is needed but the routing rationale must be added as a brief inline comment in the MD.
- **Algorithm:** per-file decision.
- **Assertion shape:** every MD reference to register_entity either has updated handling prose OR a documented MCP-routing rationale.
- **DoD:** all affected MD files committed with the chosen routing; no silent semantic break.
- **Dependencies:** Task 15.8.0.

---

## Group 16: Doctor Integration + Final Migration Wiring

### Task 16.1: Register doctor check in session-start hook

- **File:** `plugins/pd/hooks/lib/doctor/__init__.py` (or doctor.py — verify location)
- **Action:** Register `check_status_write_path` from Group 10 in the doctor's check registry so it fires at SessionStart.
- **DoD:** session-start runs the check; doctor reports it in its output.
- **Dependencies:** Group 15.

### Task 16.2: VERIFY in-transaction FK check is present (added in Group 0.2)

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (verify migration 12 body)
- **Action:** **VERIFY-ONLY task per plan-reviewer iter-1.** The in-transaction `PRAGMA foreign_key_check` was added in Task 0.2 from day 1 of the feature. Confirm it's still present in migration 12 body just before the COMMIT and schema_version stamp.
- **Algorithm:** read migration 12 source, grep for `foreign_key_check` inside the BEGIN IMMEDIATE block.
- **Assertion shape:** `grep -A2 'BEGIN IMMEDIATE' database.py | grep 'foreign_key_check'` matches inside migration 12 body.
- **DoD:** verified present; no new code written.
- **Dependencies:** Task 16.1.

### Task 16.3: VERIFY post-commit defensive FK check is present (added in Group 0.2)

- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (verify migration 12 body)
- **Action:** **VERIFY-ONLY task per plan-reviewer iter-1.** The post-commit defensive FK check was added in Task 0.2. Confirm it's outside the try/finally block.
- **Assertion shape:** post-finally FK check matches source pattern from design §3.3.
- **DoD:** verified present; no new code written.
- **Dependencies:** Task 16.2.

### Task 16.4: Write end-to-end migration integration test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_migration_safety.py`
- **Action:** Write `test_migration_12_end_to_end` — `db = make_v11_db()`, run migration 12, assert all expected schema changes present + FK check clean + schema_version=12 + row count parity.
- **Mock pattern:** make_v11_db then EntityDatabase init re-trigger.
- **Assertion shape:** comprehensive post-state checks.
- **DoD:** integration test passes.
- **Dependencies:** Task 16.3.

### Task 16.5: Write down-migration test

- **File:** `plugins/pd/hooks/lib/entity_registry/test_migration_safety.py`
- **Action:** Write `test_migration_12_down` — apply migration 12, then apply migration_12_down, assert runtime state reverted (entity_type column restored, triggers restored, CHECK narrowed back). Implement `_migration_12_polymorphic_taxonomy_and_events_down` function + register in MIGRATIONS_DOWN[12].
- **Algorithm:** reverse of forward migration sub-steps.
- **Assertion shape:** post-down state matches v11 schema baseline.
- **DoD:** down test passes.
- **Dependencies:** Task 16.4.

---

## Cross-Group Verification (Final)

### Task X.1: Full grep-predicate audit

- **File:** none
- **Action:** Run all grep predicates from spec §4 Acceptance Criteria Roll-Up; assert each returns the expected count (0 for the negative grep-predicates).
- **DoD:** all 7 grep predicates pass.
- **Dependencies:** Group 16.

### Task X.2: Full pytest run

- **File:** none
- **Action:** Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/` and `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/`.
- **DoD:** all tests pass.
- **Dependencies:** Task X.1.

### Task X.3: Live DB migration smoke test

- **File:** none
- **Action:** Backup `~/.claude/pd/entities/entities.db`, run pd doctor (triggers migration if needed), verify schema_version=12 + no errors + entity counts preserved.
- **DoD:** live DB migrates cleanly.
- **Dependencies:** Task X.2.
