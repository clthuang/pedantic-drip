# Tasks — Feature 110: Markdown Projections and Generalized Guards

- **Project:** P003-entity-system-redesign M3
- **Plan:** plan.md rev 1 | **Spec:** spec.md rev 4 | **Design:** design.md rev 3
- **Format note:** tasks use `### Task N.M:` heading convention per implementing-skill parser regex `/^(#{3,4})\s+Task\s+(\d+(?:\.\d+)*):?\s*(.+)$/`
- **Status:** revision 2 (plan-reviewer iter-1 blockers/warnings resolved)
- **TDD discipline (mandatory):** Within each Group, tasks are listed in logical order grouped by concern (schema, port, test). Implementers MUST execute RED tests first — write the failing test, run it, confirm it fails, then write the implementation task that makes it pass. Tasks tagged with `**DoD:**` assertions express the GREEN-state contract. The Group's full set of test tasks (e.g., 2.3-2.7) should be written as RED skeletons BEFORE the implementation tasks (e.g., 2.1-2.2) are touched. Implementer-skill is responsible for enforcing this ordering at execution time. Where a test cannot fail-before-scaffold (e.g., it imports a not-yet-defined function), the RED skeleton asserts the import fails — that's the initial RED state.

## Group 0 — Scaffolding

### Task 0.1: Append projection-related entries to .gitignore
- **Why:** Spec FR-4.5, AC-1.4
- **Source:** Plan Group 0.1
- **DoD:** `cat .gitignore | grep -E "^(\*\*/\.meta\.json|docs/backlog\.md|pd-state\.diff\.md)$" | wc -l` returns 3.

### Task 0.2: Create data_file_guards package init
- **Why:** Plan Group 0.2; enables Group 9 imports
- **DoD:** `plugins/pd/hooks/lib/data_file_guards/__init__.py` exists; `python3 -c "import data_file_guards"` succeeds with `PYTHONPATH=plugins/pd/hooks/lib`.

### Task 0.3: Create test fixtures directory and placeholders
- **Why:** Plan Group 0.3; AC-7.5 hot-add test needs fixtures
- **DoD:** `plugins/pd/hooks/tests/fixtures/test_data_file_guards.json` exists (empty `[]` placeholder); `fixture_guard.py` and `fixture_decision.py` exist as minimal valid Python modules.

## Group 1 — Migration 13 stub + pre-flight gate

### Task 1.1: Add _migration_13_entity_display stub with pre-flight gate
- **Why:** Plan Group 1.1; Design TD-6 (3-check gate); FR-5.5
- **Source:** Spec FR-5.5
- **DoD:** Function defined in `plugins/pd/hooks/lib/entity_registry/database.py`; runs 3 pre-flight checks (user_version, schema_version table cross-check, table_info column layout); registered in `MIGRATIONS[13]`. Body raises NotImplementedError after gate passes (will be implemented in Group 2).

### Task 1.2: Add _migration_13_entity_display_down stub
- **Why:** Plan Group 1.2; Design TD-8 + FR-5.4
- **DoD:** Function defined; raises NotImplementedError; registered in `MIGRATIONS_DOWN[13]`.

### Task 1.3: Test pre-flight aborts on stale schema (3 shapes)
- **Why:** Plan Group 1.3; AC-5.6, AC-5.6b, AC-5.6c
- **DoD:** `test_migration_13_safety.py::test_pre_flight_aborts_on_stale_schema` covers: (a) entity_type present + type/kind absent (never-ran-12 shape); (b) entity_type present + type/kind present (partial-12 shape); (c) user_version=12 but schema_version table=11 (version divergence). Each asserts ABORT with respective error phrase.

### Task 1.4: Test pre-flight passes on clean post-12 DB
- **Why:** Plan Group 1.4
- **DoD:** Fresh post-12 fixture proceeds past gate (stub raises NotImplementedError after gate).

## Group 2 — entity_display table + index + backfill

