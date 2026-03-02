# Plan: Bidirectional UUID Sync Between Files and DB

## Implementation Order

The plan follows TDD order: tests are written alongside each phase. Each phase produces a testable unit before the next begins.

### Dependency Graph

```
Phase 1: Foundation (no deps)
  ├── C1: Dataclasses + constants
  └── database.py: list_entities()
         │
Phase 2: Internal Helpers (depends on Phase 1)
  ├── _derive_optional_fields()
  └── _derive_feature_directory()
         │
Phase 3: Core Functions (depends on Phases 1-2)
  ├── detect_drift()
  ├── stamp_header()
  └── ingest_header()
         │
Phase 4: Bulk Functions (depends on Phases 1-3; uses ARTIFACT_BASENAME_MAP from Phase 1.2)
  ├── backfill_headers()
  └── scan_all()
         │
Phase 5: Integration (depends on Phase 4)
  ├── backfill.py modification
  └── frontmatter_sync_cli.py
```

## Phase 1: Foundation

### 1.1 Add `list_entities()` to `database.py`

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
**Scope:** ~10 lines — new public method on `EntityDatabase`
**Tests:** Add tests to existing `test_database.py`

**Sub-step 1.1a: Write tests first in `test_database.py` (expect failures):**

```
Tests (TDD — RED phase):
  - test_list_entities_returns_all: register 3 entities, list_entities() returns 3
  - test_list_entities_filter_by_type: register feature + project, list_entities("feature") returns 1
  - test_list_entities_empty_db: returns []
  - test_list_entities_unknown_type: returns []
```

**Sub-step 1.1b: Implement in `database.py` (tests pass — GREEN phase):**

```
Implementation:
  1. Add list_entities(self, entity_type=None) -> list[dict] method
  2. If entity_type is None: SELECT * FROM entities
  3. If entity_type provided: SELECT * FROM entities WHERE entity_type = ?
  4. Return list of dicts with same keys as get_entity
  5. Return empty list if no matches
```

**AC coverage:** None directly — enables C5/C6 per design R1.

### 1.2 Create `frontmatter_sync.py` with dataclasses and constants

**File:** `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync.py`
**Scope:** ~40 lines — dataclasses + module-level constants
**Tests:** Begin `test_frontmatter_sync.py` with dataclass construction tests

```
Implementation:
  1. Imports: dataclasses, json, os, logging
  2. Import from frontmatter: read_frontmatter, write_frontmatter, build_header, validate_header, FrontmatterUUIDMismatch
     Note: validate_header imported per spec R2 — called internally by build_header, but imported for spec compliance
  3. Import from frontmatter_inject: _parse_feature_type_id, ARTIFACT_BASENAME_MAP, ARTIFACT_PHASE_MAP
  4. Import from database: EntityDatabase
  5. Define COMPARABLE_FIELD_MAP = {"entity_uuid": "uuid", "entity_type_id": "type_id"}
  6. Define 4 dataclasses: FieldMismatch, DriftReport, StampResult, IngestResult

Tests (TDD — write first):
  - test_field_mismatch_construction: verify fields accessible
  - test_drift_report_construction: verify all 6 fields
  - test_stamp_result_construction: verify 3 fields
  - test_ingest_result_construction: verify 3 fields
  - test_comparable_field_map_content: verify exactly 2 entries
  - test_module_imports_resolve: import frontmatter_sync, assert COMPARABLE_FIELD_MAP, ARTIFACT_BASENAME_MAP, ARTIFACT_PHASE_MAP exist
    Note: catches import path errors at Phase 1.2 boundary rather than deferring to Phase 2.1+
```

**AC coverage:** Foundation for all ACs.

## Phase 2: Internal Helpers

### 2.1 Implement `_derive_optional_fields()`

**File:** `frontmatter_sync.py`
**Scope:** ~30 lines
**Tests:** Add to `test_frontmatter_sync.py`

