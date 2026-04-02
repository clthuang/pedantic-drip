# Tasks: Unify Entity Reconciliation

## Stage 1: Tests First, Then Implementation (TDD)

### Plan Item 1: Write unit tests for _sync_backlog_entities()

- [ ] **Task 1.1** — Add backlog status parsing test fixtures
  - Add `seed_backlog()` helper and `write_backlog_md()` helper to test_entity_status.py
  - `seed_backlog(db, entity_id, status=None)` registers a backlog entity via `db.register_entity(entity_type="backlog", ...)`
  - `write_backlog_md(tmp_path, rows)` writes a pipe-delimited markdown table with header + rows
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Helpers exist, can be called without error

- [ ] **Task 1.2** — Write test: (closed:) row → status "dropped"
  - Class `TestSyncBacklogEntities`, test method `test_closed_status_mapped_to_dropped`
  - Write backlog.md with `| 00014 | 2026-01-01T00:00:00Z | Security Scanning (closed: not needed) |`
  - Seed entity `backlog:00014` with status `"open"`, call `_sync_backlog_entities()`, assert status updated to `"dropped"`
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED) because `_sync_backlog_entities` doesn't exist yet

- [ ] **Task 1.3** — Write test: (promoted →) row → status "promoted"
  - Test method `test_promoted_status_mapped`
  - Row: `| 00020 | 2026-01-01T00:00:00Z | Rename plugin (promoted → feature:048) |`
  - Seed entity with status `"open"`, assert updated to `"promoted"`
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

- [ ] **Task 1.4** — Write test: (fixed:) row → status "dropped"
  - Test method `test_fixed_status_mapped_to_dropped`
  - Row: `| 00048 | 2026-01-01T00:00:00Z | Release tag check (fixed: auto-increment) |`
  - Seed entity with status `"open"`, assert updated to `"dropped"`
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

- [ ] **Task 1.5** — Write test: (already implemented) row → status "dropped"
  - Test method `test_already_implemented_mapped_to_dropped`
  - Row: `| 00046 | 2026-01-01T00:00:00Z | Add review cycle (closed: already implemented — Stage 4) |`
  - Seed entity with status `"open"`, assert updated to `"dropped"`
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

- [ ] **Task 1.6** — Write test: no marker → status "open", new entity registered
  - Test method `test_no_marker_registered_as_open`
  - Row: `| 00016 | 2026-01-01T00:00:00Z | Multi-Model Orchestration |`
  - No seed (entity not in DB). Assert entity registered with status `"open"`, `registered` count == 1
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

- [ ] **Task 1.7** — Write test: junk ID deletion
  - Test method `test_junk_ids_deleted`
  - Seed entities `backlog:B2`, `backlog:#`, `backlog:~~B1~~` in DB
  - Call `_sync_backlog_entities()` (with valid backlog.md). Assert all 3 deleted, `deleted` count == 3
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

- [ ] **Task 1.8** — Write test: junk deletion handles ValueError (entity with children)
  - Test method `test_junk_deletion_skips_entity_with_children`
  - Mock `db.delete_entity` to raise `ValueError` for the junk entity. Assert warning captured in results, no crash
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

- [ ] **Task 1.9** — Write test: same-project dedup
  - Test method `test_same_project_dedup`
  - Seed `backlog:00020` twice with same `project_id` (one with status `"open"`, one with `None`)
  - Assert only one remains (the one with non-null status), `deleted` count == 1
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

- [ ] **Task 1.10** — Write test: missing backlog.md returns empty results
  - Test method `test_missing_backlog_md_returns_empty`
  - Don't write any backlog.md. Assert returns `{"updated": 0, "skipped": 0, "registered": 0, "deleted": 0, "warnings": []}`
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

### Plan Item 2: Implement _sync_backlog_entities() helper

- [ ] **Task 2.1** — Add regex constants to entity_status.py
  - Add `BACKLOG_ROW_RE`, `CLOSED_RE`, `PROMOTED_RE`, `FIXED_RE`, `JUNK_ID_RE` at module level
  - Align `CLOSED_RE` with doctor/checks.py: `r'\((?:closed|already implemented)[:\s—]'`
  - Align `PROMOTED_RE` with doctor/checks.py: `r'\(promoted\s*(?:→|->)'`
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`
  - **Done when:** Constants exist, `import re` added

- [ ] **Task 2.2** — Implement `_cleanup_junk_backlogs()` helper
  - Private function: `_cleanup_junk_backlogs(db, project_id) -> tuple[int, list[str]]`
  - Uses `db.list_entities(entity_type="backlog", project_id=project_id)`
  - Deletes entities where `entity_id` doesn't match `JUNK_ID_RE` (^[0-9]{5}$)
  - Catches `ValueError` from `delete_entity` (entity has children), appends to warnings
  - Returns `(deleted_count, warnings_list)`
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`
  - **Done when:** Function exists, Task 1.7 and 1.8 tests pass