### Task 2.1: Implement migration 13 body (CREATE TABLE + INDEX + version stamp)
- **Why:** Plan Group 2.1; Spec FR-8.1, FR-5.1, FR-5.2, FR-5.3
- **DoD:** Inside `BEGIN IMMEDIATE`: `PRAGMA foreign_key_check` pre-commit; `CREATE TABLE entity_display(uuid PK FK ON DELETE CASCADE, seq INT NOT NULL, slug TEXT NOT NULL)`; `CREATE INDEX idx_entity_display_seq ON entity_display(seq)`; idempotency early-return; `PRAGMA user_version = 13`; INSERT into `schema_version(13, ISO_TS)`; `PRAGMA foreign_key_check` post-commit.

### Task 2.2: Implement backfill INSERT with runtime PRAGMA introspection
- **Why:** Plan Group 2.2; FR-8.2, FR-5.6
- **DoD:** Backfill body: `PRAGMA table_info(entities)` discovers columns; asserts presence of `uuid`, `entity_id`, `metadata`; aborts with column-missing error if absent. INSERT uses `CAST(substr(entity_id, 1, instr(entity_id, '-') - 1) AS INTEGER)` for seq, `substr(entity_id, instr(entity_id, '-') + 1)` for slug.

### Task 2.3: Test entity_display schema after migration
- **Why:** AC-8.1
- **DoD:** `PRAGMA table_info(entity_display)` returns 3 cols + PRIMARY KEY constraint; `sqlite_master` shows `idx_entity_display_seq`.

### Task 2.4: Test 1:1 backfill invariant
- **Why:** AC-8.2
- **DoD:** `SELECT COUNT(*) FROM entities WHERE uuid NOT IN (SELECT uuid FROM entity_display)` returns 0.

### Task 2.5: Test backfill seq/slug match entity_id suffix
- **Why:** AC-8.3
- **DoD:** Per-row SQL compares `entity_display.seq` and `entity_display.slug` against `entities.entity_id` parsed.

### Task 2.6: Test migration 13 idempotent replay
- **Why:** AC-5.2, FR-5.2
- **DoD:** Run migration twice; second run no-op (early-return); schema_version=13, entity_display row count unchanged.

### Task 2.7: Test user_version and schema_version table set
- **Why:** AC-5.3
- **DoD:** Post-migration `PRAGMA user_version = 13` AND `SELECT MAX(version) FROM schema_version = 13` AND `(13, ISO_TS)` row exists.

### Task 2.8: Test single-tx BEGIN IMMEDIATE + FK check pre/post
- **Why:** AC-5.1
- **DoD:** Inspect migration function source: BEGIN IMMEDIATE present; PRAGMA foreign_key_check called before AND after the DDL block; both calls return zero rows in healthy fixture; partial-state DB rolls back cleanly on synthetic FK violation.

### Task 2.9: Test runtime PRAGMA table_info introspection aborts on missing column
- **Why:** AC-5.7
- **DoD:** Synthetic fixture DB with `metadata` column dropped from entities; migration ABORTS with column-missing error; entity_display table NOT created.

## Group 3 — Pre-audit + migration_audit_log

### Task 3.1: Create migration_audit_log table
- **Why:** Plan Group 3.1; Design TD-2
- **DoD:** `CREATE TABLE IF NOT EXISTS migration_audit_log` inside migration 13 transaction with 5 columns per design TD-2 schema. No indexes.

### Task 3.2: Implement pre-audit query + mismatch logging
- **Why:** Plan Group 3.2; FR-8.2-pre
- **DoD:** SQL per spec FR-8.2-pre runs before backfill INSERT; each mismatch row → `INSERT INTO migration_audit_log(13, 'mismatch_row', payload_json, ISO_TS)`.

### Task 3.3: Implement env-var bypass + bypass_acknowledged forensic row
- **Why:** Plan Group 3.3; FR-8.2-pre per spec rev-4 fix
- **DoD:** If mismatch count > 0 AND `os.environ.get('PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS') != '1'`, RAISE with UUID list. If env IS set, INSERT row `(13, 'bypass_acknowledged', '{"mismatch_count":N,"user":"...","ts":"..."}', ISO_TS)` to migration_audit_log.

### Task 3.4: Test pre-audit clean DB zero mismatches
- **Why:** AC-8.0 part a
- **DoD:** Clean fixture: pre-audit returns 0 rows; no migration_audit_log rows written.

