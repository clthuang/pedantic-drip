# Plan: Entity Export MCP Tool

## Implementation Order

Bottom-up, test-first approach: database layer → helper layer → MCP tool layer. Each phase builds on the previous one.

```
Phase 1: Database Layer (constant + method)
  └── 1.1 EXPORT_SCHEMA_VERSION constant + export_entities_json() method + tests
        ↓
Phase 2: Helper Layer (serialization + file I/O)
  └── 2.1 _process_export_entities() function + tests
        ↓
Phase 3: MCP Tool Layer (thin entry point)
  └── 3.1 export_entities MCP tool + import update + tests
        ↓
Phase 4: Final Regression
  └── 4.1 Full regression run
```

## Phase 1: Database Layer

### 1.1 `EXPORT_SCHEMA_VERSION` Constant + `export_entities_json()` Method + Tests

**Design ref:** Component 1, Database Layer Interface
**Spec ref:** FR-2, FR-4, FR-5, FR-6
**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_database.py`

**Implementation:**
1. Add module-level constant `EXPORT_SCHEMA_VERSION = 1` near the existing export/migration section in `database.py`.
2. Add `export_entities_json(self, entity_type=None, status=None, include_lineage=True) -> dict` method to `EntityDatabase` class.
3. Entity type validation via existing `self._validate_entity_type(entity_type)` when entity_type is not None — raises `ValueError`.
4. Build SQL query conditionally (Python-conditional pattern matching `list_entities`): `SELECT uuid, type_id, entity_type, entity_id, name, status, artifact_path, parent_type_id, created_at, updated_at, metadata FROM entities` with optional WHERE clauses for entity_type and status, ORDER BY `created_at ASC, type_id ASC`.
5. Metadata normalization: `json.loads(row["metadata"])` with try/except `(json.JSONDecodeError, ValueError)` falling back to `{}`. NULL metadata also normalizes to `{}`.
6. Build entity dicts. When `include_lineage=True`, include `parent_type_id`; when False, omit it.
7. Assemble envelope: `schema_version` (from constant), `exported_at` (`datetime.now().astimezone().isoformat()` — local timezone, intentionally differs from `_now_iso()` which is UTC), `entity_count`, `filters_applied` dict, `entities` array.

**Tests (TDD — write first):**
- `TestExportEntitiesJson::test_no_filters_returns_all` — no args → all entities in response with correct envelope structure (AC-1)
- `TestExportEntitiesJson::test_entity_type_filter` — `entity_type="feature"` → only features (AC-2)
- `TestExportEntitiesJson::test_status_filter` — `status="completed"` → only completed entities (AC-3)
- `TestExportEntitiesJson::test_combined_filters` — both entity_type + status → AND logic (AC-4)
- `TestExportEntitiesJson::test_invalid_entity_type_raises` — `entity_type="invalid"` → ValueError with repr-quoted tuple format: `"Invalid entity_type 'invalid'. Must be one of ('backlog', ...)"` (AC-8)
- `TestExportEntitiesJson::test_unmatched_status_returns_empty` — status that matches nothing → `entity_count: 0`, empty entities array
- `TestExportEntitiesJson::test_empty_database` — no entities → valid envelope with `entity_count: 0` (AC-9)
- `TestExportEntitiesJson::test_schema_version` — returns `schema_version: 1` (FR-6)
- `TestExportEntitiesJson::test_exported_at_format` — ISO 8601 with timezone offset
- `TestExportEntitiesJson::test_filters_applied_in_envelope` — `filters_applied` contains only `entity_type` and `status` (including None values); explicitly assert `include_lineage` is NOT in `filters_applied`
- `TestExportEntitiesJson::test_uuid_in_entity` — each entity dict contains `uuid` field (AC-10)
- `TestExportEntitiesJson::test_include_lineage_true` — parent_type_id present in entity dicts
- `TestExportEntitiesJson::test_include_lineage_false` — parent_type_id absent from entity dicts (AC-7, AC-9 partial)
- `TestExportEntitiesJson::test_metadata_null_normalized` — NULL metadata → `{}` (AC-8)
- `TestExportEntitiesJson::test_metadata_valid_json` — valid JSON metadata → parsed dict
- `TestExportEntitiesJson::test_metadata_malformed_json` — malformed JSON → `{}` fallback
- `TestExportEntitiesJson::test_entity_ordering` — results ordered by created_at ASC, type_id ASC
- `TestExportEntitiesJson::test_all_entity_fields_present` — each entity has all expected keys (uuid, type_id, entity_type, entity_id, name, status, artifact_path, created_at, updated_at, metadata)
- `TestExportEntitiesJson::test_performance_1000_entities` — 1000 entities export completes within 5 seconds (AC-11). Use `db._conn.executemany()` for bulk insert during setup; time only the `export_entities_json()` call via `time.perf_counter()`, not the test setup

**Done when:** All `TestExportEntitiesJson` tests pass. Method returns correct envelope for all filter combinations.

## Phase 2: Helper Layer

### 2.1 `_process_export_entities()` Function + Tests

**Design ref:** Component 2, Server Helper Interface
**Spec ref:** FR-1, FR-3
**File:** `plugins/iflow/hooks/lib/entity_registry/server_helpers.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py`
**Depends on:** 1.1 (calls `db.export_entities_json()`)

**Implementation:**
1. Add `_process_export_entities(db, entity_type, status, output_path, include_lineage, artifacts_root) -> str` function.
2. Call `db.export_entities_json(entity_type, status, include_lineage)` wrapped in try/except `ValueError` → return `f"Error: {exc}"`.
3. If `output_path` is not None:
   - Resolve via existing `resolve_output_path(output_path, artifacts_root)` — returns None on path escape.
   - If resolved is None → return `"Error: output path escapes artifacts root"`.
   - Create parent directories via `os.makedirs(parent_dir, exist_ok=True)` (only if parent_dir is non-empty).
   - Write JSON with `json.dump(data, f, indent=2, ensure_ascii=False)` using UTF-8 encoding.
   - Catch `OSError` only (narrow scope per spec FR-3) → return `f"Error writing export: {exc}"`.
   - Return `f"Exported {data['entity_count']} entities to {resolved}"`.
4. If `output_path` is None → return `json.dumps(data, indent=2, ensure_ascii=False)`.
5. Import: `json` is already imported at line 8 of server_helpers.py. No new imports needed.

**Note:** The path escape check (`if resolved is None`) occurs BEFORE the file write attempt. This intentionally differs from the existing `_process_export_lineage_markdown` where the check occurs after the write block — this is a deliberate improvement to prevent any file I/O when the path is invalid.

**Tests (TDD — write first):**
- `TestProcessExportEntities::test_no_output_path_returns_json_string` — returns valid JSON string directly
- `TestProcessExportEntities::test_output_path_writes_file` — file created with valid JSON content, returns confirmation message (AC-4)
- `TestProcessExportEntities::test_output_path_creates_parent_dirs` — parent directories auto-created (AC-10)
- `TestProcessExportEntities::test_path_escape_returns_error` — `"../../etc/passwd"` → `"Error: output path escapes artifacts root"` (AC-6)
- `TestProcessExportEntities::test_oserror_returns_error_string` — permission denied → `"Error writing export: ..."` (FR-3)
- `TestProcessExportEntities::test_invalid_entity_type_returns_error` — ValueError from database → `"Error: Invalid entity_type 'xyz'. Must be one of ('backlog', ...)"` (helper prepends `"Error: "` prefix)
- `TestProcessExportEntities::test_json_encoding_utf8` — non-ASCII characters preserved in output
- `TestProcessExportEntities::test_json_indentation` — 2-space indentation in output
- `TestProcessExportEntities::test_include_lineage_forwarded` — `include_lineage=False` passed through to database method
- `TestProcessExportEntities::test_confirmation_message_format` — returns `"Exported {n} entities to {path}"` with correct count

**Error message format note:** Tests MUST assert the full error string including the `"Error: "` prefix prepended by the helper. The database layer's canonical format is `Invalid entity_type 'xyz'. Must be one of ('backlog', 'brainstorm', 'project', 'feature')` (repr-quoted, tuple parens). Do NOT test against spec FR-4's plain format.

**Done when:** All `TestProcessExportEntities` tests pass. File I/O, error handling, and JSON serialization work correctly.

## Phase 3: MCP Tool Layer

### 3.1 `export_entities` MCP Tool + Import Update + Tests

**Design ref:** Component 3, MCP Tool Interface, Import Changes
**Spec ref:** FR-1
**File:** `plugins/iflow/mcp/entity_server.py`
**Test file:** `plugins/iflow/mcp/test_export_entities.py` (**Created** — new Python pytest file. Note: `test_entity_server.sh` exists as a bash bootstrap wrapper test; this new file tests tool-level Python behavior.)
**Depends on:** 2.1 (delegates to `_process_export_entities`)

**Implementation:**
1. Update import in `entity_server.py` — add `_process_export_entities` to the import from `entity_registry.server_helpers`:
   ```python
   from entity_registry.server_helpers import (
       _process_export_lineage_markdown,
       _process_export_entities,       # new
       _process_get_lineage,
       _process_register_entity,
       parse_metadata,
   )
   ```
2. Add `export_entities` async function with `@mcp.tool()` decorator:
   - Parameters: `entity_type: str | None = None`, `status: str | None = None`, `output_path: str | None = None`, `include_lineage: bool = True`
   - `_db` null guard: return `"Error: database not initialized (server not started)"`
   - Delegate to `_process_export_entities(_db, entity_type, status, output_path, include_lineage, _artifacts_root)`
3. Add docstring per design interface specification.

**Test mechanism:** Tests import `entity_server` module, patch module-level globals (`_db`, `_artifacts_root`), and call the `export_entities` async function directly via `asyncio.run()` or pytest-asyncio. This follows the same pattern used in `test_search_mcp.py` for feature 012.

**Tests (TDD — write first):**
- `TestExportEntitiesTool::test_db_not_initialized` — set `entity_server._db = None`, call `export_entities()` → returns `"Error: database not initialized (server not started)"` (null guard)
- `TestExportEntitiesTool::test_delegates_to_helper` — patch `_process_export_entities` via `unittest.mock.patch`, set `entity_server._db` to a mock, call `export_entities(entity_type="feature", status="active", include_lineage=False)`, assert patch called with `(mock_db, "feature", "active", None, False, mock_artifacts_root)`
- `TestExportEntitiesTool::test_include_lineage_default_true` — call `export_entities()` with no args, assert `_process_export_entities` called with `include_lineage=True`
- `TestExportEntitiesTool::test_returns_helper_result` — patch `_process_export_entities` to return a string, verify `export_entities()` returns that exact string

**Done when:** All `TestExportEntitiesTool` tests pass. Tool delegates correctly with proper argument forwarding.

## Phase 4: Final Regression

### 4.1 Full Regression Run

**Spec ref:** AC-5
**Depends on:** All previous phases

**Implementation:**
1. Run full existing entity registry test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
2. Verify all existing tests still pass (AC-5 — no regression to existing MCP tools).
3. Run entity server bootstrap tests: `bash plugins/iflow/mcp/test_entity_server.sh`
4. Verify zero test failures across all suites.

**Done when:** All existing and new tests pass. Zero failures.

## Dependency Graph

```
1.1 (EXPORT_SCHEMA_VERSION + export_entities_json)
 └──→ 2.1 (_process_export_entities)
       └──→ 3.1 (export_entities MCP tool + import)
