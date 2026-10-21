# Tasks: Bidirectional UUID Sync Between Files and DB

## Phase 1: Foundation

### Task 1.1a: Write list_entities() tests [RED]
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Depends on:** nothing
- **Parallel group:** P1
- **Complexity:** Simple
- **Steps:**
  1. Add 4 test functions to existing `test_database.py`:
     - `test_list_entities_returns_all`: register 3 entities, assert list_entities() returns 3
     - `test_list_entities_filter_by_type`: register feature + project, assert list_entities("feature") returns 1
     - `test_list_entities_empty_db`: assert returns []
     - `test_list_entities_unknown_type`: assert returns []
  2. Run tests — confirm all 4 FAIL (method does not exist yet)
- **Done when:** 4 tests exist and all fail with `AttributeError`

### Task 1.1b: Implement list_entities() [GREEN]
- **File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
- **Depends on:** 1.1a
- **Parallel group:** —
- **Complexity:** Simple
- **Steps:**
  1. Add `list_entities(self, entity_type=None) -> list[dict]` method to `EntityDatabase`
  2. If entity_type is None: `SELECT * FROM entities`
  3. If entity_type provided: `SELECT * FROM entities WHERE entity_type = ?`
  4. Return list of dicts with same keys as `get_entity` — `cursor.fetchall()` returns `[]` naturally on no matches (no None handling needed)
  5. Run tests — confirm all 4 pass
- **Done when:** All 4 tests from 1.1a pass

### Task 1.2a: Write dataclass and constant tests [RED]
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`
- **Depends on:** nothing
- **Parallel group:** P1
- **Complexity:** Simple
- **Steps:**
  1. Create `test_frontmatter_sync.py` with 6 tests:
     - `test_field_mismatch_construction`: FieldMismatch(field="entity_uuid", file_value="abc", db_value="xyz") — verify all 3 fields accessible (spec R4: field, file_value, db_value)
     - `test_drift_report_construction`: DriftReport with 6 fields — verify all accessible
     - `test_stamp_result_construction`: StampResult with 3 fields — verify all accessible
     - `test_ingest_result_construction`: IngestResult with 3 fields — verify all accessible
     - `test_comparable_field_map_content`: assert exactly 2 entries in COMPARABLE_FIELD_MAP
     - `test_module_imports_resolve`: import frontmatter_sync, assert COMPARABLE_FIELD_MAP, ARTIFACT_BASENAME_MAP, ARTIFACT_PHASE_MAP exist
  2. Run tests — confirm all 6 FAIL (module does not exist yet)
- **Done when:** 6 tests exist and all fail with `ImportError`/`ModuleNotFoundError`

### Task 1.2b: Create frontmatter_sync.py with dataclasses and constants [GREEN]
- **File:** `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync.py`
- **Depends on:** 1.2a
- **Parallel group:** —
- **Complexity:** Simple
- **Steps:**
  1. Create `frontmatter_sync.py` with imports:
     - `dataclasses`, `json`, `os`, `logging`
     - From `frontmatter`: `read_frontmatter`, `write_frontmatter`, `build_header`, `validate_header`, `FrontmatterUUIDMismatch`
     - From `frontmatter_inject`: `_parse_feature_type_id`, `ARTIFACT_BASENAME_MAP`, `ARTIFACT_PHASE_MAP`
     - From `database`: `EntityDatabase`
  2. Define `COMPARABLE_FIELD_MAP = {"entity_uuid": "uuid", "entity_type_id": "type_id"}`
  3. Define 4 dataclasses: `FieldMismatch`, `DriftReport`, `StampResult`, `IngestResult`
  4. Run tests — confirm all 6 pass
- **Done when:** All 6 tests from 1.2a pass

## Phase 2: Internal Helpers

### Task 2.1a: Write _derive_optional_fields() tests [RED]
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`
- **Depends on:** 1.2b
- **Parallel group:** P2
- **Complexity:** Medium
- **Steps:**
  1. Add 7 tests to `test_frontmatter_sync.py` — all call `_derive_optional_fields(entity, artifact_type)`:
     - `test_derive_feature_entity`: feature type_id, `artifact_type="spec"` → result has feature_id, feature_slug, phase
     - `test_derive_project_id_from_metadata`: entity with `metadata='{"project_id": "P001"}'` (JSON string, not dict), `artifact_type="spec"` → result has project_id="P001"
     - `test_derive_project_id_from_parent`: parent_type_id="project:P001", `artifact_type="spec"` → result project_id="P001"
     - `test_derive_metadata_priority`: both metadata JSON and parent_type_id → metadata wins
     - `test_derive_non_feature_entity`: project type_id, `artifact_type="spec"` → no feature_id/feature_slug in result
     - `test_derive_malformed_metadata`: invalid JSON string → falls back to parent_type_id
     - `test_derive_no_project_id`: neither metadata nor parent → no project_id key in result
  2. Run tests — confirm all 7 FAIL
