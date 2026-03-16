# Plan: iflow Migration Tool

## Build Order

The plan follows a bottom-up approach: Python atomic operations first (independently testable), then Bash orchestration, then integration tests.

**TDD discipline:** Every step follows RED-GREEN-REFACTOR. Write failing tests first, then implement to make them pass. Tests are listed before the implementation description to enforce this ordering.

**Parallelism note:** Steps marked as parallelizable apply to concurrent agent dispatch, not developer parallelism.

### Phase 1: Python Foundation (migrate_db.py)

All migrate_db.py subcommands are independently testable with pytest + tmp_path fixtures.

#### Step 1: Scaffold migrate_db.py with argparse

**What:** Create `scripts/migrate_db.py` with argparse skeleton — all 8 subcommands registered but returning stub JSON. Include `SUPPORTED_SCHEMA_VERSION = 1` constant.

**Why:** Establishes the CLI contract that migrate.sh will call. All subsequent steps add real implementations to the existing subcommands.

**Dependencies:** None

**AC coverage:** Partial AC-8 (version constant)

**RED:** Write `test_migrate_db.py::test_subcommand_help` — verify each subcommand is registered and `--help` works. Write `test_subcommand_stubs` — verify each subcommand returns valid JSON (even if stub).
**GREEN:** Create the argparse skeleton to make tests pass.

#### Step 2: backup subcommand

**What:** Implement `backup_database()` — open source DB, call `.backup(pages=-1)` to destination, compute SHA-256 of destination file, count rows in `--table`, return JSON `{sha256, size_bytes, entry_count}`.

**Why:** Core export primitive. All other export steps depend on having valid .db backups.

**Dependencies:** Step 1

**AC coverage:** AC-2

**RED:** Write tests first:
- `test_backup_wal_mode` — Create a WAL-mode SQLite DB with test data → backup → verify integrity_check passes on backup
- `test_backup_checksum` — Verify SHA-256 matches actual file hash
- `test_backup_entry_count` — Verify entry_count matches source
**GREEN:** Implement backup_database() to pass all tests.

#### Step 3: manifest subcommand

**What:** Implement `generate_manifest()` — walk staging directory, compute SHA-256 for each file, read entry counts from DBs, read `_metadata` table for embedding provider/model (if present; null if missing), read plugin.json for version, write `manifest.json` to staging dir.

**Why:** Manifest is the integrity anchor for the bundle. Required by validate, info, and check-embeddings.

**Dependencies:** Step 2 (needs backup DBs in staging dir to count)

**AC coverage:** AC-1 (checksums), partial AC-9 (embedding metadata capture)

**RED:** Write tests first:
- `test_manifest_checksums` — Create staging dir with known files → manifest → verify all files listed with correct checksums
- `test_manifest_embedding_metadata` — Verify embedding_provider/model populated from _metadata
- `test_manifest_no_metadata` — _metadata table missing → embedding fields are null in manifest
- `test_manifest_schema_version` — Verify schema_version = 1
**GREEN:** Implement generate_manifest() to pass all tests.

**Note:** If _metadata table lacks embedding_provider/model keys, set manifest fields to null. Document this in the manifest as "unknown" provider.

#### Step 4: validate subcommand

**What:** Implement `validate_manifest()` — read manifest.json, check `schema_version <= SUPPORTED_SCHEMA_VERSION`, then verify SHA-256 of each listed file. Also verify no unexpected files exist in the bundle directory (security: prevent path traversal). Return `{valid, errors}`. Exit 1 for schema version mismatch, exit 3 for checksum mismatch.

**Why:** First line of defense on import. Must run before any state changes.

**Dependencies:** Step 3 (needs manifest to validate against)

**AC coverage:** AC-7, AC-8

**RED:** Write tests first:
- `test_validate_passes` — Valid bundle → validate passes
- `test_validate_checksum_mismatch` — Tamper with a file → checksum mismatch detected, exit 3
- `test_validate_schema_too_new` — Set schema_version=99 → rejected with correct error message, exit 1
- `test_validate_schema_current` — schema_version=1 → passes
- `test_validate_unexpected_files` — Extra files in bundle → flagged in errors
**GREEN:** Implement validate_manifest() to pass all tests.

