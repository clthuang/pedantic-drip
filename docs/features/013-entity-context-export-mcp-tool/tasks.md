# Tasks: Entity Export MCP Tool

## Phase 1: Database Layer

### Task 1.1.1: Write TDD tests for `export_entities_json()` (RED)

- [ ] Write all `TestExportEntitiesJson` tests in `test_database.py`

**File:** `plugins/iflow/hooks/lib/entity_registry/test_database.py`
**Depends on:** None
**Done when:** All 19 tests exist and fail (RED) because `export_entities_json()` and `EXPORT_SCHEMA_VERSION` do not exist yet.

Tests to write:
1. `test_no_filters_returns_all` — no args → all entities with correct envelope (AC-1)
2. `test_entity_type_filter` — `entity_type="feature"` → only features (AC-2)
3. `test_status_filter` — `status="completed"` → only completed
4. `test_combined_filters` — entity_type + status → AND logic (AC-3)
5. `test_invalid_entity_type_raises` — `entity_type="invalid"` → `pytest.raises(ValueError, match=r"Invalid entity_type 'invalid'. Must be one of \('backlog',")` (ValueError path — spec FR-4). Exact database format: `Invalid entity_type 'invalid'. Must be one of ('backlog', 'brainstorm', 'project', 'feature')`
6. `test_unmatched_status_returns_empty` — unmatched status → entity_count: 0
7. `test_empty_database` — no entities → valid envelope with entity_count: 0 (AC-9)
8. `test_schema_version` — returns schema_version: 1 (FR-6)
9. `test_exported_at_format` — ISO 8601 with timezone offset
10. `test_filters_applied_in_envelope` — filters_applied contains entity_type and status; include_lineage NOT in filters_applied
11. `test_uuid_in_entity` — each entity has uuid field (AC-10)
12. `test_include_lineage_true` — parent_type_id present
13. `test_include_lineage_false` — parent_type_id absent (AC-7)
14. `test_metadata_null_normalized` — NULL metadata → {} (AC-8)
15. `test_metadata_valid_json` — valid JSON → parsed dict
16. `test_metadata_malformed_json` — malformed JSON → {} fallback
17. `test_entity_ordering` — ordered by created_at ASC, type_id ASC
18. `test_all_entity_fields_present` — each entity has all expected keys
19. `test_performance_1000_entities` — 1000 entities < 5 seconds (AC-11)

### Task 1.1.2: Implement `EXPORT_SCHEMA_VERSION` and `export_entities_json()` (GREEN)

- [ ] Add `EXPORT_SCHEMA_VERSION = 1` constant and `export_entities_json()` method to `database.py`

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
**Depends on:** 1.1.1
**Done when:** All 19 `TestExportEntitiesJson` tests pass (GREEN).

Implementation steps:
1. Add `EXPORT_SCHEMA_VERSION = 1` at module level near the export section
2. Add `export_entities_json(self, entity_type=None, status=None, include_lineage=True)` method
3. Validate entity_type via `self._validate_entity_type()` when not None
4. Build SQL with Python-conditional WHERE clauses (matching `list_entities` pattern)
5. ORDER BY `created_at ASC, type_id ASC`
6. Normalize metadata: `json.loads()` with try/except `(json.JSONDecodeError, ValueError)` → `{}`; NULL → `{}`
7. Conditionally include `parent_type_id` based on `include_lineage`
8. Assemble envelope with `datetime.now().astimezone().isoformat()` for `exported_at`

## Phase 2: Helper Layer

### Task 2.1.1: Write TDD tests for `_process_export_entities()` (RED)

- [ ] Write all `TestProcessExportEntities` tests in `test_server_helpers.py`

**File:** `plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py`
**Depends on:** 1.1.2
**Done when:** All 10 tests exist and fail (RED) because `_process_export_entities()` does not exist yet.

Tests to write:
1. `test_no_output_path_returns_json_string` — returns valid JSON string directly
2. `test_output_path_writes_file` — file created with valid JSON, returns confirmation (AC-4)
3. `test_output_path_creates_parent_dirs` — parent directories auto-created (AC-10)
4. `test_path_escape_returns_error` — `"../../etc/passwd"` → error about path escape (AC-6)
5. `test_oserror_returns_error_string` — permission denied → `"Error writing export: ..."` (FR-3)
6. `test_invalid_entity_type_returns_error` — ValueError → `"Error: Invalid entity_type 'xyz'. Must be one of ('backlog', ...)"` (helper prepends `"Error: "` prefix)
7. `test_json_encoding_utf8` — non-ASCII characters preserved
8. `test_json_indentation` — 2-space indentation
9. `test_include_lineage_forwarded` — `include_lineage=False` passed through to database method
10. `test_confirmation_message_format` — returns `"Exported {n} entities to {path}"`

Error message format: Tests MUST assert the full error string including `"Error: "` prefix. Database format is authoritative: `Invalid entity_type 'xyz'. Must be one of ('backlog', 'brainstorm', 'project', 'feature')`.

### Task 2.1.2: Implement `_process_export_entities()` (GREEN)

- [ ] Add `_process_export_entities()` function to `server_helpers.py`

**File:** `plugins/iflow/hooks/lib/entity_registry/server_helpers.py`
**Depends on:** 2.1.1
**Done when:** All 10 `TestProcessExportEntities` tests pass (GREEN).