- [ ] **Task 2.3** — Implement `_dedup_backlogs()` helper
  - Private function: `_dedup_backlogs(db, project_id) -> int`
  - Uses `db.list_entities(entity_type="backlog", project_id=project_id)`
  - Groups by `(entity_id, project_id)` composite key
  - For duplicates: keeps entity with non-null status, deletes the other
  - Returns count deleted
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`
  - **Done when:** Function exists, Task 1.9 test passes

- [ ] **Task 2.4** — Implement `_sync_backlog_entities()` main function
  - Private function per design I2 signature: `_sync_backlog_entities(db, full_artifacts_path, artifacts_root, project_id)`
  - Execution order: (1) junk cleanup via `_cleanup_junk_backlogs`, (2) dedup via `_dedup_backlogs`, (3) parse backlog.md and sync
  - Reads `os.path.join(full_artifacts_path, "backlog.md")`
  - Uses BACKLOG_ROW_RE to parse rows, status regex to detect markers
  - Strips status markers from name with `re.sub`
  - Register new entities via `db.register_entity()`, update existing via `db.update_entity()`
  - Returns aggregated `{"updated": N, "skipped": N, "registered": N, "deleted": N, "warnings": [...]}`
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`
  - **Done when:** All Tasks 1.2–1.10 tests pass (GREEN)

### Plan Item 3: Write tests + implement _sync_brainstorm_entities()

- [ ] **Task 3.1** — Write test: register new brainstorm
  - Class `TestSyncBrainstormEntities`, test method `test_new_brainstorm_registered`
  - Create `brainstorms/foo.prd.md` file. Assert entity `brainstorm:foo` registered with status `"active"`, `registered` == 1
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

- [ ] **Task 3.2** — Write test: skip existing brainstorm
  - Test method `test_existing_brainstorm_skipped`
  - Seed `brainstorm:foo` in DB, create file. Assert `skipped` == 1, no duplicate
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

- [ ] **Task 3.3** — Write test: archive brainstorm with missing file (AC-9)
  - Test method `test_missing_prd_file_archived`
  - Seed `brainstorm:foo` with status `"active"` and `artifact_path="docs/brainstorms/foo.prd.md"` but don't create the file
  - Assert status updated to `"archived"`, `archived` == 1
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

- [ ] **Task 3.4** — Write test: terminal-status brainstorms not re-archived
  - Test method `test_terminal_brainstorm_not_rearchived`
  - Seed `brainstorm:foo` with status `"promoted"`, no file. Assert not updated (already terminal)
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test exists, fails (RED)

- [ ] **Task 3.5** — Implement `_sync_brainstorm_entities()` helper
  - Private function per design I5 signature: `_sync_brainstorm_entities(db, full_artifacts_path, artifacts_root, project_root, project_id)`
  - Part 1: scan brainstorms/ for .prd.md files, register unregistered (copy from brainstorm_registry.py)
  - Part 2 (NEW): scan DB brainstorm entities, check if `os.path.join(project_root, artifact_path)` exists, set missing to "archived"
  - Skip terminal statuses: promoted, abandoned, archived
  - Returns `{"registered": N, "archived": N, "skipped": N}`
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`
  - **Done when:** Tasks 3.1–3.4 tests pass (GREEN)

## Stage 2: Integration (depends on Stage 1)

> **Commit boundary note:** Tasks 5.1, 5.2, 6.1, and 6.2 must be committed together as one atomic commit to avoid a broken test window (removing brainstorm_sync key before updating test assertions).

### Plan Item 4: Refactor sync_entity_statuses() to call all 4 helpers

- [ ] **Task 4.1** — Extract existing feature/project logic into `_sync_meta_json_entities()`
  - Move the for-loop body from `sync_entity_statuses()` into `_sync_meta_json_entities(db, full_artifacts_path, subdir, entity_type, project_id)`
  - `sync_entity_statuses()` calls it twice: once for `("features", "feature")`, once for `("projects", "project")`
  - Behavior unchanged — pure refactor
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`
  - **Done when:** Existing tests pass: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py -v`

- [ ] **Task 4.2** — Update sync_entity_statuses() signature and wire all 4 helpers
  - Add `artifacts_root: str = "docs"` and `project_root: str = ""` parameters
  - If `project_root` is empty, derive safely: `full_artifacts_path.removesuffix(artifacts_root).rstrip(os.sep)` — add assertion that result is non-empty and a valid directory
  - Pass `project_root` to `_sync_brainstorm_entities()` (needed for AC-9 missing-file detection)
  - Pass `artifacts_root` to `_sync_backlog_entities()` (needed for artifact_path storage)
  - Call `_sync_meta_json_entities` (features), `_sync_meta_json_entities` (projects), `_sync_brainstorm_entities`, `_sync_backlog_entities`
  - Aggregate results: merge all counters, concatenate warnings
  - Return dict gains `registered` and `deleted` keys
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`
  - **Done when:** New integration test passes with all 4 entity types in fixture dir