```
Implementation (per design TD-2):
  1. Parse entity type from type_id
  2. If feature: extract feature_id + feature_slug via _parse_feature_type_id
  3. project_id: metadata JSON first, parent_type_id fallback
  4. phase: from ARTIFACT_PHASE_MAP
  5. Return dict of optional fields

Tests (TDD — write first):
  - test_derive_feature_entity: feature type_id → feature_id, feature_slug, phase
  - test_derive_project_id_from_metadata: metadata JSON with project_id
  - test_derive_project_id_from_parent: parent_type_id="project:P001" → "P001"
  - test_derive_metadata_priority: metadata wins over parent_type_id
  - test_derive_non_feature_entity: project type_id → no feature_id/feature_slug
  - test_derive_malformed_metadata: invalid JSON → falls back to parent_type_id
  - test_derive_no_project_id: neither source → no project_id in result
```

**AC coverage:** AC-6a (metadata project_id derivation).

### 2.2 Implement `_derive_feature_directory()`

**File:** `frontmatter_sync.py`
**Scope:** ~15 lines
**Tests:** Add to `test_frontmatter_sync.py`

```
Implementation (per design TD-3):
  1. Check artifact_path isdir → return
  2. Check artifact_path isfile → return dirname
  3. Construct from entity_id → check isdir → return
  4. Return None

Tests (TDD — write first):
  - test_derive_dir_from_artifact_path_dir: artifact_path is a directory
  - test_derive_dir_from_artifact_path_file: artifact_path is a file → dirname
  - test_derive_dir_from_entity_id: no artifact_path, construct from entity_id
    Setup: pass artifacts_root=str(tmp_path), create {tmp_path}/features/{entity_id}/ directory before calling
  - test_derive_dir_none: no artifact_path, constructed path doesn't exist → None
    Setup: do NOT create directory — os.path.isdir check should fail
```

**AC coverage:** Enables AC-14, AC-15 (backfill directory resolution).

## Phase 3: Core Functions

### 3.1 Implement `detect_drift()`

**File:** `frontmatter_sync.py`
**Scope:** ~40 lines
**Tests:** Add to `test_frontmatter_sync.py`

```
Implementation (per design C2):
  1. Read frontmatter
  2. Determine lookup_key (type_id → header.entity_uuid → no_header)
  3. Look up entity
  4. Branch on header/entity presence → status
  5. Compare COMPARABLE_FIELD_MAP fields (uuid: case-insensitive, type_id: case-sensitive)
  6. Catch broad Exception → status="error" (per design TD-4 never-raise contract)

Tests (TDD — write first):
  - test_drift_in_sync: matching header and DB → "in_sync" (AC-1)
  - test_drift_file_only: header with UUID, no DB record → "file_only" (AC-2)
  - test_drift_db_only: no header, type_id provided, DB record exists → "db_only" (AC-3)
  - test_drift_diverged_type_id: header type_id != DB type_id → "diverged" + FieldMismatch (AC-4)
  - test_drift_no_header: no header, no type_id → "no_header" (AC-5)
  - test_drift_header_no_uuid_no_type_id: header without entity_uuid, no type_id → "no_header"
  - test_drift_type_id_different_uuid: type_id provided, file has different UUID → "diverged"
  - test_drift_db_error: DB raises generic Exception (e.g., RuntimeError) → "error" (tests broad except per TD-4)
```

**AC coverage:** AC-1, AC-2, AC-3, AC-4, AC-5.

### 3.2 Implement `stamp_header()`

**File:** `frontmatter_sync.py`
**Scope:** ~50 lines
**Tests:** Add to `test_frontmatter_sync.py`

```
Implementation (per design C3):
  1. Get entity from DB
  2. Extract required fields
  3. Derive optional fields via _derive_optional_fields
  4-7. Single try/except: build_header → read existing → UUID check → write_frontmatter
  8. Return created/updated

Tests (TDD — write first):
  - test_stamp_creates_header: no existing frontmatter → "created" (AC-6)
    Assert: header["created_at"] == db_entity["created_at"] (DB-authoritative, NOT datetime.now())
  - test_stamp_with_project_id_from_metadata: metadata project_id in header (AC-6a)
  - test_stamp_updates_header: existing matching header → "updated" (AC-7)
    Note: created_at preserves file's original value on update (write_frontmatter merge semantics), not the DB value
  - test_stamp_mismatch_error: existing different UUID → "error" (AC-8)
  - test_stamp_entity_not_found: bad type_id → "error" (AC-9)
  - test_stamp_preserves_body: body content unchanged after stamp (AC-10)
  - test_stamp_header_no_uuid_in_existing: existing header without entity_uuid → "created"
  - test_stamp_build_header_error: invalid artifact_type → "error" via ValueError
```