4.1 (full regression) ← runs after all phases
```

**Parallelism:** All steps are sequential — each phase depends on the previous. No parallel groups.

## Files Changed Summary

| File | Action | Phase |
|------|--------|-------|
| `plugins/iflow/hooks/lib/entity_registry/database.py` | Modified — add constant + method | 1.1 |
| `plugins/iflow/hooks/lib/entity_registry/test_database.py` | Modified — add export tests | 1.1 |
| `plugins/iflow/hooks/lib/entity_registry/server_helpers.py` | Modified — add function | 2.1 |
| `plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py` | Modified — add export helper tests | 2.1 |
| `plugins/iflow/mcp/entity_server.py` | Modified — add tool + update import | 3.1 |
| `plugins/iflow/mcp/test_export_entities.py` | **Created** — MCP tool unit tests | 3.1 |

## AC Coverage Matrix

| AC | Phase | Test |
|----|-------|------|
| AC-1 | 1.1 | TestExportEntitiesJson::test_no_filters_returns_all |
| AC-2 | 1.1 | TestExportEntitiesJson::test_entity_type_filter |
| AC-3 | 1.1 | TestExportEntitiesJson::test_combined_filters (database layer — MCP tool is thin pass-through) |
| AC-4 | 2.1 | TestProcessExportEntities::test_output_path_writes_file |
| AC-5 | 4.1 | Full regression run |
| AC-6 | 2.1 | TestProcessExportEntities::test_path_escape_returns_error |
| AC-7 | 1.1 | TestExportEntitiesJson::test_include_lineage_false |
| AC-8 | 1.1 | TestExportEntitiesJson::test_metadata_null_normalized |
| AC-9 | 1.1 | TestExportEntitiesJson::test_empty_database |
| AC-10 | 1.1, 2.1 | TestExportEntitiesJson::test_uuid_in_entity, TestProcessExportEntities::test_output_path_creates_parent_dirs |
| AC-11 | 1.1 | TestExportEntitiesJson::test_performance_1000_entities |