- **Done when:** 7 tests exist and all fail with `AttributeError` or `ImportError`

### Task 2.1b: Implement _derive_optional_fields() [GREEN]
- **File:** `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync.py`
- **Depends on:** 2.1a
- **Parallel group:** —
- **Complexity:** Medium
- **Steps:**
  1. Add `_derive_optional_fields(entity: dict, artifact_type: str) -> dict` function (per design TD-2)
  2. Parse entity type from type_id
  3. If feature: extract feature_id + feature_slug via `_parse_feature_type_id`
  4. project_id: try `json.loads(entity["metadata"])` first, then `parent_type_id` fallback
  5. phase: from `ARTIFACT_PHASE_MAP.get(artifact_type)`
  6. Return dict of optional fields
  7. Run tests — confirm all 7 pass
- **Done when:** All 7 tests from 2.1a pass

### Task 2.2a: Write _derive_feature_directory() tests [RED]
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`
- **Depends on:** 1.2b
- **Parallel group:** P2
- **Complexity:** Simple
- **Steps:**
  1. Add 4 tests to `test_frontmatter_sync.py`:
     - `test_derive_dir_from_artifact_path_dir`: artifact_path is a directory → returns it
     - `test_derive_dir_from_artifact_path_file`: artifact_path is a file → returns dirname
     - `test_derive_dir_from_entity_id`: no artifact_path, entity with `entity_id="003-my-feature"`, `artifacts_root=str(tmp_path)`, create `{tmp_path}/features/003-my-feature/` directory → returns that path
     - `test_derive_dir_none`: no artifact_path, constructed path doesn't exist (do NOT create directory) → returns None
  2. Run tests — confirm all 4 FAIL
- **Done when:** 4 tests exist and all fail

### Task 2.2b: Implement _derive_feature_directory() [GREEN]
- **File:** `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync.py`
- **Depends on:** 2.2a
- **Parallel group:** —
- **Complexity:** Simple
- **Steps:**
  1. Add `_derive_feature_directory(entity: dict, artifacts_root: str) -> str | None`
  2. Check artifact_path isdir → return
  3. Check artifact_path isfile → return dirname
  4. Construct from entity_id → check isdir → return
  5. Return None
  6. Run tests — confirm all 4 pass
- **Done when:** All 4 tests from 2.2a pass

## Phase 3: Core Functions

### Task 3.1a: Write detect_drift() tests [RED]
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`
- **Depends on:** 2.1b, 2.2b
- **Parallel group:** P3
- **Complexity:** Medium
- **Steps:**
  1. Add 8 tests — all call `detect_drift(db, file_path, type_id)` (db first, per design C2):
     - `test_drift_in_sync`: matching header and DB → status="in_sync" (AC-1)
     - `test_drift_file_only`: header with UUID, no DB record → status="file_only" (AC-2)
     - `test_drift_db_only`: no header, type_id provided, DB record → status="db_only" (AC-3)
     - `test_drift_diverged_type_id`: header type_id != DB type_id → status="diverged" + FieldMismatch (AC-4)
     - `test_drift_no_header`: no header, no type_id → status="no_header" (AC-5)
     - `test_drift_header_no_uuid_no_type_id`: header without entity_uuid, no type_id → "no_header"
     - `test_drift_type_id_different_uuid`: type_id provided, file has different UUID → "diverged"
     - `test_drift_db_error`: mock `db.get_entity` to raise `RuntimeError("connection lost")` → status="error" (verifies broad `except Exception` per TD-4)
  2. Each test: create temp file with/without frontmatter, in-memory DB, call `detect_drift(db, filepath, type_id)`
  3. Run tests — confirm all 8 FAIL
