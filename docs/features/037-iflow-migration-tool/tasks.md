# Tasks: iflow Migration Tool

## Phase 1: Python Foundation

### Step 1: Scaffold migrate_db.py with argparse

**Parallel group: none (root)**

- [ ] **1.1** Write `scripts/test_migrate_db.py::test_subcommand_help` — parametrize over all 8 subcommands (`backup`, `manifest`, `validate`, `merge-memory`, `merge-entities`, `verify`, `info`, `check-embeddings`), assert `--help` exits 0 with usage text.
  - **Done:** Test file exists, test discovers 8 subcommands, all fail (RED).
  - **Deps:** none

- [ ] **1.2** Write `test_migrate_db.py::test_subcommand_stubs` — invoke each subcommand with minimal args, assert stdout is valid JSON.
  - **Done:** Test exists, fails because no script yet (RED).
  - **Deps:** none

- [ ] **1.3** Create `scripts/migrate_db.py` with argparse skeleton — register all 8 subcommands, each returning stub JSON `{}`. Define `SUPPORTED_SCHEMA_VERSION = 1` constant.
  - **Done:** Both tests from 1.1 and 1.2 pass (GREEN). Script is executable.
  - **Deps:** 1.1, 1.2

### Step 2: backup subcommand

**Parallel group A (depends on Step 1 only): Steps 2, 5, 6, 7**

- [ ] **2.1** Write `test_backup_wal_mode` — create a WAL-mode SQLite DB with `entries` table and 10 rows, call `backup_database()`, verify `PRAGMA integrity_check` passes on the backup file.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **2.2** Write `test_backup_checksum` — backup a DB, compute SHA-256 of output file independently, assert it matches the returned `sha256` field.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **2.3** Write `test_backup_entry_count` — backup a DB with known row count, assert returned `entry_count` matches.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **2.4** Implement `backup_database()` in migrate_db.py — open source DB, `conn.backup(dst, pages=-1)`, compute SHA-256 of dst file, count rows in `--table`, return JSON `{sha256, size_bytes, entry_count}`.
  - **Done:** All 3 backup tests pass (GREEN).
  - **Deps:** 2.1, 2.2, 2.3

### Step 3: manifest subcommand

**Depends on Step 2**

- [ ] **3.1** Write `test_manifest_checksums` — create staging dir with known files, call `generate_manifest()`, verify all files listed with correct SHA-256 checksums.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 2.4

- [ ] **3.2** Write `test_manifest_embedding_metadata` — create memory.db with `_metadata` table containing `embedding_provider` and `embedding_model` keys, generate manifest, verify fields populated.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 2.4

- [ ] **3.3** Write `test_manifest_no_metadata` — create memory.db without `_metadata` table, generate manifest, verify embedding fields are null.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 2.4

- [ ] **3.4** Write `test_manifest_schema_version` — generate manifest, verify `schema_version` equals 1.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 2.4

- [ ] **3.5** Implement `generate_manifest()` — walk staging dir, compute SHA-256 per file, read entry/entity/workflow_phases counts from DBs, read `_metadata` table for embedding provider/model (null if missing), write `manifest.json`.
  - **Done:** All 4 manifest tests pass (GREEN).
  - **Deps:** 3.1, 3.2, 3.3, 3.4

### Step 4: validate subcommand

**Depends on Step 3**

- [ ] **4.1** Write `test_validate_passes` — create valid bundle with matching checksums, assert validate returns `{valid: true, errors: []}`.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 3.5

- [ ] **4.2** Write `test_validate_checksum_mismatch` — tamper with a file after manifest generation, assert validate detects mismatch and exits 3.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 3.5

- [ ] **4.3** Write `test_validate_schema_too_new` — set `schema_version=99` in manifest, assert rejected with correct error message and exit 1.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 3.5

- [ ] **4.4** Write `test_validate_schema_current` — set `schema_version=1`, assert passes.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 3.5

- [ ] **4.5** Write `test_validate_unexpected_files` — add extra file not in manifest, assert flagged in errors.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 3.5

- [ ] **4.6** Implement `validate_manifest()` — read manifest.json, check `schema_version <= SUPPORTED_SCHEMA_VERSION` (exit 1 if not), verify SHA-256 of each listed file (exit 3 on mismatch), check for unexpected files in bundle dir. Return `{valid, errors}`.
  - **Done:** All 5 validate tests pass (GREEN).
  - **Deps:** 4.1, 4.2, 4.3, 4.4, 4.5

