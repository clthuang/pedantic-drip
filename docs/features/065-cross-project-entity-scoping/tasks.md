# Tasks: Cross-Project Entity Scoping

## Shared Templates

**TEST_PROJECT_ID constant:** `TEST_PROJECT_ID = '__test__'` in test helper. All test register_entity calls use this.

**DB method project_id pattern:** `project_id: str | None = None` for optional, `project_id: str` for required. MCP tools default to `_project_id` module global.

---

## Phase 1: Project Identity Module

### T1.1: Write normalize_remote_url tests
- **File:** `plugins/pd/hooks/lib/entity_registry/test_project_identity.py`
- **Plan ref:** 1.1
- **AC:** 6 tests pass: SSH SCP → `github.com/terry/pedantic-drip`, HTTPS same, ssh:// same, git:// same, empty → empty, local path → path without .git suffix
- **Depends on:** none

### T1.2: Implement normalize_remote_url
- **File:** `plugins/pd/hooks/lib/entity_registry/project_identity.py`
- **Plan ref:** 1.1
- **AC:** All T1.1 tests pass. Function follows 7-step normalization from spec FS-1.3.
- **Depends on:** T1.1

### T1.3: Write detect_project_id tests
- **File:** `test_project_identity.py`
- **Plan ref:** 1.1
- **AC:** 7 tests pass: root commit returns 12-char hex, shallow clone falls back to HEAD, no-git falls back to abs path hash, ENTITY_PROJECT_ID env var overrides, lru_cache hit on second call with same args, multiple root commits takes first, timeout falls to next fallback
- **Depends on:** none

### T1.4: Implement detect_project_id
- **File:** `project_identity.py`
- **Plan ref:** 1.1
- **AC:** All T1.3 tests pass. Shallow detection via `git rev-parse --is-shallow-repository`. lru_cache(maxsize=1).
- **Depends on:** T1.3

### T1.5: Write GitProjectInfo and collect_git_info tests
- **File:** `test_project_identity.py`
- **Plan ref:** 1.1
- **AC:** 3 tests pass: full git info populates all fields, partial failure leaves empty strings for failed fields, non-git dir returns is_git_repo=False with empty git fields
- **Depends on:** T1.2, T1.4 (collect_git_info uses both)

### T1.6: Implement GitProjectInfo dataclass and collect_git_info
- **File:** `project_identity.py`
- **Plan ref:** 1.1
- **AC:** All T1.5 tests pass. Dataclass is frozen. Each git query independent.
- **Depends on:** T1.5

**Verify Phase 1:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_project_identity.py -v`

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
- **AC:** Tests written that assert: (a) all existing entities get project_id='__unknown__', (b) same type_id in different projects coexist, (c) same type_id in same project rejected, (d) _metadata next_seq_* migrated to sequences table with project_id='__unknown__', (e) _metadata next_seq_* keys deleted, (f) FTS search works post-migration, (g) all 9 triggers exist, (h) enforce_immutable_project_id trigger fires on UPDATE, (i) migration rolls back on failure, (j) migration is idempotent
- **Depends on:** none

### T2.3: Implement _add_project_scoping migration function
- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Plan ref:** 2.1
- **AC:** All T2.1 and T2.2 tests pass. Function registered in MIGRATIONS dict as key 8. Uses exact DDL from design I-7. Self-managed transaction with rollback.
- **Depends on:** T2.1, T2.2

### T2.4: Write next_sequence_value tests
- **File:** `test_database.py`
- **Plan ref:** 2.2
- **AC:** 4 tests pass: (a) bootstrap from empty sequences table scans entities, (b) increment returns sequential values, (c) different projects get independent counters, (d) atomic under BEGIN IMMEDIATE
- **Depends on:** T2.3 (needs migration to create sequences table)

### T2.5: Implement next_sequence_value method
- **File:** `database.py`
- **Plan ref:** 2.2
- **AC:** All T2.4 tests pass. Bootstrap regex `^\d+` on entity_ids. Read-increment-write atomic in transaction.
- **Depends on:** T2.4

### T2.6: Write id_generator tests and update generate_entity_id
- **File:** `id_generator.py`, `test_id_generator.py`
- **Plan ref:** 2.3
- **AC:** (a) generate_entity_id requires project_id param, (b) uses next_sequence_value instead of _metadata, (c) _scan_existing_max_seq deleted, (d) 2 new tests pass
- **Depends on:** T2.5

**Verify Phase 2:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "migration_8 or sequence" && plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_id_generator.py -v`