#### Step 5: verify subcommand

**What:** Implement `verify_database()` — run `PRAGMA integrity_check`, count rows in `--table`, compare to `--expected-count`. If `--expected-count 0`, skip count comparison (just return actual_count). Return `{ok, actual_count, integrity}`.

**Why:** Post-import verification. Also used pre-merge to get current counts.

**Dependencies:** Step 1

**AC coverage:** AC-11

**RED:** Write tests first:
- `test_verify_healthy` — Healthy DB with matching count → ok=true
- `test_verify_count_only` — Healthy DB with `--expected-count 0` → ok=true, actual_count populated
- `test_verify_count_mismatch` — Count mismatch → ok=false (warning, not failure per AC-11)
- `test_verify_corrupt` — Corrupt DB → integrity check fails
**GREEN:** Implement verify_database() to pass all tests.

#### Step 6: merge-memory subcommand

**What:** Implement `merge_memory_db()` per design TD-3 — ATTACH source, INSERT OR IGNORE with source_hash dedup, FTS5 rebuild, explicit BEGIN/COMMIT with try/except/rollback. Support `--dry-run` via COUNT queries.

**Why:** Core import primitive for semantic memory.

**Dependencies:** Step 1

**AC coverage:** AC-5 (memory merge), AC-6 (dry-run), AC-13 (rollback)

**RED:** Write tests first:
- `test_merge_memory_no_overlap` — Merge with no overlap → all entries added
- `test_merge_memory_full_overlap` — Merge with full overlap → all entries skipped
- `test_merge_memory_partial_overlap` — Merge with partial overlap → correct added/skipped counts
- `test_merge_memory_dry_run` — Dry-run → returns counts but no DB changes
- `test_merge_memory_rollback` — Simulated failure mid-merge → rollback, no partial state
**GREEN:** Implement merge_memory_db() to pass all tests.

**Note:** Use the ATTACH-based INSERT OR IGNORE approach from design TD-3 with explicit column names. Column schema evolution is handled by updating the explicit column list in TD-3, not by dynamic resolution.

#### Step 7: merge-entities subcommand

**What:** Implement `merge_entities_db()` per design TD-2 — ATTACH source, FK OFF, identify new type_ids, insert with Python UUID generation, merge workflow_phases, reconstruct parent_uuid (scoped to imported type_ids only), FTS5 rebuild, explicit BEGIN/COMMIT with try/except/rollback. Support `--dry-run`.

**Why:** Core import primitive for entity registry. Most complex merge logic.

**Dependencies:** Step 1

**AC coverage:** AC-5 (entity merge), AC-6 (dry-run), AC-13 (rollback)

**RED:** Write tests first:
- `test_merge_entities_no_overlap` — Merge with no overlap → all entities + workflow_phases added, new UUIDs generated
- `test_merge_entities_full_overlap` — Merge with full overlap → all skipped (type_id dedup)
- `test_merge_entities_parent_child` — Merge with parent-child relationships → parent_uuid reconstructed correctly
- `test_merge_entities_dry_run` — Dry-run → counts only, no changes
- `test_merge_entities_rollback` — Simulated failure → rollback
**GREEN:** Implement merge_entities_db() to pass all tests.

#### Step 8: info and check-embeddings subcommands

**What:** Implement `info` (read and return manifest JSON) and `check-embeddings` (compare bundle embedding_provider/model against destination _metadata table). Return `{mismatch, warning}`.

**Why:** Embedding mismatch detection is a user-facing safety check. Info is used for dry-run display.

**Dependencies:** Step 3 (needs manifest format)

**AC coverage:** AC-9