**AC coverage:** AC-6, AC-6a, AC-7, AC-8, AC-9, AC-10.

### 3.3 Implement `ingest_header()`

**File:** `frontmatter_sync.py`
**Scope:** ~25 lines
**Tests:** Add to `test_frontmatter_sync.py`

```
Implementation (per design C4):
  1. Read frontmatter
  2. Extract entity_uuid
  3. Look up entity in DB
  4. Update artifact_path via db.update_entity
  5. try/except ValueError around step 4: entity deleted between check and update → return error("Entity disappeared")

Tests (TDD — write first):
  - test_ingest_updates_path: valid header → "updated", artifact_path set (AC-11)
    Assert: DB entity's artifact_path updated; passes UUID to update_entity (validates _resolve_identifier UUID path)
  - test_ingest_no_frontmatter: no header → "skipped" (AC-12)
  - test_ingest_entity_not_found: UUID not in DB → "error" (AC-13)
  - test_ingest_no_uuid_in_header: header without entity_uuid → "skipped"
  - test_ingest_race_condition: entity deleted between check and update → "error"
```

**AC coverage:** AC-11, AC-12, AC-13.

## Phase 4: Bulk Functions

### 4.1 Implement `backfill_headers()`

**File:** `frontmatter_sync.py`
**Scope:** ~40 lines
**Tests:** Add to `test_frontmatter_sync.py`

```
Implementation (per design C5):
  1. Query db.list_entities(entity_type="feature")
  2. For each entity: derive directory, scan for artifact files
  3. For each file: try stamp_header; on unexpected Exception → error StampResult for that file, continue
     Note: defensive try/except around individual stamp calls ensures bulk operation never aborts on single failure

Tests (TDD — write first):
  - test_backfill_stamps_all: 3 features × 2 files = 6 stamps (AC-14)
  - test_backfill_idempotent: run twice → identical content (AC-15)
  - test_backfill_skips_mismatch: mismatched UUID → error in results (AC-16)
  - test_backfill_skips_missing_dir: entity with no directory → "skipped"
  - test_backfill_empty_db: no features → empty list
```

**AC coverage:** AC-14, AC-15, AC-16.

### 4.2 Implement `scan_all()`

**File:** `frontmatter_sync.py`
**Scope:** ~25 lines
**Tests:** Add to `test_frontmatter_sync.py`

```
Implementation (per design C6):
  1. Same as backfill_headers but calls detect_drift instead of stamp_header

Tests (TDD — write first):
  - test_scan_mixed_statuses: headers + no headers → mixed results (AC-17)
  - test_scan_empty_db: no features → empty list
```

**AC coverage:** AC-17.

## Phase 5: Integration

### 5.1 Modify `backfill.py`

**File:** `plugins/iflow/hooks/lib/entity_registry/backfill.py`
**Scope:** ~5 lines — add `header_aware` parameter
**Tests:** Add to `test_frontmatter_sync.py` (integration section)

```
Implementation (per design C7/TD-7):
  1. Add header_aware=False parameter to run_backfill
  2. If header_aware: lazy import + call backfill_headers BEFORE guard
  3. Existing logic unchanged

Tests (TDD — write first):
  - test_backfill_header_aware_true: stamps headers even after backfill_complete (AC-18)
    Note: requires Phases 1-4 complete (frontmatter_sync.py must be fully importable).
    Write test stub with pytest.mark.skip until Phase 4.2 is complete; remove skip marker as final step of Phase 5.1.
  - test_backfill_header_aware_false: no headers stamped — backward compat (AC-19)
```

**AC coverage:** AC-18, AC-19.

### 5.2 Create `frontmatter_sync_cli.py`

**File:** `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync_cli.py`
**Scope:** ~100 lines
**Tests:** Add CLI integration tests to `test_frontmatter_sync.py`