### Step 5: verify subcommand

**Parallel group A (depends on Step 1 only)**

- [ ] **5.1** Write `test_verify_healthy` — create healthy DB with known row count, call verify with matching `--expected-count`, assert `{ok: true, actual_count: N, integrity: "ok"}`.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **5.2** Write `test_verify_count_only` — create DB with 5 rows, call verify with `--expected-count 0`, assert ok=true AND actual_count=5 (confirms skip-count-validation path returns correct actual_count).
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **5.3** Write `test_verify_count_mismatch` — provide wrong expected count, assert ok=false as warning (not failure per AC-11).
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **5.4** Write `test_verify_corrupt` — create corrupt DB file, assert integrity check fails.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **5.5** Implement `verify_database()` — run `PRAGMA integrity_check`, count rows in `--table`, compare to `--expected-count` (skip if 0). Return `{ok, actual_count, integrity}`.
  - **Done:** All 4 verify tests pass (GREEN).
  - **Deps:** 5.1, 5.2, 5.3, 5.4

### Step 6: merge-memory subcommand

**Parallel group A (depends on Step 1 only)**

- [ ] **6.1** Write `test_merge_memory_no_overlap` — create src and dst memory DBs with disjoint entries, merge, assert all src entries added to dst.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **6.2** Write `test_merge_memory_full_overlap` — create src and dst with identical source_hash values, merge, assert all skipped, added=0.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **6.3** Write `test_merge_memory_partial_overlap` — create src and dst with some overlapping source_hash values, merge, assert correct added/skipped counts.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **6.4** Write `test_merge_memory_dry_run` — merge with `--dry-run`, assert returned counts match but dst DB unchanged.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **6.5** Write `test_merge_memory_rollback` — use `unittest.mock.patch` to replace `dst.execute` with a `side_effect` that raises `sqlite3.OperationalError` after N successful calls. Assert dst row count unchanged after the exception.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **6.6** Implement `merge_memory_db()` per design TD-3 — ATTACH source, INSERT OR IGNORE with source_hash dedup (WHERE clause), FTS5 rebuild, BEGIN/COMMIT with try/except/rollback. Support `--dry-run` via COUNT queries.
  - **Done:** All 5 merge-memory tests pass (GREEN).
  - **Deps:** 6.1, 6.2, 6.3, 6.4, 6.5

- [ ] **6.7** Write `test_merge_memory_fts_rebuild` — after a no-overlap merge, query `entries_fts` with a known term from a merged entry, assert row returned.
  - **Done:** Test passes (verifies FTS5 rebuild).
  - **Deps:** 6.6

### Step 7: merge-entities subcommand

**Parallel group A (depends on Step 1 only)**

- [ ] **7.1** Write `test_merge_entities_no_overlap` — create src and dst entity DBs with disjoint type_ids, merge, assert all entities + workflow_phases added with new UUIDs generated.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **7.2** Write `test_merge_entities_full_overlap` — create src and dst with same type_ids, merge, assert all skipped.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **7.3** Write `test_merge_entities_parent_child` — create src entities with parent-child relationships (parent_type_id set), merge, assert parent_uuid reconstructed correctly in dst.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **7.4** Write `test_merge_entities_dry_run` — merge with `--dry-run`, assert counts returned but dst unchanged.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **7.5** Write `test_merge_entities_rollback` — use `unittest.mock.patch` to replace `dst.execute` with a `side_effect` that raises `sqlite3.OperationalError` after N successful calls. Assert dst row count unchanged after the exception.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **7.6** Implement `merge_entities_db()` per design TD-2 — ATTACH source, FK OFF, identify new type_ids, insert with Python UUID generation, merge workflow_phases, reconstruct parent_uuid scoped to imported type_ids, FTS5 rebuild, BEGIN/COMMIT with try/except/rollback. Support `--dry-run`.
  - **Done:** All 5 merge-entities tests pass (GREEN).
  - **Deps:** 7.1, 7.2, 7.3, 7.4, 7.5