### Task 3.5: Test pre-audit mismatch aborts without env bypass
- **Why:** AC-8.0 part b
- **DoD:** Synthetic mismatch fixture (manually edit metadata JSON to differ from entity_id suffix); migration ABORTS with UUID list; entity_display table NOT created.

### Task 3.6: Test pre-audit mismatch with env bypass writes forensic rows
- **Why:** AC-8.0 part c; new from spec rev-4
- **DoD:** Same fixture + `PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS=1`; migration proceeds; migration_audit_log has N+1 rows (N mismatch + 1 bypass_acknowledged).

## Group 4 — scan_entity_ids port

### Task 4.1: Modify scan_entity_ids to query entity_display
- **Why:** Plan Group 4.1; FR-8.3a
- **Source:** Spec FR-8.3
- **DoD:** New body: `SELECT COALESCE(MAX(seq), 0) FROM entity_display d JOIN entities e ON d.uuid = e.uuid WHERE e.workspace_uuid = ?`. Old regex-on-entity_id removed. Function signature unchanged.

### Task 4.2: Test scan_entity_ids returns same max_seq pre vs post migration
- **Why:** AC-8.4
- **DoD:** Pre-migration call returns same value as post-migration call when entity content is unchanged. Asserts byte-equality.

## Group 5 — _project_meta_json reads entity_display

### Task 5.1: Modify _project_meta_json to query entity_display
- **Why:** Plan Group 5.1; FR-8.3b
- **DoD:** At `workflow_state_server.py:373,416-418`, replace `metadata.get('id')`/`metadata.get('slug')` with JOIN against entity_display. If row missing, log WARN and fall back to metadata JSON (defense-in-depth).

### Task 5.2: Test _project_meta_json reads from entity_display
- **Why:** AC-8.5
- **DoD:** Test deletes `id`/`slug` from `metadata` JSON post-migration, re-projects, asserts `.meta.json` output byte-identical to pre-edit.

### Task 5.3: Test _project_meta_json byte-deterministic
- **Why:** AC-4.1 (analog to AC-4.2 backlog test)
- **DoD:** Two consecutive `_project_meta_json(db, engine, type_id)` invocations against unchanged DB state produce byte-identical bytes (SHA256 hash equality). Static-check grep: `_project_meta_json` body contains no `datetime.utcnow()` / `datetime.now()` calls.

### Task 5.4: Test delete .meta.json then regenerate matches pre-delete bytes
- **Why:** AC-4.3
- **DoD:** Capture `.meta.json` bytes; delete file; re-invoke `_project_meta_json`; compare bytes byte-for-byte.

### Task 5.5: Test tamper safety — manual edit doesn't affect DB
- **Why:** AC-4.5
- **DoD:** Append `"tampered": true` to `.meta.json`. Read `SELECT status FROM entities WHERE type_id = ?` before and after; equal. Re-invoke projection: file content reverts to canonical (no `tampered` key).

### Task 5.6: Test _project_backlog_md import smoke
- **Why:** AC-1.3
- **DoD:** `python3 -c "from workflow_state_server import _project_backlog_md; print(callable(_project_backlog_md))"` prints `True`.

## Group 6 — backfill.py port

### Task 6.1: Port backfill.py entity_id parsing to entity_display query
- **Why:** Plan Group 6.1; FR-8.3c
- **DoD:** Replace exact old/new text per plan Group 6.1 spec. Test suite still passes.

## Group 7 — Rename test (AC-8.6 + AC-8.7)

### Task 7.1: Test slug rename leaves entities table byte-identical
- **Why:** AC-8.6
- **DoD:** `UPDATE entity_display SET slug='renamed' WHERE uuid = ?` → assert `sqlite3 .dump` of entities WHERE uuid = ? byte-identical pre/post; phase_events full dump byte-identical (NO updated_at touch on entities; NO new phase_events row).

### Task 7.2: Test slug rename preserves child→parent linkage
- **Why:** AC-8.7
- **DoD:** Parent entity + child entity; rename parent slug via entity_display; assert child.parent_uuid still resolves to parent; parent.uuid + entity_id + type_id unchanged.

## Group 8 — _project_backlog_md function

