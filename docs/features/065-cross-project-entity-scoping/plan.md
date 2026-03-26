# Plan: Cross-Project Entity Scoping

## Implementation Order

5 phases, ~48 estimated tests. Each phase builds on the previous. Tests written before or alongside implementation (TDD where practical).

## Phase 1: Foundation — Project Identity Module (no dependencies)

### 1.1 Create `project_identity.py`
**File:** `plugins/pd/hooks/lib/entity_registry/project_identity.py`
**Design ref:** I-1

- `normalize_remote_url(raw_url)` — pure function, test first
- `detect_project_id(working_dir)` — env var override, shallow check, fallback chain, lru_cache
- `GitProjectInfo` dataclass
- `collect_git_info(working_dir)` — assembles all fields, each independent

**Tests first:** `plugins/pd/hooks/lib/entity_registry/test_project_identity.py`
- normalize_remote_url: SSH SCP, HTTPS, ssh://, git://, empty, local path (~6 tests)
- detect_project_id: root commit, shallow fallback, no-git fallback, env var override, cache hit, multiple roots (~7 tests)
- collect_git_info: full info, partial failure, non-git dir (~3 tests)

**Depends on:** nothing
**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_project_identity.py -v`

## Phase 2: Schema Migration (depends on Phase 1)

### 2.1 Write migration 8 function
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Design ref:** I-7 (exact DDL), TD-1, TD-2, TD-3, TD-5, TD-6

- `_add_project_scoping(conn)` — self-managed transaction following `_schema_expansion_v6` pattern
- 14-step DDL sequence: FK off, BEGIN IMMEDIATE, CREATE projects/sequences/entities_new, data copy with `'__unknown__'`, DROP+RENAME, 9 triggers, 6 indexes, counter migration, FTS rebuild, version update, COMMIT, FK on
- Register in `MIGRATIONS` dict as key `8`

### 2.2 Write `next_sequence_value()` method
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Design ref:** I-2

- Bootstrap scan: regex `^\d+` on entity_ids filtered by project_id + entity_type
- Atomic read-increment-write within transaction
- Return pre-increment value (next_val holds NEXT-to-issue)

### 2.3 Update `id_generator.py`
**File:** `plugins/pd/hooks/lib/entity_registry/id_generator.py`
**Design ref:** I-3

- `generate_entity_id(db, entity_type, name, project_id)` — required project_id
- Call `db.next_sequence_value(project_id, entity_type)` instead of `_metadata`
- Delete `_scan_existing_max_seq` (superseded)

**Tests:** Add to `plugins/pd/hooks/lib/entity_registry/test_database.py`
- Migration 8: fresh DB schema, data copy, composite UNIQUE allow/reject, 9 triggers, FTS works, counter migration, rollback safety, idempotent (~13 tests)
- next_sequence_value: bootstrap, increment, project isolation (~4 tests)
- id_generator: project-scoped generation (~2 tests)

**Depends on:** Phase 1 (detect_project_id used in backfill path)
**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "migration_8 or sequence or id_gen"`

## Phase 3: Core DB API Changes (depends on Phase 2)

### 3.1 Update `_resolve_identifier` and `resolve_ref`
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Design ref:** I-2 (FS-3.2)

- `_resolve_identifier(identifier, project_id=None)` — add `AND project_id = ?` for type_id path, ambiguity error for multi-project
- `resolve_ref(ref, project_id=None)` — pass project_id to exact lookup and prefix search
- `search_by_type_id_prefix(prefix, project_id=None)` — add WHERE clause

### 3.2 Update `register_entity` and `register_entities_batch`
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Design ref:** I-2

- Add `project_id: str` (required) to both
- INSERT includes project_id column
- Post-insert UUID lookup: `WHERE type_id = ? AND project_id = ?`
- Parent resolution: `WHERE type_id = ? AND project_id = ?` (parents in same project)

### 3.3 Update query methods
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Design ref:** I-2

- `list_entities(project_id=None)` — add WHERE clause
- `search_entities(project_id=None)` — JOIN filter on entities table
- `export_entities_json(project_id=None)` — add WHERE clause
- `export_lineage_markdown(project_id=None)` — filter roots
- `scan_entity_ids(project_id=None)` — add WHERE clause

### 3.4 Update mutation methods
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Design ref:** I-2, TD-6, TD-8

- `set_parent(type_id, parent_type_id, project_id=None)` — pass project_id to _resolve_identifier
- `update_entity(..., project_id=None, new_project_id=None)` — re-attribution via trigger-drop (TD-8) with FTS sync
- `delete_entity(type_id, project_id=None)` — resolve via _resolve_identifier, delete by UUID. Fix cascade gap: also delete entity_tags, entity_dependencies, entity_okr_alignment rows
- `upsert_workflow_phase(type_id, project_id, **kwargs)` — project_id required for entity existence check