**RED:** Write tests first:
- `test_check_same_provider` — Same provider → mismatch=false
- `test_check_different_provider` — Different provider → mismatch=true with correct warning message
- `test_check_fresh_machine` — Fresh machine (no _metadata table) → mismatch=false (skip check)
- `test_check_null_provider_in_bundle` — Bundle has null provider (no _metadata on source) → skip check, no warning
- `test_info_returns_manifest` — Info returns full manifest content
**GREEN:** Implement info and check-embeddings to pass all tests.

### Phase 2: Bash Orchestration (migrate.sh)

#### Step 9: migrate.sh scaffold + help + shared utilities

**What:** Create `scripts/migrate.sh` with:
- `set -euo pipefail`
- Color output helpers (`RED/GREEN/YELLOW/NC`) respecting `NO_COLOR`
- `die()/warn()/ok()/info()/step()` functions
- Python path resolution (dev workspace → plugin cache → system python3)
- `check_active_session()` (pgrep + WAL fallback)
- `copy_markdown_files()` and `copy_file()` helpers with --force logic
- JSON extraction helpers using `$PYTHON` (not bare `python3`) for consistency with resolved Python path
- Path constants (`IFLOW_DIR`, `MEMORY_DIR`, `MEMORY_DB`, `ENTITY_DIR`, `ENTITY_DB` with ENTITY_DB_PATH override)
- help subcommand with usage text
- Subcommand dispatch (`case` statement for export/import/help)

**Why:** Shared foundation for export and import flows. Session detection and path resolution are shared.

**Dependencies:** Step 1 (migrate_db.py must exist for Python path validation)

**AC coverage:** AC-3 (session detection), AC-10 (force mode), AC-12 (ENTITY_DB_PATH), AC-14 (progress output)

**RED:** Write `scripts/test_migrate_bash.sh` (plain shell assertions matching existing `plugins/iflow/hooks/tests/test-hooks.sh` patterns) covering shared Bash utilities:
- `check_active_session()` — mock pgrep via PATH prepend with fake script to test both active and inactive paths
- `copy_markdown_files()` — with and without --force, skip vs overwrite
- `copy_file()` — skip vs overwrite vs create new
- JSON extraction helpers — verify they parse migrate_db.py output correctly
- ENTITY_DB_PATH override — verify path constants resolve from env var
**GREEN:** Implement the migrate.sh scaffold to pass all tests.

#### Step 10: Export flow

**What:** Implement `export_flow()` per design — 6 steps: session check, staging dir, backup memory DB, backup entity DB, copy markdown + projects.txt, generate manifest + create tar.gz + cleanup staging.

**Pre-flight checks:** Before starting the export, validate that data stores exist:
- If neither memory.db nor entities.db exists → exit 1 with "No iflow data found" error message
- If .md files are absent → log info message "No markdown files found, skipping" (not an error)
- If MEMORY_DIR doesn't exist but MEMORY_DB does → create the directory

**Why:** Complete export path. Depends on all Python subcommands being functional.

**Dependencies:** Steps 2, 3, 9

**AC coverage:** AC-1, AC-2, AC-3, AC-14

**RED:** Write integration test: create test state → export → verify tar.gz contains expected files with matching checksums.
**GREEN:** Implement export_flow() to pass the test.

#### Step 11: Import flow

**What:** Implement `import_flow()` per design — 8 steps: validate bundle, session check, embedding check, create dirs, merge/copy memory, merge/copy entities, copy files, verify integrity + doctor check.

**Fresh-machine path:** When no pre-existing DB exists, copy the bundle's .db file directly. The source DB was created via `.backup()` and validated via checksums in Step 1, so raw copy is safe. Add `PRAGMA integrity_check` on the copied DB in the verify step (Step 8/8) as a defense-in-depth check.

**Tar extraction safety:** After `tar -xzf`, verify that all extracted paths are within the expected bundle directory (no path traversal). The validate subcommand (Step 4) also checks for unexpected files.

**Count verification:** Post-import verify uses `pre_merge_count + merge_added` as expected. Per AC-11, count mismatches are reported as warnings, not failures — this handles the rare case where actual inserts differ from reported counts.