- [ ] **Task 4.3** — Write integration test for unified sync
  - Test method `test_unified_sync_all_four_types`
  - Create fixtures: features/.meta.json, projects/.meta.json, brainstorms/foo.prd.md, backlog.md
  - Seed entities for each type in DB. Call `sync_entity_statuses()` with all params
  - Assert return dict has all 6 keys: updated, skipped, archived, registered, deleted, warnings
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`
  - **Done when:** Test passes

### Plan Item 5: Update orchestrator __main__.py

- [ ] **Task 5.1** — Remove brainstorm_registry import and Task 2 call
  - Delete `from reconciliation_orchestrator import brainstorm_registry` (keep entity_status, kb_import)
  - Delete Task 2 block (lines ~100-107 in __main__.py)
  - Delete `results["brainstorm_sync"]` initialization from results dict
  - **Note:** Part of atomic commit with Tasks 5.2, 6.1, 6.2 — do not commit separately
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py`
  - **Done when:** No brainstorm_registry references in __main__.py

- [ ] **Task 5.2** — Add artifacts_root and project_root to Task 1 call
  - Update Task 1 call: `entity_status.sync_entity_statuses(entity_db, full_artifacts_path, project_id=project_id, artifacts_root=args.artifacts_root, project_root=args.project_root)`
  - `args.project_root` already exists as a CLI argument — wire it through
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py`
  - **Done when:** Task 1 call passes both `artifacts_root` and `project_root` parameters

## Stage 3: Cleanup (depends on Stage 2) — atomic commit

### Plan Item 6: Delete brainstorm_registry + update tests + regression

- [ ] **Task 6.1** — Update test_orchestrator.py assertions
  - Remove assertions for `brainstorm_sync` key (lines ~97, ~143)
  - Add assertions for `entity_sync` having `registered` and `deleted` keys
  - Update `TestFullRunOutputsValidJson` expected keys list
  - **Files:** `plugins/pd/hooks/lib/reconciliation_orchestrator/test_orchestrator.py`
  - **Done when:** Updated assertions compile (may fail until deletion done)

- [ ] **Task 6.2** — Delete brainstorm_registry.py and test_brainstorm_registry.py
  - First verify: `grep -r brainstorm_registry plugins/pd/` — confirm only __main__.py (already handled in 5.1) and test files remain
  - Check `__init__.py` for any brainstorm_registry imports
  - `rm plugins/pd/hooks/lib/reconciliation_orchestrator/brainstorm_registry.py`
  - `rm plugins/pd/hooks/lib/reconciliation_orchestrator/test_brainstorm_registry.py`
  - **Files:** delete 2 files
  - **Done when:** Files removed, `grep -r brainstorm_registry plugins/pd/` returns zero matches

- [ ] **Task 6.3** — Run full regression test suite
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/reconciliation_orchestrator/ plugins/pd/hooks/lib/entity_registry/ -v`
  - All tests pass with zero failures
  - **Files:** none (verification only)
  - **Done when:** Exit code 0, all tests pass

### Plan Item 7: Final regression

- [ ] **Task 7.1** — Run extended test suite
  - Run reconciliation_orchestrator + entity_registry + workflow_engine tests
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/reconciliation_orchestrator/ plugins/pd/hooks/lib/entity_registry/ plugins/pd/hooks/lib/workflow_engine/ -v`
  - **Files:** none (verification only)
  - **Done when:** All tests pass

## Task Dependencies

```
Tasks 1.1 → 1.2–1.10 (fixtures needed first)
Tasks 1.2–1.10 → 2.1–2.4 (RED before GREEN)
Tasks 3.1–3.4 → 3.5 (RED before GREEN)
Tasks 2.4 + 3.5 → 4.1–4.3 (helpers before integration)
Tasks 4.1–4.3 → 5.1–5.2 (unified fn before orchestrator)
Tasks 5.1–5.2 → 6.1–6.3 (orchestrator updated before cleanup)
Tasks 6.1–6.3 → 7.1 (cleanup before final regression)

Parallel groups:
- Tasks 1.2–1.10 can run in parallel (independent test cases)
- Tasks 3.1–3.4 can run in parallel (independent test cases)
- Items 1-2 and Item 3 are independent (can be done in parallel)
- Tasks 6.1 + 6.2 must be in same atomic commit
```