**Tests:** Add to `test_database.py`
- _resolve_identifier: UUID unchanged, type_id with project, type_id without project (unique), ambiguity error (~4 tests)
- register_entity: idempotency within project, new entity across projects, parent resolution (~3 tests)
- delete_entity: extended cascade (tags, deps, OKR cleaned up) (~2 tests)
- re-attribution: trigger-drop, data preserved, FTS sync, rollback (~4 tests)

**Depends on:** Phase 2 (migration must have run)
**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v`

## Phase 4: MCP Server Layer (depends on Phase 3)

### 4.1 Update `entity_server.py` startup
**File:** `plugins/pd/mcp/entity_server.py`
**Design ref:** I-4, I-5

- Add `_project_id` and `_git_info` module globals
- In `lifespan()`: detect project_id, upsert project, backfill `__unknown__` entities
- `_upsert_project(db, info)` — INSERT ... ON CONFLICT DO UPDATE (preserves created_at)
- `_backfill_project_ids(db, project_root, project_id)` — UPDATE with LIKE escaping, log count
- Update `_resolve_ref_param` to pass `_project_id`

### 4.2 Update MCP tool functions
**File:** `plugins/pd/mcp/entity_server.py`
**Design ref:** I-4

- `register_entity` — add project_id param (default `_project_id`), auto_id param
- `update_entity` — add project_id and new_project_id params
- `search_entities` — add project_id param, `"*"` → None mapping
- `export_entities` — add project_id param
- `export_lineage_markdown` — add project_id param
- New `list_projects` tool

### 4.3 Update `server_helpers.py`
**File:** `plugins/pd/hooks/lib/entity_registry/server_helpers.py`
**Design ref:** I-6

- `_process_register_entity` — add project_id, auto_id pass-through
- `_process_export_entities` — add project_id pass-through

### 4.4 Update `workflow_state_server.py`
**File:** `plugins/pd/mcp/workflow_state_server.py`
**Design ref:** I-9

- Add `_project_id` global, resolved at startup
- `list_features_by_phase`, `list_features_by_status` — add project_id param

**Tests:** Update existing MCP test files
- `test_search_mcp.py` — search with project_id filtering (~3 tests)
- `test_export_entities.py` — export with project_id (~2 tests)
- `test_workflow_state_server.py` — list with project_id (~2 tests)
- New: list_projects tool, auto_id registration (~3 tests)

**Depends on:** Phase 3 (DB methods with project_id)
**Verification:**
```
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_search_mcp.py plugins/pd/mcp/test_workflow_state_server.py -v
```

## Phase 5: Consumer Updates (depends on Phase 4)

### 5.1 Update `backfill.py`
**File:** `plugins/pd/hooks/lib/entity_registry/backfill.py`
**Design ref:** I-8

- Bump `_BACKFILL_VERSION` to `"3"`
- `run_backfill(db, artifacts_root, project_id)` — pass project_id to all register_entity calls
- `backfill_workflow_phases` — derive project_id internally via `detect_project_id()` if it calls `upsert_workflow_phase`

### 5.2 Update `add-to-backlog` command
**File:** `plugins/pd/commands/add-to-backlog.md`
**Design ref:** Spec FS-6.1

- Remove file-parsing ID generation
- Use `register_entity` MCP tool with `auto_id=true`, omit `entity_id`

### 5.3 Update doctor checks
**File:** `plugins/pd/hooks/lib/doctor/checks.py`
**Design ref:** I-10

- Bump `ENTITY_SCHEMA_VERSION` to 8
- `check_entity_orphans` — filter by project_id column
- New `check_project_attribution` — warn on `__unknown__` entities
- Auto-fix: run artifact-path backfill via `--fix`

### 5.4 Update existing tests for changed signatures
**Files:** `test_backfill.py`, `test_frontmatter_sync.py`, `test_database.py` (existing tests)

- All `register_entity` calls in tests must include `project_id` parameter
- All `register_entities_batch` calls must include `project_id`
- Update test helpers/fixtures to supply project_id

**Tests:**
- Doctor: schema version, attribution warnings, auto-fix (~5 tests)
- Backfill: project_id pass-through (~3 tests)

**Depends on:** Phase 4 (MCP tools with project_id for add-to-backlog)
**Verification:**
```
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/ -v
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v
```

## Dependency Graph

```
Phase 1 (project_identity.py)
    ↓
Phase 2 (migration 8, sequences, id_generator)
    ↓
Phase 3 (DB API: resolve, register, query, mutate)
    ↓
Phase 4 (MCP server: startup, tools, helpers)
    ↓
Phase 5 (consumers: backfill, add-to-backlog, doctor, test updates)
```

## Final Verification

After all phases:
1. `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v` (940+ existing + ~48 new)
2. `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/ -v`
3. `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v`
4. `PYTHONPATH="plugins/pd/hooks/lib:plugins/pd" plugins/pd/.venv/bin/python -m pytest plugins/pd/ui/tests/ -v`
5. Manual: backup real DB → start entity_server → verify migration → run search_entities → run doctor
