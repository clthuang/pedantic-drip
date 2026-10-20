# Tasks: Cross-Project Entity Scoping

## Shared Templates

**TEST_PROJECT_ID constant:** `TEST_PROJECT_ID = '__test__'` defined in `plugins/pd/hooks/lib/entity_registry/test_helpers.py` (created in T5.6). All test register_entity calls use this. Until T5.6, use inline `project_id="__test__"`.

**DB method project_id pattern:** `project_id: str | None = None` for optional, `project_id: str` for required. MCP tools default to `_project_id` module global. Convention: DB layer `None` = all projects; MCP layer `"*"` string → converted to `None` at handler.

**File path convention:** All paths relative to repo root (`plugins/pd/...`). `database.py` = `plugins/pd/hooks/lib/entity_registry/database.py`. `entity_server.py` = `plugins/pd/mcp/entity_server.py`.

**Entity server test location:** Unit tests for entity_server.py live at `plugins/pd/hooks/lib/entity_registry/test_entity_server.py` (not `plugins/pd/mcp/`). MCP integration tests (test_search_mcp.py, test_export_entities.py) live at `plugins/pd/mcp/`.

---

## Phase 1: Project Identity Module

### T1.1: Write normalize_remote_url tests
- **File:** `plugins/pd/hooks/lib/entity_registry/test_project_identity.py` (create new)
- **Design ref:** I-1, spec FS-1.3
- **AC:** 6 tests written and passing: (1) `git@github.com:terry/pedantic-drip.git` → `github.com/terry/pedantic-drip`, (2) `https://github.com/terry/pedantic-drip.git` → same, (3) `ssh://git@github.com/terry/pedantic-drip` → same, (4) `git://github.com/terry/pedantic-drip.git` → same, (5) `""` → `""`, (6) `/path/to/repo.git` → `/path/to/repo`
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_project_identity.py -v -k "normalize"`
- **Depends on:** none

### T1.2: Implement normalize_remote_url
- **File:** `plugins/pd/hooks/lib/entity_registry/project_identity.py` (create new)
- **Design ref:** I-1, spec FS-1.3
- **AC:** All T1.1 tests green. 7-step normalization: strip scheme → strip user@ → SCP colon→slash → strip .git → strip trailing / → lowercase host → return.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_project_identity.py -v -k "normalize"`
- **Depends on:** T1.1

### T1.3: Write detect_project_id tests
- **File:** `plugins/pd/hooks/lib/entity_registry/test_project_identity.py`
- **Design ref:** I-1, spec FS-1.1
- **AC:** 7 tests written: (1) git repo returns 12-char hex from root commit, (2) shallow clone (monkeypatch `subprocess.run` for rev-list to return rc=128) falls back to HEAD, (3) no-git (monkeypatch all subprocess.run to raise FileNotFoundError) returns SHA-256 of abs path truncated to 12, (4) `ENTITY_PROJECT_ID` env var (monkeypatch `os.environ`) overrides all detection, (5) second call with same args returns cached result (monkeypatch subprocess.run with call counter), (6) multiple root commits (stdout has 2 lines) takes first, (7) timeout (monkeypatch subprocess.run to raise `subprocess.TimeoutExpired`) falls to next fallback
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_project_identity.py -v -k "detect"`
- **Depends on:** none

### T1.4: Implement detect_project_id
- **File:** `plugins/pd/hooks/lib/entity_registry/project_identity.py`
- **Design ref:** I-1, spec FS-1.1, TD-7
- **AC:** All T1.3 tests green. Implementation: (1) check ENTITY_PROJECT_ID env var first, (2) check `git rev-parse --is-shallow-repository` — if "true", skip rev-list, (3) try `git rev-list --max-parents=0 HEAD`, take first line, truncate to 12, (4) fallback: `git rev-parse --short=12 HEAD`, (5) fallback: `hashlib.sha256(os.path.abspath(cwd)).hexdigest()[:12]`. `@functools.lru_cache(maxsize=1)`. Timeout=5s on all subprocess calls.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_project_identity.py -v -k "detect"`
- **Depends on:** T1.3