Implementation steps:
1. Add `_process_export_entities(db, entity_type, status, output_path, include_lineage, artifacts_root)` function
2. Call `db.export_entities_json()` wrapped in try/except `ValueError` → `f"Error: {exc}"`
3. If `output_path` not None: resolve via `resolve_output_path()`, check for None (path escape), create parent dirs, write JSON with `json.dump(data, f, indent=2, ensure_ascii=False)`, catch `OSError`
4. Path escape check occurs BEFORE file write (intentional improvement over `_process_export_lineage_markdown`)
5. If `output_path` is None: return `json.dumps(data, indent=2, ensure_ascii=False)`
6. No new imports needed — `json` already imported at line 8

## Phase 3: MCP Tool Layer

### Task 3.1.1: Write TDD tests for `export_entities` MCP tool (RED)

- [ ] Create `test_export_entities.py` with all `TestExportEntitiesTool` tests

**File:** `plugins/iflow/mcp/test_export_entities.py` (**Created** — new Python pytest file. Intentionally renamed from design's `test_entity_server.py` to avoid confusion with the bash wrapper and to follow `test_search_mcp.py` per-feature naming convention.)
**Depends on:** 2.1.2
**Done when:** All 4 tests exist and fail (RED) because `export_entities` tool does not exist yet.

**Test mechanism:** Import `entity_server` module, patch module-level globals (`_db`, `_artifacts_root`), call async function directly via `asyncio.run()` or pytest-asyncio. Follows pattern from `test_search_mcp.py`. Include the same `sys.path` bootstrap from `test_search_mcp.py` (lines 12-16) before `import entity_server` to make the module importable when running from the project root.

**Test independence note:** Each test independently sets `entity_server._db` (to None or a mock), so test execution order does not matter. No shared fixture cleanup needed.

Tests to write:
1. `test_db_not_initialized` — set `entity_server._db = None`, call `export_entities()` → `"Error: database not initialized (server not started)"`
2. `test_delegates_to_helper` — `unittest.mock.patch("entity_server._process_export_entities")` (patch at usage site, not definition site), set `entity_server._db` to a mock, call `export_entities(entity_type="feature", status="active", include_lineage=False)`, assert called with `(mock_db, "feature", "active", None, False, mock_artifacts_root)`
3. `test_include_lineage_default_true` — patch `entity_server._process_export_entities`, call `export_entities()` with no args, assert called with `include_lineage=True`
4. `test_returns_helper_result` — patch `entity_server._process_export_entities` to return a string, verify `export_entities()` returns that exact string

### Task 3.1.2: Implement `export_entities` MCP tool and update imports (GREEN)

- [ ] Add `export_entities` tool to `entity_server.py` and update import statement

**File:** `plugins/iflow/mcp/entity_server.py`
**Depends on:** 3.1.1
**Done when:** All 4 `TestExportEntitiesTool` tests pass (GREEN).

Implementation steps:
1. Update import: add `_process_export_entities` to the import from `entity_registry.server_helpers`
2. Add `export_entities` async function with `@mcp.tool()` decorator
3. Parameters: `entity_type: str | None = None`, `status: str | None = None`, `output_path: str | None = None`, `include_lineage: bool = True`
4. `_db` null guard → return error string
5. Delegate to `_process_export_entities(_db, entity_type, status, output_path, include_lineage, _artifacts_root)`
6. Add docstring per design interface specification

## Phase 4: Final Regression

### Task 4.1.1: Run full regression test suite

- [ ] Run all existing and new test suites, verify zero failures

**Depends on:** 3.1.2
**Done when:** All tests in steps 1-3 below pass with zero failures (AC-5).

Steps:
1. Run entity registry test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
2. Run new MCP tool tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_export_entities.py -v`
3. Run entity server bootstrap tests: `bash plugins/iflow/mcp/test_entity_server.sh`
4. Verify zero failures across all suites

## Dependency Graph

```
1.1.1 (tests RED) → 1.1.2 (implement GREEN)
                       ↓
                     2.1.1 (tests RED) → 2.1.2 (implement GREEN)
                                            ↓
                                          3.1.1 (tests RED) → 3.1.2 (implement GREEN)
                                                                 ↓
                                                               4.1.1 (regression)
```

**Parallelism:** All tasks are sequential — each depends on the previous. No parallel groups.

## Files Changed Summary

| File | Action | Task |
|------|--------|------|
| `plugins/iflow/hooks/lib/entity_registry/test_database.py` | Modified — add 19 export tests | 1.1.1 |
| `plugins/iflow/hooks/lib/entity_registry/database.py` | Modified — add constant + method | 1.1.2 |
| `plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py` | Modified — add 10 helper tests | 2.1.1 |
| `plugins/iflow/hooks/lib/entity_registry/server_helpers.py` | Modified — add function | 2.1.2 |
| `plugins/iflow/mcp/test_export_entities.py` | **Created** — 4 MCP tool tests | 3.1.1 |
| `plugins/iflow/mcp/entity_server.py` | Modified — add tool + update import | 3.1.2 |

## AC Coverage Matrix

| AC | Task | Test |
|----|------|------|
| AC-1 | 1.1.1 | test_no_filters_returns_all |
| AC-2 | 1.1.1 | test_entity_type_filter |
| AC-3 | 1.1.1 | test_combined_filters |
| AC-4 | 2.1.1 | test_output_path_writes_file |
| AC-5 | 4.1.1 | Full regression run |
| AC-6 | 2.1.1 | test_path_escape_returns_error |
| AC-7 | 1.1.1 | test_include_lineage_false |
| AC-8 | 1.1.1 | test_metadata_null_normalized |
| AC-9 | 1.1.1 | test_empty_database |
| AC-10 | 1.1.1 | test_uuid_in_entity |
| AC-11 | 1.1.1 | test_performance_1000_entities |