- [ ] **7.7** Write `test_merge_entities_fts_rebuild` — after a no-overlap merge, query `entities_fts` with a known term from an imported entity, assert row returned.
  - **Done:** Test passes (verifies FTS5 rebuild).
  - **Deps:** 7.6

### Step 8: info and check-embeddings subcommands

**Depends on Step 3 (needs manifest format)**

- [ ] **8.1** Write `test_check_same_provider` — same embedding_provider in bundle and dst → assert mismatch=false.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 3.5

- [ ] **8.2** Write `test_check_different_provider` — different provider → assert mismatch=true with correct warning message.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 3.5

- [ ] **8.3** Write `test_check_fresh_machine` — no _metadata table in dst (fresh machine) → assert mismatch=false (skip check).
  - **Done:** Test exists, fails (RED).
  - **Deps:** 3.5

- [ ] **8.4** Write `test_check_null_provider_in_bundle` — bundle has null embedding_provider → assert skip check, no warning.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 3.5

- [ ] **8.5** Write `test_info_returns_manifest` — call info subcommand, assert returns full manifest JSON content.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 3.5

- [ ] **8.6** Implement `info` (read and return manifest JSON) and `check-embeddings` (compare bundle vs dst _metadata table embedding_provider/model). Return `{mismatch, warning}`.
  - **Done:** All 5 info/check-embeddings tests pass (GREEN).
  - **Deps:** 8.1, 8.2, 8.3, 8.4, 8.5

## Phase 2: Bash Orchestration

### Step 9: migrate.sh scaffold + help + shared utilities

**Depends on Step 1**