### Task 8.1: Implement _project_backlog_md function (two-format)
- **Why:** Plan Group 8.1; Design §4.5, TD-10
- **DoD:** Function exists in `workflow_state_server.py`; emits flat top-level table for `metadata.format='table_row'` and bullet items for `format='bullet_item'` under appropriate section headers. Sorts within section by ID ascending.

### Task 8.2: Implement backfill parser for existing backlog.md
- **Why:** Plan Group 8.2 / 12.4
- **DoD:** Script in `plugins/pd/scripts/` parses existing `docs/backlog.md`, assigns `metadata.format`/`section`/`section_intro`/`subsection` to each entity row matching by ID. Updates entities via `update_entity` MCP. Runs once during Group 12.

### Task 8.3: Test backlog projection byte-deterministic
- **Why:** AC-4.2
- **DoD:** Two consecutive `_project_backlog_md(db)` calls produce byte-identical output (SHA256 hash equality).

### Task 8.4: Test backlog projection has no datetime.utcnow calls
- **Why:** AC-4.2 static-check requirement
- **DoD:** `grep -nE "datetime\.(utcnow|now)\b"` against the `_project_backlog_md` function body returns no matches.

### Task 8.5: Test backlog projection regenerates byte-identical after delete
- **Why:** AC-4.4
- **DoD:** Delete `docs/backlog.md`, run `_project_backlog_md`, compare bytes to pre-delete capture.

### Task 8.6: Implement compare_backlog_projection.py + AC-4.2a test
- **Why:** Plan Group 8.6; AC-4.2a
- **DoD:** Script does whitespace-normalized diff between `_project_backlog_md(db)` output and current `docs/backlog.md`. Test asserts diff is empty (no semantic content drift).

## Group 9 — data_file_guards package

### Task 9.1: Implement dispatcher.py
- **Why:** Plan Group 9.1; Design §4.3
- **DoD:** `plugins/pd/hooks/lib/data_file_guards/dispatcher.py` per design §4.3 pseudocode. Reads stdin JSON; routes via `fnmatch.fnmatch`; uses `sys.path.insert(0, lib_dir)` + `importlib.import_module` per TD-3.

### Task 9.2: Implement meta_json_decision.py
- **Why:** Plan Group 9.2
- **DoD:** `decide(file_path, tool_name, payload) → dict` matching current meta-json-guard.sh decision logic (bootstrap sentinel check, permit/deny). All 4 existing meta-json-guard test paths produce equivalent outputs.

### Task 9.3: Implement backlog_decision.py
- **Why:** Plan Group 9.3
- **DoD:** Always denies Write/Edit/NotebookEdit on `docs/backlog.md`. Reason text contains `/pd:add-to-backlog` AND `update via DB then re-project` (AC-7.4).

### Task 9.4: Create data_file_guards.json config
- **Why:** Plan Group 9.4; FR-7.1
- **DoD:** File at `plugins/pd/hooks/data_file_guards.json` with exactly 2 entries matching spec FR-7.1 schema. `exclude_patterns` field present on first entry.

### Task 9.5: Create probe_fnmatch.py
- **Why:** Plan Group 9.5; Design TD-1
- **DoD:** Script at `plugins/pd/hooks/tests/probe_fnmatch.py` runs the 5-row Verified Behavior matrix from design TD-1 + exits nonzero on any deviation.

### Task 9.6: Test fnmatch behavior matches design TD-1 matrix
- **Why:** Plan Group 9.6
- **DoD:** pytest invokes probe + asserts exit 0; OR pytest directly asserts each TD-1 matrix row.

### Task 9.7: Test data_file_guards.json schema parse smoke
- **Why:** AC-7.1
- **DoD:** Test `json.loads(open('plugins/pd/hooks/data_file_guards.json').read())` succeeds; result is list with ≥ 2 entries; first entry has `pattern`, `exclude_patterns`, `decision_module`, `mcp_tool_hint` keys.

## Group 10 — data-file-guard.sh + hooks.json + test migration

### Task 10.1: Create data-file-guard.sh entrypoint
- **Why:** Plan Group 10.1; FR-7.2
- **DoD:** Script at `plugins/pd/hooks/data-file-guard.sh`. Executable bit set. Sources `lib/session-start-helpers.sh` for venv. On venv-load failure, exits 0 with empty hookSpecificOutput (allow). Invokes `python3 -m data_file_guards.dispatcher` with stdin piped. Uses `safe_emit_hook_json` per NFR-4.