**Why:** Complete import path. Includes both fresh-machine (direct copy) and merge (existing state) branches.

**Dependencies:** Steps 4, 5, 6, 7, 8, 9

**AC coverage:** AC-3 (session check uses exit code 2, same as export per spec), AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-13, AC-15

**RED:** Write integration tests:
- Export from test state → import into empty dir → verify
- Export → import with overlapping state → verify merge correctness
**GREEN:** Implement import_flow() to pass tests.

### Phase 3: Integration & Polish

#### Step 12: End-to-end tests

**What:** Write `scripts/test_migrate.py` with the 12 test cases from spec Testing Strategy section. Uses pytest + tmp_path + subprocess to invoke migrate.sh and migrate_db.py as actual CLI commands.

**Why:** Validates the full export → import pipeline including Bash + Python integration.

**Dependencies:** Steps 10, 11

**AC coverage:** All 15 ACs covered across 12 test cases

**Tests:**
1. Export round-trip (AC-1, AC-2)
2. Import fresh (AC-4)
3. Import merge (AC-5)
4. Dry-run (AC-6)
5. Corrupt bundle (AC-7)
6. Session detection (AC-3)
7. ENTITY_DB_PATH override (AC-12)
8. Embedding mismatch (AC-9)
9. Post-import doctor (AC-15)
10. Fresh machine embedding check (AC-9)
11. UUID generation on merge (AC-5)
12. Force overwrite (AC-10)

#### Step 13: Error messages and edge cases

**What:** Verify each error condition in the spec Error Messages table produces the exact message and exit code. Concrete deliverables:
1. Add test case for each of the 7 error conditions in spec Error Messages table
2. Add "no data to export" check in export_flow (validate MEMORY_DB or ENTITY_DB exists)
3. Add "Python not available" check in migrate.sh (before invoking migrate_db.py)
4. Add disk-full partial failure reporting in import_flow (track which files were/weren't restored)

**Why:** User-facing error quality. The spec defines exact messages — implementation must match.

**Dependencies:** Steps 10, 11

**AC coverage:** AC-13 (disk full), AC-14 (progress output)

**RED:** Write 7 test cases (one per error condition in spec table).
**GREEN:** Implement error handling to pass each test.

## AC Traceability

| AC | Steps |
|----|-------|
| AC-1 (export bundle) | 2, 3, 10 |
| AC-2 (backup API) | 2, 10 |
| AC-3 (session detection) | 9, 10, 11 |
| AC-4 (fresh import) | 11 |
| AC-5 (merge) | 6, 7, 11 |
| AC-6 (dry-run) | 6, 7, 11 |
| AC-7 (bundle validation) | 4, 11 |
| AC-8 (version compat) | 1, 4 |
| AC-9 (embedding mismatch) | 3, 8, 11 |
| AC-10 (force mode) | 9, 11 |
| AC-11 (verification) | 5, 11 |
| AC-12 (ENTITY_DB_PATH) | 9 |
| AC-13 (disk full) | 6, 7, 13 |
| AC-14 (progress output) | 9, 10, 11 |
| AC-15 (doctor check) | 11 |

## Dependency Graph

```
Step 1 (scaffold)
├── Step 2 (backup) ──────────────┐
│   └── Step 3 (manifest) ────────┤
│       └── Step 4 (validate) ────┤
├── Step 5 (verify) ──────────────┤
├── Step 6 (merge-memory) ────────┤
├── Step 7 (merge-entities) ──────┤
├── Step 8 (info + check-embed) ──┤
│                                 │
└── Step 9 (migrate.sh scaffold) ─┤
        ├── Step 10 (export flow) ┤
        └── Step 11 (import flow) ┤
                                  │
        Step 12 (e2e tests) ──────┘
        Step 13 (error polish) ───┘
```

Steps 2, 5, 6, 7, 8 can be implemented in parallel (all depend only on Step 1).
Steps 10, 11 can be partially parallelized (both depend on Step 9 + respective Python steps).
Steps 12, 13 run after both flows are complete.