### T1.5: Write GitProjectInfo and collect_git_info tests
- **File:** `plugins/pd/hooks/lib/entity_registry/test_project_identity.py`
- **Design ref:** I-1, spec FS-1.2
- **AC:** 3 tests: (1) real git repo populates all 11 fields of GitProjectInfo (assert project_id is 12-char, root_commit_sha is 40-char, name is non-empty, etc.), (2) monkeypatch git remote to fail — remote_url/normalized_url/remote_host/owner/repo are empty strings but project_id and project_root still populated, (3) non-git dir (monkeypatch) returns is_git_repo=False with all git fields empty
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_project_identity.py -v -k "collect"`
- **Depends on:** T1.2, T1.4 (collect_git_info calls both)

### T1.6: Implement GitProjectInfo dataclass and collect_git_info
- **File:** `plugins/pd/hooks/lib/entity_registry/project_identity.py`
- **Design ref:** I-1, spec FS-1.2
- **AC:** All T1.5 tests green. `@dataclasses.dataclass(frozen=True)` with 11 fields. Each git subprocess call wrapped in try/except independently — partial failure fills empty string for that field.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_project_identity.py -v`
- **Depends on:** T1.5

**Verify Phase 1:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_project_identity.py -v` — all 16 tests green.

---

## Phase 2: Schema Migration

### T2.1: Write migration 8 schema tests
- **File:** `plugins/pd/hooks/lib/entity_registry/test_database.py`
- **Plan ref:** 2.1
- **AC:** Tests written (not yet passing) that assert: (a) projects table exists with all 13 columns, (b) sequences table exists with PK(project_id, entity_type), (c) entities table has project_id column with UNIQUE(project_id, type_id), (d) parent_type_id has no FK constraint, (e) parent_uuid FK preserved
- **Depends on:** none

### T2.2: Write migration 8 data tests
- **File:** `test_database.py`
- **Plan ref:** 2.1
- **AC:** Tests written that assert: (a) all existing entities get project_id='__unknown__', (b) same type_id in different projects coexist, (c) same type_id in same project rejected, (d) _metadata next_seq_* migrated to sequences table with project_id='__unknown__', (e) _metadata next_seq_* keys deleted, (f) FTS search works post-migration, (g) all 9 triggers exist (query sqlite_master for trigger count), (h) enforce_immutable_project_id trigger fires on UPDATE (assert sqlite3.IntegrityError), (i) rollback test: wrap conn.execute, raise OperationalError when SQL matches "ALTER TABLE entities_new RENAME" — assert original entities table has no project_id column post-exception, (j) migration is idempotent (open DB twice, second open is no-op)
- **Depends on:** none

### T2.3a: Implement migration 8 — table creation and data copy (steps 1-7)
- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Plan ref:** 2.1
- **AC:** PRAGMA FK off, BEGIN IMMEDIATE, CREATE projects/sequences/entities_new tables, INSERT data copy with '__unknown__', DROP+RENAME. T2.1 schema tests pass. Register as `_add_project_scoping` in MIGRATIONS dict key 8.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "migration_8_schema"`
- **Depends on:** T2.1, T2.2

### T2.3b: Implement migration 8 — triggers and indexes (steps 8-9)
- **File:** `database.py`
- **Plan ref:** 2.1
- **AC:** Recreate all 9 triggers (8 existing + enforce_immutable_project_id) and 6 indexes (4 existing + idx_project_id + idx_project_entity_type). T2.2 trigger tests (g, h) pass.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "migration_8_trigger"`
- **Depends on:** T2.3a

### T2.3c: Implement migration 8 — sequence migration, FTS, finalize (steps 10-14)
- **File:** `database.py`
- **Plan ref:** 2.1
- **AC:** Migrate _metadata next_seq_* to sequences table, delete old keys, rebuild FTS5, update schema_version, COMMIT, PRAGMA FK on. All T2.1 and T2.2 tests pass including rollback (i) and idempotency (j). **Checkpoint:** after tests pass, run `cp ~/.claude/pd/entities/entities.db ~/.claude/pd/entities/entities.db.pre-migration-8.bak` before proceeding to Phase 3.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "migration_8"`
- **Depends on:** T2.3b