### Task 10.2: Delete meta-json-guard.sh
- **Why:** Plan Group 10.2; FR-7.3, AC-7.6
- **DoD:** `git rm plugins/pd/hooks/meta-json-guard.sh`. `test -f plugins/pd/hooks/meta-json-guard.sh` returns nonzero.

### Task 10.3: Update hooks.json to register data-file-guard.sh
- **Why:** Plan Group 10.3; FR-7.4
- **DoD:** Exact old/new text edit per plan Group 10.3. Verify `grep -c meta-json-guard plugins/pd/hooks/hooks.json` returns 0; `grep -c data-file-guard plugins/pd/hooks/hooks.json` returns 1.

### Task 10.4: Create test-data-file-guard.sh and migrate 4 existing tests
- **Why:** Plan Group 10.4; FR-7.3 test migration callout
- **DoD:** New `plugins/pd/hooks/tests/test-data-file-guard.sh` with 4 migrated tests (deny-write, deny-edit, deny-project-meta [verifies AC-7.7 exclude], allow-non-meta) + new tests for AC-7.4 backlog deny, AC-7.5 hot-add via env overrides, AC-7.8 fail-open under venv-load failure. All tests pass.

### Task 10.5: Remove migrated meta-json-guard tests from test-hooks.sh
- **Why:** Plan Group 10.5
- **DoD:** `grep -c "meta_json_guard" plugins/pd/hooks/tests/test-hooks.sh` returns 0 post-edit. Total test count in test-hooks.sh reduced by 4.

### Task 10.6: Test hooks.json data-file-guard registered exactly once + meta-json-guard absent
- **Why:** AC-7.2, AC-7.6
- **DoD:** `grep -c '"data-file-guard.sh"' plugins/pd/hooks/hooks.json` returns 1; `grep -c '"meta-json-guard.sh"' plugins/pd/hooks/hooks.json` returns 0; `test -f plugins/pd/hooks/meta-json-guard.sh` returns nonzero.

### Task 10.7: Test meta-json deny path (AC-7.3)
- **Why:** AC-7.3 (parallel to AC-7.4 backlog deny tested in Task 10.4)
- **DoD:** Hook integration test in `test-data-file-guard.sh`: stdin Write tool call with file_path matching `*.meta.json` (outside projection path) → assert `permissionDecision=deny` AND reason text contains `complete_phase / transition_phase`.

## Group 11 — AST audit + F4-AUDIT comments

### Task 11.1: Add F4-AUDIT comment near _write_meta_json_fallback
- **Why:** Plan Group 11.1; FR-4.1, AC-1.1b
- **DoD:** Comment `# F4-AUDIT: degraded-mode-only` within 5 lines of `def _write_meta_json_fallback` at `engine.py:444`.

### Task 11.2: Add F4-AUDIT comment near init_project_state
- **Why:** Plan Group 11.2; FR-4.1
- **DoD:** Comment `# F4-AUDIT: project-type schema differs; ported to feature 111` within 5 lines of `def init_project_state` at `feature_lifecycle.py:223`.

### Task 11.3: Replace _fix_last_completed_phase + _fix_completed_timestamp with MCP wrappers
- **Why:** Plan Group 11.3; Design TD-11 (corrected symbol names)
- **DoD:** Both functions at `fix_actions.py:52` and `:87` replaced with bodies that invoke `complete_phase`/`transition_phase` MCP per TD-11 4-drift-class table. Each carries `# F4-AUDIT: MCP-routed (TD-11)` comment.

### Task 11.4: Add F4-AUDIT comment near _fix_backlog_annotation
- **Why:** Plan Group 11.4
- **DoD:** Comment `# F4-AUDIT: annotation-only; not state mutation` within 5 lines of `_fix_backlog_annotation` at `fix_actions.py:149`.

### Task 11.5: Implement test_no_unaudited_meta_json_writes
- **Why:** AC-1.1
- **DoD:** AST walk per spec AC-1.1 over `workflow_engine/`, `plugins/pd/mcp/`, `plugins/pd/hooks/lib/doctor/` (excl `*/tests/*`); allow-list `{_project_meta_json, _write_meta_json_fallback, init_project_state, _fix_last_completed_phase, _fix_completed_timestamp}`. Test FAILS if any unaudited writer found.