- [ ] **9.1** Write `scripts/test_migrate_bash.sh` test: `check_active_session()` — create fake pgrep via PATH prepend, test active path returns 0 and inactive path returns 1.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **9.2** Write test: `copy_markdown_files()` — test with and without `--force`: skip existing files vs overwrite, count added/skipped.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **9.3** Write test: `copy_file()` — test skip (file exists, no force), overwrite (file exists + force), create new (file doesn't exist).
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **9.4** Write test: JSON extraction helpers — pipe sample migrate_db.py JSON output, verify correct field extraction.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **9.5** Write test: ENTITY_DB_PATH override — set env var, verify path constants resolve from it.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 1.3

- [ ] **9.6** Implement `scripts/migrate.sh` scaffold — `set -euo pipefail`, color helpers (respect `NO_COLOR`), `die()/warn()/ok()/info()/step()`, Python path resolution, `check_active_session()`, `copy_markdown_files()`, `copy_file()`, JSON extraction helpers using `$PYTHON`, path constants, help subcommand, `case` dispatch.
  - **Done:** All 5 Bash utility tests pass (GREEN). `migrate.sh help` prints usage and exits 0.
  - **Deps:** 9.1, 9.2, 9.3, 9.4, 9.5

### Step 10: Export flow

**Depends on Steps 2, 3, 9**

- [ ] **10.1** Write integration test: create test state (memory.db with entries, entities.db with entities + workflow_phases, markdown files, projects.txt) → run `migrate.sh export` → verify tar.gz contains expected files with matching checksums.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 2.4, 3.5, 9.6

- [ ] **10.2** Implement `export_flow()` in migrate.sh — pre-flight checks (validate data stores exist), 6 steps: session check, staging dir, backup memory DB, backup entity DB, copy markdown + projects.txt, generate manifest + create tar.gz + cleanup staging. Print summary.
  - **Done:** Integration test passes (GREEN). Export produces valid tar.gz.
  - **Deps:** 10.1

### Step 11: Import flow

**Depends on Steps 4, 5, 6, 7, 8, 9**

- [ ] **11.1** Write integration test: export from test state → import into empty dir (fresh machine) → verify all entries present, integrity check passes.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 4.6, 5.5, 6.6, 7.6, 8.6, 9.6

- [ ] **11.2** Write integration test: export → import with overlapping state → verify merge correctness (correct added/skipped counts, no duplicates).
  - **Done:** Test exists, fails (RED).
  - **Deps:** 4.6, 5.5, 6.6, 7.6, 8.6, 9.6

- [ ] **11.3** Implement `import_flow()` in migrate.sh — tar extraction with path traversal safety check, 8 steps: validate bundle, session check (exit 2), embedding check, create dirs, merge/copy memory (fresh-machine: direct copy; existing: merge), merge/copy entities, copy files (--force logic), verify integrity + doctor check. Print summary.
  - **Done:** Both import integration tests pass (GREEN).
  - **Deps:** 11.1, 11.2

## Phase 3: Integration & Polish

### Step 12: End-to-end tests

**Depends on Steps 10, 11**

- [ ] **12.1** Write e2e test 1: Export round-trip — create state, export, extract, verify checksums match (AC-1, AC-2).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **12.2** Write e2e test 2: Import fresh — export, import into empty dir, verify all entries (AC-4).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **12.3** Write e2e test 3: Import merge — create overlapping state, import, verify no duplicates (AC-5).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **12.4** Write e2e test 4: Dry-run — import with `--dry-run`, verify zero filesystem changes (AC-6).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **12.5** Write e2e test 5: Corrupt bundle — tamper with file, verify import rejects with exit 3 (AC-7).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **12.6** Write e2e test 6: Session detection — mock pgrep active, verify abort exit 2 (AC-3).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **12.7** Write e2e test 7: ENTITY_DB_PATH override — set env var, verify export reads from custom path (AC-12).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **12.8** Write e2e test 8: Embedding mismatch — different provider, verify warning printed (AC-9).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **12.9** Write e2e test 9: Post-import doctor — import, verify health checks run (AC-15).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **12.10** Write e2e test 10: Fresh machine embedding — import to empty dir with no _metadata, verify no mismatch warning (AC-9).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **12.11** Write e2e test 11: UUID generation — import with overlapping entities, verify new UUIDs generated for new entries (AC-5).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **12.12** Write e2e test 12: Force overwrite — create existing markdown, import with `--force`, verify overwritten (AC-10).
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

### Step 13: Error messages and edge cases

**Depends on Steps 10, 11**

- [ ] **13.1** Write test: no subcommand → verify "Usage: migrate.sh {export|import|help}" message and exit 1.
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **13.2** Write test: active session without --force → verify "Error: Active Claude session detected..." message and exit 2.
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **13.3** Write test: bundle not found → verify "Error: Bundle not found: {path}" and exit 1.
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **13.4** Write test: checksum mismatch → verify exact error message with file name, expected, actual, and exit 3.
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **13.5** Write test: schema version too new → verify "Error: Bundle requires..." message and exit 1.
  - **Done:** Test passes.
  - **Deps:** 10.2, 11.3

- [ ] **13.6a** Write test: no data to export — run `migrate.sh export` with empty `~/.claude/iflow/`, verify "Error: No iflow data found..." and exit 1.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 10.2

- [ ] **13.6b** Implement "no data to export" pre-flight check in export_flow — validate MEMORY_DB or ENTITY_DB exists before starting.
  - **Done:** Test from 13.6a passes (GREEN).
  - **Deps:** 13.6a

- [ ] **13.7a** Write test: Python not available — set PATH to exclude python3, run `migrate.sh export`, verify "Error: Python 3 required..." and exit 1.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 9.6

- [ ] **13.7b** Implement Python availability check in migrate.sh — verify `$PYTHON` is executable before invoking migrate_db.py.
  - **Done:** Test from 13.7a passes (GREEN).
  - **Deps:** 13.7a

- [ ] **13.8a** Write test: disk-full mid-import — mock write failure after N files copied, assert exit 1, error message lists restored files and NOT-restored files, DB changes rolled back.
  - **Done:** Test exists, fails (RED).
  - **Deps:** 11.3

- [ ] **13.8b** Implement disk-full partial failure reporting in import_flow — track which files were/weren't restored, report in error message on write failure (AC-13).
  - **Done:** Test from 13.8a passes (GREEN).
  - **Deps:** 13.8a

- [ ] **13.9** Write test: path traversal in bundle — create a tar.gz with an entry like `../../etc/passwd`, verify import rejects with exit 1 before extracting any files.
  - **Done:** Test passes.
  - **Deps:** 11.3

## Summary

- **Total tasks:** 79
- **Phase 1 (Python):** 43 tasks across 8 steps
- **Phase 2 (Bash):** 11 tasks across 3 steps
- **Phase 3 (Integration):** 25 tasks across 2 steps
- **Parallel groups:** Steps 2, 5, 6, 7 can run in parallel after Step 1. Steps 10, 11 can partially parallelize after Step 9.