```
Implementation (per design C8/TD-5/TD-6):
  1. argparse with 5 subcommands: drift, stamp, ingest, backfill, scan
  2. _open_db(): ENTITY_DB_PATH env var → fallback
  3. _run_handler(func): shared DB lifecycle wrapper
  4. Each handler: closure over args, prints JSON via dataclasses.asdict + json.dumps

Tests (TDD — write first via subprocess.run):
  - test_cli_drift: outputs valid JSON with status field (AC-20)
  - test_cli_backfill: stamps and outputs JSON summary (AC-21)
  - test_cli_scan: outputs JSON array of drift reports (AC-22)
  - test_cli_db_error: invalid DB path → JSON error, exit code 1
  - test_cli_bad_args: missing args → exit code non-zero
```

**AC coverage:** AC-20, AC-21, AC-22.

### 5.3 Error handling verification

**Tests only** — no new implementation, tests verify TD-4 behavior:

```
Tests:
  - test_detect_drift_db_unavailable: DB connection error → "error" result (AC-23)
  - test_stamp_header_db_unavailable: DB connection error → "error" result (AC-23)
  - test_ingest_header_db_unavailable: DB connection error → "error" result (AC-23)
  - test_detect_drift_missing_file: file not found → "no_header" (AC-24)
  - test_stamp_header_missing_file: precondition failure → "error" (AC-24)
  - test_ingest_header_missing_file: no frontmatter → "skipped" (AC-24)
```

**AC coverage:** AC-23, AC-24.

## AC Coverage Matrix

| AC | Phase | Test |
|----|-------|------|
| AC-1 | 3.1 | test_drift_in_sync |
| AC-2 | 3.1 | test_drift_file_only |
| AC-3 | 3.1 | test_drift_db_only |
| AC-4 | 3.1 | test_drift_diverged_type_id |
| AC-5 | 3.1 | test_drift_no_header |
| AC-6 | 3.2 | test_stamp_creates_header |
| AC-6a | 3.2 | test_stamp_with_project_id_from_metadata |
| AC-7 | 3.2 | test_stamp_updates_header |
| AC-8 | 3.2 | test_stamp_mismatch_error |
| AC-9 | 3.2 | test_stamp_entity_not_found |
| AC-10 | 3.2 | test_stamp_preserves_body |
| AC-11 | 3.3 | test_ingest_updates_path |
| AC-12 | 3.3 | test_ingest_no_frontmatter |
| AC-13 | 3.3 | test_ingest_entity_not_found |
| AC-14 | 4.1 | test_backfill_stamps_all |
| AC-15 | 4.1 | test_backfill_idempotent |
| AC-16 | 4.1 | test_backfill_skips_mismatch |
| AC-17 | 4.2 | test_scan_mixed_statuses |
| AC-18 | 5.1 | test_backfill_header_aware_true |
| AC-19 | 5.1 | test_backfill_header_aware_false |
| AC-20 | 5.2 | test_cli_drift |
| AC-21 | 5.2 | test_cli_backfill |
| AC-22 | 5.2 | test_cli_scan |
| AC-23 | 5.3 | test_*_db_unavailable (3 tests) |
| AC-24 | 5.3 | test_*_missing_file (3 tests) |

All 24 ACs covered. Total: ~45 test functions across ~400 lines.

## File Impact Summary

| File | Phase | Action |
|------|-------|--------|
| `entity_registry/database.py` | 1.1 | Modify (+10 lines) |
| `entity_registry/frontmatter_sync.py` | 1.2-4.2 | Create (~200 lines) |
| `entity_registry/frontmatter_sync_cli.py` | 5.2 | Create (~100 lines) |
| `entity_registry/test_frontmatter_sync.py` | 1.2-5.3 | Create (~400 lines) |
| `entity_registry/backfill.py` | 5.1 | Modify (+5 lines) |

## Risk Mitigations

- **list_entities missing:** Phase 1.1 adds it first — all downstream phases depend on it.
- **Import breakage from frontmatter_inject:** Phase 1.2 imports immediately — fails fast if API changed.
- **Concurrent access:** No mitigation needed per design R3. Tests use isolated in-memory DBs.
- **Scale:** Phase 4.1 test with 3 features validates the pattern; real-world ~50 features at ~5s is acceptable per design R4.