### Task 11.6: Implement test_no_unaudited_backlog_md_writes
- **Why:** AC-1.2
- **DoD:** Same AST walk pattern; allow-list `{_project_backlog_md, _fix_backlog_annotation}`. FAILS if unaudited writer found.

### Task 11.7: Implement audit comment proximity check
- **Why:** AC-1.1b
- **DoD:** Each allow-listed writer's enclosing function has `# F4-AUDIT:` comment within 5 lines of the write Call node.

### Task 11.8: Implement test for 4 TD-11 drift classes
- **Why:** AC-9.1 through AC-9.4 (design TD-11)
- **DoD:** One test per drift class row in TD-11 table: `lastCompletedPhase mismatch`, `status mismatch`, `branch field stale`, `unknown drift`. Each verifies the autofix routes through correct MCP or downgrades to WARN.

## Group 12 — Backlog writer port + cleanup_backlog modify

### Task 12.1: Modify add-to-backlog command to register-then-project
- **Why:** Plan Group 12.1; FR-4.3
- **DoD:** `plugins/pd/commands/add-to-backlog.md` Step 5 no longer uses Write tool to append to `docs/backlog.md`. Instead calls `register_entity(entity_type='backlog', entity_id=<next-id>-<slug>, metadata={"format":"table_row", "section":null, ...})`. Then invokes `_project_backlog_md` to regenerate file.

### Task 12.2: Modify finish-feature MED-finding emission
- **Why:** Plan Group 12.2; FR-4.3
- **DoD:** `plugins/pd/commands/finish-feature.md` Step 5b MED emission registers backlog entries via MCP (entity_type='backlog', metadata.format='bullet_item', metadata.section=<feature header>) then re-projects. Old direct Write block removed.

### Task 12.3: Modify cleanup_backlog.py to route through update_entity MCP
- **Why:** Plan Group 12.3; FR-4.3
- **DoD:** `plugins/pd/scripts/cleanup_backlog.py` archival path calls `update_entity(type_id, status='archived')` instead of direct file write. Post-archival, calls `_project_backlog_md` to regenerate.

### Task 12.4: Run backfill parser against current backlog.md
- **Why:** Plan Group 12.4; Design TD-10 backfill rule
- **DoD:** Script from Task 8.2 executed against current `docs/backlog.md`. Every existing backlog entity row has `metadata.format`/`section`/`section_intro`/`subsection` set per parsed structure. DB committed.

### Task 12.5: Re-run AST audit test post-port (regression gate)
- **Why:** Plan Group 12.5; AC-1.2
- **DoD:** `test_no_unaudited_backlog_md_writes` passes post-Group 12 edits — confirms no leftover Write tool calls to backlog.md outside the projection path.

## Group 13 — .gitignore tracked-copy removal

### Task 13.1: git rm --cached for 132 .meta.json files
- **Why:** Plan Group 13.1; FR-4.5, AC-1.5
- **DoD:** Pre-task: `git ls-files docs/features/*/.meta.json | wc -l` returns 132. Run `git rm --cached docs/features/*/.meta.json`. Post-task: same query returns 0. If pre-task returns 0 (fresh worktree edge case per spec FR-4.5), skip without error.

### Task 13.2: git rm --cached docs/backlog.md
- **Why:** Plan Group 13.2; AC-1.5
- **DoD:** Same defense-in-depth pattern. Post-task: `git ls-files docs/backlog.md` returns 0.

### Task 13.3: Test .gitignore contains required patterns
- **Why:** AC-1.4
- **DoD:** Test reads `.gitignore`, asserts all 3 patterns present (`**/.meta.json`, `docs/backlog.md`, `pd-state.diff.md`).

### Task 13.4: Test no tracked data files post-commit
- **Why:** AC-1.5
- **DoD:** `git ls-files | grep -E "(\.meta\.json|^docs/backlog\.md|^pd-state\.diff\.md)$"` returns 0 lines.

## Group 14 — pd_state_diff.py + pre-commit modify