### T2.4: Write next_sequence_value tests
- **File:** `test_database.py`
- **Plan ref:** 2.2
- **AC:** 4 tests pass: (a) bootstrap from empty sequences table scans entities, (b) increment returns sequential values, (c) different projects get independent counters, (d) structural atomicity test: monkeypatch conn.execute to capture SQL, call next_sequence_value, assert "BEGIN IMMEDIATE" appears (concurrent correctness covered by test_sqlite_retry_integration.py)
- **Depends on:** T2.3c (needs migration to create sequences table)

### T2.5: Implement next_sequence_value method
- **File:** `database.py`
- **Plan ref:** 2.2
- **AC:** All T2.4 tests pass. Bootstrap regex `^\d+` on entity_ids. Read-increment-write atomic in transaction.
- **Depends on:** T2.4

### T2.6a: Write generate_entity_id tests
- **File:** `plugins/pd/hooks/lib/entity_registry/test_id_generator.py`
- **Plan ref:** 2.3
- **AC:** 2 tests using real in-memory DB (`EntityDatabase(":memory:")` which auto-runs migration 8): (a) `generate_entity_id(db, "backlog", "test", project_id="__test__")` returns `"001-test"` (verify counter increments on second call → `"002-..."`), (b) `assert not hasattr(id_generator, "_scan_existing_max_seq")` — function must be deleted, not just unused.
- **Depends on:** T2.5

### T2.6b: Update generate_entity_id implementation
- **File:** `plugins/pd/hooks/lib/entity_registry/id_generator.py`
- **Plan ref:** 2.3
- **AC:** (a) project_id required param, (b) calls db.next_sequence_value, (c) _scan_existing_max_seq deleted. All T2.6a tests pass.
- **Depends on:** T2.6a

**Verify Phase 2:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "migration_8 or sequence" && plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_id_generator.py -v`

---

## Phase 3: Core DB API Changes

**Parallelism:** T3.1 is the gateway. After T3.1, T3.2 depends on T3.1, T3.3 depends on T3.1, T3.4 depends on T3.3. T3.5-T3.9 are independent of each other and of T3.3/T3.4 — they can run in parallel after T3.1.

### T3.1: Update _resolve_identifier with project_id
- **File:** `database.py`
- **Plan ref:** 3.1
- **AC:** (a) UUID lookup unchanged, (b) type_id + project_id filters correctly, (c) type_id without project_id returns if globally unique, (d) ambiguity error lists projects. 4 tests in `test_database.py`.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "resolve_identifier_project"`
- **Depends on:** T2.3c (migration)

### T3.2: Update resolve_ref and search_by_type_id_prefix with project_id
- **File:** `database.py`
- **Plan ref:** 3.1
- **AC:** (a) resolve_ref passes project_id to all three resolution paths, (b) search_by_type_id_prefix adds AND project_id=?, (c) return type unchanged (str for resolve_ref). 1 test: register two entities with identical type_id prefixes in different projects, call search_by_type_id_prefix with project_id=TEST_PROJECT_ID, assert only test entity returned.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "resolve_ref_project or prefix_project"`
- **Depends on:** T3.1

### T3.3: Update register_entity with project_id
- **File:** `plugins/pd/hooks/lib/entity_registry/database.py` (search for `def register_entity` ~line 1339)
- **Design ref:** I-2
- **Context:** Current register_entity uses `INSERT OR IGNORE` keyed on `UNIQUE(type_id)`. Post-migration, UNIQUE is `(project_id, type_id)`. The INSERT SQL (~line 1398), post-insert UUID lookup (~line 1424), and parent resolution (~line 1388) all need `AND project_id = ?`.
- **AC:** (a) project_id required param (no default), (b) INSERT includes project_id column, (c) post-insert UUID lookup: `WHERE type_id = ? AND project_id = ?`, (d) parent resolution: `WHERE type_id = ? AND project_id = ?`, (e) 3 tests: same type_id+project returns existing UUID, same type_id different project creates new entity, parent resolved within project.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "register_project"`
- **Depends on:** T3.1 (for parent resolution via _resolve_identifier)