---

## Phase 3: Core DB API Changes

### T3.1: Update _resolve_identifier with project_id
- **File:** `database.py`
- **Plan ref:** 3.1
- **AC:** (a) UUID lookup unchanged, (b) type_id + project_id filters correctly, (c) type_id without project_id returns if globally unique, (d) ambiguity error lists projects. 4 tests pass.
- **Depends on:** T2.3 (migration)

### T3.2: Update resolve_ref and search_by_type_id_prefix with project_id
- **File:** `database.py`
- **Plan ref:** 3.1
- **AC:** (a) resolve_ref passes project_id to all three resolution paths, (b) search_by_type_id_prefix adds AND project_id=?, (c) return type unchanged (str for resolve_ref)
- **Depends on:** T3.1

### T3.3: Update register_entity with project_id
- **File:** `database.py`
- **Plan ref:** 3.2
- **AC:** (a) project_id required param, (b) INSERT includes project_id, (c) post-insert UUID lookup uses AND project_id=?, (d) parent resolution uses AND project_id=?, (e) idempotency within same project preserved, (f) same type_id in different project creates new entity. 3 tests pass.
- **Depends on:** T3.1 (for parent resolution)

### T3.4: Update register_entities_batch with project_id
- **File:** `database.py`
- **Plan ref:** 3.2
- **AC:** project_id required, applied to all entities in batch. Same idempotency semantics as T3.3.
- **Depends on:** T3.3

### T3.5: Update query methods with project_id
- **File:** `database.py`
- **Plan ref:** 3.3
- **AC:** list_entities, search_entities, export_entities_json, export_lineage_markdown, scan_entity_ids all accept optional project_id. None=all projects, string=filter. Tests verify filtering.
- **Depends on:** T2.3 (migration)

### T3.6: Update set_parent with project_id
- **File:** `database.py`
- **Plan ref:** 3.4
- **AC:** project_id passed to _resolve_identifier for both type_id args.
- **Depends on:** T3.1

### T3.7: Update delete_entity with project_id and extended cascade
- **File:** `database.py`
- **Plan ref:** 3.4, TD-6
- **AC:** (a) resolves type_id via _resolve_identifier with project_id, (b) deletes by UUID not type_id, (c) cascade: entity_tags, entity_dependencies, entity_okr_alignment, workflow_phases, entities_fts, entities. 2 tests verify junction table cleanup.
- **Depends on:** T3.1

### T3.8: Update update_entity with project_id and re-attribution
- **File:** `database.py`
- **Plan ref:** 3.4, TD-8
- **AC:** (a) project_id for _resolve_identifier, (b) new_project_id triggers trigger-drop: DROP TRIGGER, UPDATE project_id, FTS sync, CREATE TRIGGER, (c) preserves UUID/tags/deps/OKR/workflow_phases, (d) atomic rollback on failure. 4 tests pass.
- **Depends on:** T3.1

### T3.9: Update upsert_workflow_phase with required project_id
- **File:** `database.py`
- **Plan ref:** 3.4, TD-4
- **AC:** project_id required for entity existence check. Callers must resolve type_id within project scope first.
- **Depends on:** T3.1