- **Done when:** 8 tests exist and all fail

### Task 3.1b: Implement detect_drift() [GREEN]
- **File:** `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync.py`
- **Depends on:** 3.1a
- **Parallel group:** —
- **Complexity:** Medium
- **Steps:**
  1. Add `detect_drift(db: EntityDatabase, filepath: str, type_id: str | None = None) -> DriftReport` (db first, per design C2/spec R3)
  2. Read frontmatter from filepath
  3. Determine lookup_key: type_id → header.entity_uuid → return no_header
  4. Look up entity in DB via lookup_key
  5. Branch: no header+no entity → no_header, header+no entity → file_only, entity+no header → db_only
  6. Compare COMPARABLE_FIELD_MAP fields (uuid: case-insensitive, type_id: case-sensitive)
  7. Wrap entire function body in try/except broad Exception → status="error"
  8. Run tests — confirm all 8 pass
- **Done when:** All 8 tests from 3.1a pass

### Task 3.2a: Write stamp_header() tests [RED]
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`
- **Depends on:** 2.1b, 2.2b
- **Parallel group:** P3
- **Complexity:** Medium
- **Steps:**
  1. Add 8 tests — all call `stamp_header(db, filepath, type_id, artifact_type)` (db first, per design C3):
     - `test_stamp_creates_header`: no existing frontmatter → action="created" (AC-6)
       Assert: `header["created_at"] == db_entity["created_at"]` (DB-authoritative, NOT datetime.now())
     - `test_stamp_with_project_id_from_metadata`: metadata project_id appears in header (AC-6a)
     - `test_stamp_updates_header`: existing matching header → action="updated" (AC-7)
       Note: created_at preserves file's original value on update (write_frontmatter merge semantics)
     - `test_stamp_mismatch_error`: existing different UUID → action="error" (AC-8)
     - `test_stamp_entity_not_found`: bad type_id → action="error" (AC-9)
     - `test_stamp_preserves_body`: body content unchanged after stamp (AC-10)
     - `test_stamp_header_no_uuid_in_existing`: existing header without entity_uuid → "created"
     - `test_stamp_build_header_error`: invalid artifact_type → action="error" via ValueError
  2. Each test: create temp file, register entity in DB, call `stamp_header(db, filepath, type_id, artifact_type)`
  3. Run tests — confirm all 8 FAIL
- **Done when:** 8 tests exist and all fail

### Task 3.2b: Implement stamp_header() [GREEN]
- **File:** `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync.py`
- **Depends on:** 3.2a
- **Parallel group:** —
- **Complexity:** Medium
- **Steps:**
  1. Add `stamp_header(db: EntityDatabase, filepath: str, type_id: str, artifact_type: str) -> StampResult` (per design C3/spec R7)
  2. Get entity from DB → if None, return error
  3. Extract required fields, derive optional fields via `_derive_optional_fields(entity, artifact_type)`
  4-7. Single try/except: build_header → read existing → UUID mismatch check → write_frontmatter
  5. Return StampResult with action="created" or "updated"
  6. Run tests — confirm all 8 pass
- **Done when:** All 8 tests from 3.2a pass

### Task 3.3a: Write ingest_header() tests [RED]
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`
- **Depends on:** 2.1b
- **Parallel group:** P3
- **Complexity:** Simple
- **Steps:**
  1. Add 5 tests — all call `ingest_header(db, filepath)` (db first, per design C4):
     - `test_ingest_updates_path`: valid header → action="updated", artifact_path set (AC-11)
       Assert: DB entity's artifact_path updated to absolute filepath; verify `db.update_entity` was called with the UUID string (not type_id), confirming the _resolve_identifier path is exercised (spec R17)
     - `test_ingest_no_frontmatter`: no header → action="skipped" (AC-12)
     - `test_ingest_entity_not_found`: UUID not in DB → action="error" (AC-13)
     - `test_ingest_no_uuid_in_header`: header without entity_uuid → action="skipped"
     - `test_ingest_race_condition`: mock `db.update_entity` to raise `ValueError("Entity not found")` after `db.get_entity` succeeds → action="error"
  2. Each test: create temp file, set up DB, call `ingest_header(db, filepath)`
  3. Run tests — confirm all 5 FAIL
- **Done when:** 5 tests exist and all fail