### T3.4: Update register_entities_batch with project_id
- **File:** `database.py`
- **Plan ref:** 3.2
- **AC:** project_id required, applied to all entities in batch. 1 test: call register_entities_batch twice with same entities (same project_id, same type_ids) and assert UUIDs unchanged (idempotent).
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "batch_project"`
- **Depends on:** T3.3

### T3.5: Update query methods with project_id
- **File:** `database.py`
- **Plan ref:** 3.3
- **AC:** 5 tests in `test_database.py` (name convention: `test_project_scoped_query_list_entities`, etc.). Each test: register two entities under different project_ids (`"__test__"` and `"__other__"`), assert passing `project_id="__test__"` returns only the test entity, passing `project_id=None` returns both. For `export_lineage_markdown`: filter root entities by project_id (children included via existing tree-walk from filtered roots).
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "project_scoped_query"`
- **Depends on:** T2.3c (migration must have run to create project_id column)

### T3.6: Update set_parent with project_id
- **File:** `database.py`
- **Plan ref:** 3.4
- **AC:** 1 test in `test_database.py`: register two entities with same type_id under different project_ids. Call set_parent with project_id=TEST_PROJECT_ID and assert only the test entity's parent is set. Verify: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "set_parent_project"`
- **Depends on:** T3.1

### T3.7: Update delete_entity with project_id and extended cascade
- **File:** `database.py`
- **Plan ref:** 3.4, TD-6
- **AC:** (a) resolves type_id via _resolve_identifier with project_id, (b) deletes by UUID not type_id, (c) cascade: entity_tags, entity_dependencies, entity_okr_alignment, workflow_phases, entities_fts, entities. 2 tests: register entity with tags+deps+OKR, delete it, assert all junction table rows gone.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "delete_cascade"`
- **Depends on:** T3.1

### T3.8: Update update_entity with project_id and re-attribution
- **File:** `database.py`
- **Plan ref:** 3.4, TD-8
- **AC:** (a) project_id for _resolve_identifier, (b) new_project_id triggers trigger-drop: DROP TRIGGER, UPDATE project_id, FTS sync, CREATE TRIGGER, (c) preserves UUID/tags/deps/OKR/workflow_phases, (d) atomic rollback on failure. 4 tests.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "reattribution"`
- **Depends on:** T3.1

### T3.9: Update upsert_workflow_phase with required project_id
- **File:** `database.py`
- **Plan ref:** 3.4, TD-4
- **AC:** project_id required for entity existence check. 1 test: register entity under TEST_PROJECT_ID, call upsert_workflow_phase with project_id=TEST_PROJECT_ID (succeeds); call with project_id='__other__' (assert ValueError — entity not found in that project).
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "upsert_workflow_phase_project"`
- **Depends on:** T3.1

**Verify Phase 3:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v`

---

## Phase 4: MCP Server Layer

### T4.1: Update entity_server startup with project_id detection
- **File:** `plugins/pd/mcp/entity_server.py`
- **Plan ref:** 4.1
- **AC:** (a) _project_id and _git_info module globals added, (b) lifespan() calls detect_project_id, (c) _upsert_project using ON CONFLICT DO UPDATE (preserves created_at), (d) _backfill_project_ids with LIKE escaping + log count, (e) _resolve_ref_param passes _project_id. 2 tests in `plugins/pd/hooks/lib/entity_registry/test_entity_server.py` (MCP startup tests are co-located here for historical reasons): (1) monkeypatch detect_project_id → "abc123def456", assert _project_id set after lifespan; (2) pre-populate DB with __unknown__ entity matching project_root, call _backfill_project_ids, assert entity claimed.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_entity_server.py -v -k "startup"`
- **Depends on:** T1.6, T3.1

### T4.2: Update register_entity MCP tool with project_id and auto_id
- **File:** `plugins/pd/mcp/entity_server.py`
- **Plan ref:** 4.2
- **AC:** (a) project_id defaults to _project_id, (b) auto_id=true + no entity_id calls generate_entity_id, (c) auto_id=true + entity_id raises error, (d) `"*"` not supported for register (always single project)
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_entity_server.py -v -k "register"`
- **Depends on:** T4.1, T3.3