**Verify Phase 3:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v`

---

## Phase 4: MCP Server Layer

### T4.1: Update entity_server startup with project_id detection
- **File:** `plugins/pd/mcp/entity_server.py`
- **Plan ref:** 4.1
- **AC:** (a) _project_id and _git_info module globals added, (b) lifespan() calls detect_project_id, (c) _upsert_project using ON CONFLICT DO UPDATE (preserves created_at), (d) _backfill_project_ids with LIKE escaping, (e) _resolve_ref_param passes _project_id
- **Depends on:** T1.6, T3.1

### T4.2: Update register_entity MCP tool with project_id and auto_id
- **File:** `entity_server.py`
- **Plan ref:** 4.2
- **AC:** (a) project_id defaults to _project_id, (b) auto_id=true + no entity_id calls generate_entity_id, (c) auto_id=true + entity_id raises error, (d) `"*"` not supported for register (always single project)
- **Depends on:** T4.1, T3.3

### T4.3: Update search/export/lineage MCP tools with project_id
- **File:** `entity_server.py`
- **Plan ref:** 4.2
- **AC:** Each tool accepts project_id, defaults to _project_id, `"*"` maps to None (all projects).
- **Depends on:** T4.1, T3.5

### T4.4: Update update_entity MCP tool with project_id and new_project_id
- **File:** `entity_server.py`
- **Plan ref:** 4.2
- **AC:** project_id for resolution, new_project_id for re-attribution pass-through.
- **Depends on:** T4.1, T3.8

### T4.5: Implement list_projects MCP tool
- **File:** `entity_server.py`
- **Plan ref:** 4.2
- **AC:** Returns all projects ordered by created_at. No filters in v1. 1 test.
- **Depends on:** T4.1

### T4.6: Update server_helpers with project_id
- **File:** `server_helpers.py`
- **Plan ref:** 4.3
- **AC:** _process_register_entity adds project_id + auto_id. _process_export_entities adds project_id.
- **Depends on:** T3.3, T3.5

### T4.7: Update workflow_state_server with project_id
- **File:** `workflow_state_server.py`
- **Plan ref:** 4.4
- **AC:** _project_id global at startup. list_features_by_phase/status accept project_id, default _project_id. 2 tests.
- **Depends on:** T1.4, T3.5

**Verify Phase 4:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_search_mcp.py plugins/pd/mcp/test_workflow_state_server.py plugins/pd/mcp/test_export_entities.py -v`

---

## Phase 5: Consumer Updates

### T5.1: Update backfill.py with project_id
- **File:** `backfill.py`
- **Plan ref:** 5.1
- **AC:** (a) _BACKFILL_VERSION bumped to "3", (b) run_backfill accepts project_id, passes to register_entity, (c) backfill_workflow_phases accepts project_id, passes to upsert_workflow_phase. 3 tests.
- **Depends on:** T3.3, T3.9

### T5.2: Update reconciliation_orchestrator with project_id
- **File:** `reconciliation_orchestrator/brainstorm_registry.py`, `entity_status.py`, `__main__.py`
- **Plan ref:** 5.2
- **AC:** (a) brainstorm_registry passes project_id to register_entity, (b) entity_status passes project_id to update_entity, (c) __main__ derives project_id via detect_project_id.
- **Depends on:** T1.4, T3.3, T3.8

### T5.3: Update add-to-backlog command
- **File:** `plugins/pd/commands/add-to-backlog.md`
- **Plan ref:** 5.3
- **AC:** File-parsing ID logic removed. Uses register_entity with auto_id=true.
- **Depends on:** T4.2

### T5.4: Update doctor checks
- **File:** `plugins/pd/hooks/lib/doctor/checks.py`
- **Plan ref:** 5.4
- **AC:** (a) ENTITY_SCHEMA_VERSION=8, (b) check_entity_orphans filters by project_id, (c) check_project_attribution warns on __unknown__, (d) --fix runs artifact-path backfill. 5 tests.
- **Depends on:** T2.3, T4.1

### T5.5: Update source files with project_id plumbing
- **File:** `workflow_engine/feature_lifecycle.py`, `workflow_engine/task_promotion.py`
- **Plan ref:** 5.5
- **AC:** All register_entity calls in these files include project_id parameter.
- **Depends on:** T3.3

### T5.6: Create TEST_PROJECT_ID helper and update Group B test files
- **File:** `test_helpers.py` + 14 test files listed in plan 5.5 Group B
- **Plan ref:** 5.5
- **AC:** TEST_PROJECT_ID='__test__' constant. All register_entity/register_entities_batch calls in Group B files use it. All tests pass.
- **Depends on:** T3.3, T3.4

### T5.7: Update Group C test files (reconciliation/workflow)
- **File:** 10 test files listed in plan 5.5 Group C
- **Plan ref:** 5.5
- **AC:** All register_entity/update_entity calls include project_id. All tests pass.
- **Depends on:** T5.2, T5.5, T5.6

### T5.8: Update Group D test files (semantic_memory, UI)
- **File:** `semantic_memory/test_keywords.py`, `ui/tests/test_entities.py`
- **Plan ref:** 5.5
- **AC:** All register_entity calls include project_id. All tests pass.
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