### Task 3.3b: Implement ingest_header() [GREEN]
- **File:** `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync.py`
- **Depends on:** 3.3a
- **Parallel group:** —
- **Complexity:** Simple
- **Steps:**
  1. Add `ingest_header(db: EntityDatabase, filepath: str) -> IngestResult` (db first, per design C4/spec R14)
  2. Read frontmatter → if None, return skipped
  3. Extract entity_uuid → if missing, return skipped
  4. Look up entity in DB → if None, return error
  5. `abs_path = os.path.abspath(filepath)` then try/except ValueError around `db.update_entity(uuid, artifact_path=abs_path)` → error("Entity disappeared")
  6. Return IngestResult action="updated"
  7. Run tests — confirm all 5 pass
- **Done when:** All 5 tests from 3.3a pass

## Phase 4: Bulk Functions

### Task 4.1a: Write backfill_headers() tests [RED]
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`
- **Depends on:** 3.1b, 3.2b, 3.3b
- **Parallel group:** P4
- **Complexity:** Medium
- **Steps:**
  1. Add 5 tests:
     - `test_backfill_stamps_all`: 3 features × 2 files each = 6 stamps (AC-14)
       Setup: register 3 feature entities, create directories with `spec.md` and `design.md` in each
     - `test_backfill_idempotent`: run twice → identical file content (AC-15)
     - `test_backfill_skips_mismatch`: mismatched UUID → error in results (AC-16)
     - `test_backfill_skips_missing_dir`: entity with no directory → "skipped" result
     - `test_backfill_empty_db`: no features → empty list
  2. Run tests — confirm all 5 FAIL
- **Done when:** 5 tests exist and all fail

### Task 4.1b: Implement backfill_headers() [GREEN]
- **File:** `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync.py`
- **Depends on:** 4.1a
- **Parallel group:** —
- **Complexity:** Simple
- **Steps:**
  1. Add `backfill_headers(db: EntityDatabase, artifacts_root: str) -> list[StampResult]`
  2. Query `db.list_entities(entity_type="feature")`
  3. For each entity: derive directory, scan for artifact files matching ARTIFACT_BASENAME_MAP
  4. For each file: try `stamp_header(db, filepath, entity["type_id"], artifact_type)`; on broad Exception → error StampResult, continue
  5. Return list of all StampResults
  6. Run tests — confirm all 5 pass
- **Done when:** All 5 tests from 4.1a pass

### Task 4.2a: Write scan_all() tests [RED]
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`
- **Depends on:** 3.1b
- **Parallel group:** P4
- **Complexity:** Simple
- **Steps:**
  1. Add 2 tests:
     - `test_scan_mixed_statuses`: headers + no headers → mixed results (AC-17)
     - `test_scan_empty_db`: no features → empty list
  2. Run tests — confirm both FAIL
- **Done when:** 2 tests exist and both fail

### Task 4.2b: Implement scan_all() [GREEN]
- **File:** `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync.py`
- **Depends on:** 4.2a
- **Parallel group:** —
- **Complexity:** Simple
- **Steps:**
  1. Add `scan_all(db: EntityDatabase, artifacts_root: str) -> list[DriftReport]`
  2. Same pattern as backfill_headers but calls detect_drift instead of stamp_header
  3. Run tests — confirm both pass
- **Done when:** Both tests from 4.2a pass

## Phase 5: Integration