### T4.3: Update search/export/lineage MCP tools with project_id
- **File:** `plugins/pd/mcp/entity_server.py`
- **Plan ref:** 4.2
- **AC:** Update these 3 tools: `search_entities`, `export_entities`, `export_lineage_markdown`. Each accepts project_id param, defaults to `_project_id`, `"*"` maps to `None`. Add 1 project_id filtering test per tool in existing test files (no new test files needed).
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_search_mcp.py plugins/pd/mcp/test_export_entities.py -v`
- **Depends on:** T4.1, T3.5

### T4.4: Update update_entity MCP tool with project_id and new_project_id
- **File:** `plugins/pd/mcp/entity_server.py`
- **Plan ref:** 4.2
- **AC:** project_id for resolution, new_project_id for re-attribution pass-through.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_entity_server.py -v -k "update"`
- **Depends on:** T4.1, T3.8

### T4.5: Implement list_projects MCP tool
- **File:** `plugins/pd/mcp/entity_server.py`
- **Plan ref:** 4.2
- **AC:** Returns all projects ordered by created_at. No filters in v1. 1 test in test_entity_server.py.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_entity_server.py -v -k "list_projects"`
- **Depends on:** T4.1

### T4.6: Update server_helpers with project_id
- **File:** `plugins/pd/hooks/lib/entity_registry/server_helpers.py`
- **Plan ref:** 4.3
- **AC:** _process_register_entity adds project_id + auto_id. _process_export_entities adds project_id. Done when: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_server_helpers.py -v` passes.
- **Depends on:** T3.3, T3.5

### T4.7: Update workflow_state_server with project_id
- **File:** `plugins/pd/mcp/workflow_state_server.py`
- **Plan ref:** 4.4
- **AC:** _project_id global at startup. list_features_by_phase/status accept project_id, default _project_id. 2 tests.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v -k "project"`
- **Depends on:** T1.4, T3.5

**Verify Phase 4:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_entity_server.py plugins/pd/mcp/test_search_mcp.py plugins/pd/mcp/test_workflow_state_server.py plugins/pd/mcp/test_export_entities.py -v`

---

## Phase 5: Consumer Updates

### T5.1: Update backfill.py with project_id
- **File:** `plugins/pd/hooks/lib/entity_registry/backfill.py`
- **Plan ref:** 5.1
- **AC:** (a) _BACKFILL_VERSION bumped to "3", (b) run_backfill accepts project_id, passes to register_entity, (c) backfill_workflow_phases accepts project_id, passes to upsert_workflow_phase. 3 tests.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_backfill.py -v -k "project"`
- **Depends on:** T3.3, T3.9

### T5.2: Update reconciliation_orchestrator with project_id
- **File:** `plugins/pd/hooks/lib/reconciliation_orchestrator/brainstorm_registry.py`, `entity_status.py`, `__main__.py`
- **Plan ref:** 5.2
- **AC:** (a) brainstorm_registry passes project_id to register_entity, (b) entity_status passes project_id to update_entity, (c) __main__ derives project_id via detect_project_id.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/reconciliation_orchestrator/ -v`
- **Depends on:** T1.4, T3.3, T3.8

### T5.3: Update add-to-backlog command
- **File:** `plugins/pd/commands/add-to-backlog.md`
- **Plan ref:** 5.3
- **AC:** File-parsing ID logic removed. Uses register_entity with auto_id=true, no entity_id.
- **Verify:** `grep -En 'max_id|int\(.*split|next_id|00001' plugins/pd/commands/add-to-backlog.md` returns no matches (uses -E for macOS BSD grep). Confirm: `grep -c 'auto_id' plugins/pd/commands/add-to-backlog.md` returns ≥1.
- **Depends on:** T4.2

### T5.4: Update doctor checks
- **File:** `plugins/pd/hooks/lib/doctor/checks.py`
- **Plan ref:** 5.4
- **AC:** (a) ENTITY_SCHEMA_VERSION=8, (b) check_entity_orphans filters by project_id, (c) check_project_attribution warns on __unknown__, (d) --fix runs artifact-path backfill. 5 tests.
- **Verify:** `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v -k "project or attribution or schema_version"`
- **Depends on:** T2.3c, T4.1