### Task 14.1: Implement pd_state_diff.py
- **Why:** Plan Group 14.1; Design §4.1 algorithm + TD-9 format
- **DoD:** Script at `plugins/pd/scripts/pd_state_diff.py`. Implements phase_events-replay algorithm + backfilled-entity defense per design §4.1 step 3. Output uses parent_uuid (8-char prefix) per design rev-3.

### Task 14.2: Test clean checkout emits no changes
- **Why:** AC-6.1
- **DoD:** Run script against clean checkout; assert output is the literal `No entity state changes vs {base}` line.

### Task 14.3: Test added entity marked
- **Why:** AC-6.2
- **DoD:** Synthetic register_entity post-HEAD; rerun; assert row with new uuid + `(added)` marker.

### Task 14.4: Test missing base ref exits 0
- **Why:** AC-6.6
- **DoD:** With invalid `--base nonexistent`, script writes `pd-state diff unavailable: base ref 'nonexistent' not found` and exits 0.

### Task 14.5: Test performance median under 500ms
- **Why:** AC-6.5
- **DoD:** Median-of-5 timed runs (after 1 warm-up) against 500-row fixture DB. Median < 500ms; no single run > 1500ms (hard outlier cap). Test harness modeled on `bench-session-start.sh`.

### Task 14.6: Modify pre-commit-guard.sh per design FR-4.6
- **Why:** Plan Group 14.6
- **DoD:** Existing `plugins/pd/hooks/pre-commit-guard.sh` has new block appended AFTER existing branch-protection logic: sources `lib/session-start-helpers.sh` to load venv; invokes `python3 -m pd_state_diff --base ${pd_base_branch:-main}` writing stdout to `${PROJECT_ROOT}/pd-state.diff.md`; on script failure, emits stderr warn-line and exits 0 (does not block commit per AC-6.6).

### Task 14.7: Test pre-commit hook emits diff file
- **Why:** AC-6.3
- **DoD:** Test invokes `pre-commit-guard.sh` with synthetic stdin (Bash tool, `git commit -m ...`); after, `pd-state.diff.md` exists at repo root. File is gitignored (per Task 0.1 + AC-1.4).

### Task 14.8: Test backfilled-entity defense (no entity_created event)
- **Why:** Plan Group 14.8; Design §4.1 step 3 fallback
- **DoD:** Fixture entity with `created_at <= base_commit_ts` AND no `phase_events` row with `event_type='entity_created'`; script treats as no-change (does NOT emit row).

### Task 14.9: Test empty-tree branch run emits literal no-changes line
- **Why:** AC-6.4
- **DoD:** Fresh repo with empty DB (zero entities); run script; output is the literal `No entity state changes vs {base}` line.

## Group 15 — Down-migration + AC-5.5 round-trip + TD-7b lint

### Task 15.1: Implement _migration_13_entity_display_down body
- **Why:** Plan Group 15.1; FR-5.4
- **DoD:** DROP entity_display, DROP idx_entity_display_seq, DROP migration_audit_log (IF EXISTS). `PRAGMA user_version = 12`. DELETE FROM schema_version WHERE version=13.

### Task 15.2: Test down-migration drops artifacts
- **Why:** AC-5.4
- **DoD:** Post-down: `sqlite_master` shows none of the 3 dropped artifacts. `PRAGMA user_version` returns 12. schema_version table has no version=13 row.

### Task 15.3: Test up-down round-trip byte-identical
- **Why:** AC-5.5
- **DoD:** 100-row fixture DB. Capture `.dump` of `entities`, `workflow_phases`, `phase_events`. Run migration 13 up. Run migration 13 down. Re-capture `.dump`. Assert byte-identical.

### Task 15.4: Implement entity_id parsing audit lint
- **Why:** Plan Group 15.4; Design TD-7b + §5 invariant
- **DoD:** Test `test_audit_writes.py::test_entity_id_parsing_audit_lint` runs `grep -rnE '\.split\(":"\)|substr\(.*entity_id|instr\(.*entity_id'` over `plugins/pd/hooks/lib/`, `plugins/pd/mcp/`. Asserts all hits are inside (i) `_migration_13_*` functions, OR (ii) test files (`test_*.py`). Any other hit FAILS the test.