### Task 5.1a: Write backfill.py header_aware tests [RED]
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`
- **Depends on:** 4.1b, 4.2b
- **Parallel group:** P5
- **Complexity:** Simple
- **Steps:**
  1. Add 2 tests (initially with `@pytest.mark.xfail(strict=True)` — runs test, confirms it fails):
     - `test_backfill_header_aware_true`: stamps headers even after backfill_complete (AC-18)
     - `test_backfill_header_aware_false`: no headers stamped (AC-19)
  2. Run tests — confirm both xfail (expected failures)
- **Done when:** 2 tests exist and show as xfail (not error)

### Task 5.1b: Implement header_aware in backfill.py [GREEN]
- **File:** `plugins/iflow/hooks/lib/entity_registry/backfill.py`
- **Depends on:** 5.1a
- **Parallel group:** —
- **Complexity:** Simple
- **Steps:**
  1. Add `header_aware=False` parameter to `run_backfill`
  2. If header_aware: lazy import frontmatter_sync, call `backfill_headers` BEFORE guard
  3. Existing logic unchanged
  4. Remove `@pytest.mark.xfail(strict=True)` from 5.1a tests
  5. Run tests — confirm both pass
- **Done when:** Both tests from 5.1a pass (xfail markers removed)

### Task 5.2a: Write CLI tests [RED]
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`
- **Depends on:** 4.1b, 4.2b
- **Parallel group:** P5
- **Complexity:** Simple
- **Steps:**
  1. Add 5 CLI tests (via `subprocess.run`):
     - `test_cli_drift`: outputs valid JSON with status field (AC-20)
     - `test_cli_backfill`: stamps and outputs JSON summary (AC-21)
     - `test_cli_scan`: outputs JSON array of drift reports (AC-22)
     - `test_cli_db_error`: invalid DB path → JSON error output, exit code 1
     - `test_cli_bad_args`: missing args → exit code non-zero
  2. Run tests — confirm all 5 FAIL (module does not exist yet)
- **Done when:** 5 tests exist and all fail

### Task 5.2b: Implement frontmatter_sync_cli.py [GREEN]
- **File:** `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync_cli.py`
- **Depends on:** 5.2a
- **Parallel group:** —
- **Complexity:** Medium
- **Steps:**
  1. Create `frontmatter_sync_cli.py` with argparse
  2. 5 subcommands: drift, stamp, ingest, backfill, scan
  3. `_open_db()`: ENTITY_DB_PATH env var → fallback
  4. `_run_handler(func)`: shared DB lifecycle wrapper — `func` is a closure over argparse `args`, accepting only `db` as parameter. Example: the `drift` handler closure captures `args.filepath` and `args.type_id`; signature is `def handler(db): return detect_drift(db, args.filepath, args.type_id)`. All 5 handler closures follow this pattern.
  5. Each handler: prints JSON via `dataclasses.asdict` + `json.dumps`
  6. TD-5: Add try/except for DB construction failure → JSON error, exit(1)
  7. Run tests — confirm all 5 pass
- **Done when:** All 5 tests from 5.2a pass

### Task 5.3: Write error handling verification tests
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`
- **Depends on:** 3.1b, 3.2b, 3.3b
- **Parallel group:** P5
- **Complexity:** Simple
- **Steps:**
  1. Add 6 tests (no new implementation needed):
     - `test_detect_drift_db_unavailable`: DB connection error → status="error" (AC-23)
     - `test_stamp_header_db_unavailable`: DB connection error → action="error" (AC-23)
     - `test_ingest_header_db_unavailable`: DB connection error → action="error" (AC-23)
     - `test_detect_drift_missing_file`: file not found → status="no_header" (AC-24)
       Note: `read_frontmatter` on non-existent file returns None (never raises, per feature 002 contract) → detect_drift gets None header + no type_id → "no_header"
     - `test_stamp_header_missing_file`: precondition failure → action="error" (AC-24)
     - `test_ingest_header_missing_file`: no frontmatter → action="skipped" (AC-24)
  2. Run tests — confirm all 6 PASS (implementations already handle these per TD-4)
- **Done when:** All 6 tests pass

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 23 |
| Phases | 5 |
| Parallel groups | 5 (P1-P5) |
| Total test functions | ~47 |
| ACs covered | 24/24 |

### Parallel Groups

- **P1** (no deps): Tasks 1.1a, 1.2a — can run simultaneously
- **P2** (depends on P1): Tasks 2.1a, 2.2a — can run simultaneously
- **P3** (depends on P2): Tasks 3.1a, 3.2a, 3.3a — can run simultaneously
- **P4** (depends on P3): Tasks 4.1a, 4.2a — can run simultaneously
- **P5** (depends on P4): Tasks 5.1a, 5.2a, 5.3 — can run simultaneously

### Dependency Chain

```
P1: [1.1a, 1.2a] → [1.1b, 1.2b]
         ↓
P2: [2.1a, 2.2a] → [2.1b, 2.2b]
         ↓
P3: [3.1a, 3.2a, 3.3a] → [3.1b, 3.2b, 3.3b]
         ↓
P4: [4.1a, 4.2a] → [4.1b, 4.2b]
         ↓
P5: [5.1a, 5.2a, 5.3] → [5.1b, 5.2b]
```