### T5.5: Update source files with project_id plumbing
- **File:** `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py`, `plugins/pd/hooks/lib/workflow_engine/task_promotion.py`
- **Plan ref:** 5.5
- **Context:** These files call `db.register_entity()` which now requires project_id. Derive project_id inline via `detect_project_id(os.environ.get("PROJECT_ROOT", os.getcwd()))` at the top of each affected function — matching the pattern in reconciliation_orchestrator/__main__.py (T5.2). Do NOT add project_id as a parameter to public workflow engine functions.
- **AC:** (a) `grep -n 'register_entity' plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py plugins/pd/hooks/lib/workflow_engine/task_promotion.py` shows all call sites have project_id, (b) project_id derived via detect_project_id (import added).
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_feature_lifecycle.py plugins/pd/hooks/lib/workflow_engine/test_task_promotion.py -v`
- **Depends on:** T3.3, T1.4 (for detect_project_id import)

### T5.6: Create TEST_PROJECT_ID helper and update Group B test files
- **File:** Create `plugins/pd/hooks/lib/entity_registry/test_helpers.py` with `TEST_PROJECT_ID = '__test__'`.
- **Group B files (14):** `test_backfill.py`, `test_backfill_parent_uuid.py`, `test_frontmatter_sync.py`, `test_frontmatter.py`, `test_search.py`, `test_server_helpers.py`, `test_entity_server.py`, `test_entity_lifecycle.py`, `test_ref_resolution.py`, `test_id_generator.py`, `test_dependencies.py`, `test_database_052.py`, `doctor/test_checks.py`, `doctor/test_fixer.py`
- **Plan ref:** 5.5
- **AC:** (a) test_helpers.py exists with TEST_PROJECT_ID constant, (b) all register_entity/register_entities_batch calls in Group B files import and use TEST_PROJECT_ID, (c) also replace any inline `project_id="__test__"` strings from Phase 2/3 test additions with the import for consistency, (d) capture baseline before changes: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v --tb=no -q 2>&1 | tail -5`. Done when same command shows no NEW failures.
- **Depends on:** T3.3, T3.4

### T5.7: Update Group C test files (reconciliation/workflow)
- **Files (10):** `reconciliation_orchestrator/test_orchestrator.py`, `reconciliation_orchestrator/test_entity_status.py`, `reconciliation_orchestrator/test_brainstorm_registry.py`, `workflow_engine/test_reconciliation.py`, `workflow_engine/test_entity_engine.py`, `workflow_engine/test_feature_lifecycle.py`, `workflow_engine/test_secretary_intelligence.py`, `workflow_engine/test_task_promotion.py`, `workflow_engine/test_rollup.py`, `workflow_engine/test_engine.py`
- **Plan ref:** 5.5
- **AC:** All register_entity/update_entity calls include project_id. Capture baseline before changes: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ plugins/pd/hooks/lib/reconciliation_orchestrator/ -v --tb=no -q 2>&1 | tail -5`. Done when no NEW failures beyond baseline.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ plugins/pd/hooks/lib/reconciliation_orchestrator/ -v --tb=short`
- **Depends on:** T5.2, T5.5, T5.6

### T5.8: Update Group D test files (semantic_memory, UI)
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_keywords.py`, `plugins/pd/ui/tests/test_entities.py`
- **Plan ref:** 5.5
- **AC:** All register_entity calls include project_id. All tests pass.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_keywords.py -v && PYTHONPATH="plugins/pd/hooks/lib:plugins/pd" plugins/pd/.venv/bin/python -m pytest plugins/pd/ui/tests/test_entities.py -v`
- **Depends on:** T5.6

**Verify Phase 5:**
```
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/ -v
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v
PYTHONPATH="plugins/pd/hooks/lib:plugins/pd" plugins/pd/.venv/bin/python -m pytest plugins/pd/ui/tests/ -v
```

---

## Final Verification

After all tasks complete:
1. Full entity_registry test suite (940+ existing + ~48 new)
2. Full MCP test suite
3. Doctor tests
4. UI tests
5. Manual: backup real DB → start entity_server → verify migration → search_entities → doctor
