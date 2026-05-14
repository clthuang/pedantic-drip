# Plan — Feature 110: Markdown Projections and Generalized Guards

- **Spec:** rev 4 | **Design:** rev 3
- **Sub-features:** F4 (sealed projection write path), F7 (generalized data-file guard), F8 (entity_display table)
- **Schema baseline:** post-migration-12 (entity_type column dropped; type/kind/lifecycle_class present)
- **Status:** revision 1

## Dependency Graph

```
Group 0 (scaffolding) ──┐
                         │
Group 1 (pre-flight gate) ──► Group 2 (migration 13: entity_display table)
                                  │
                                  ├──► Group 3 (pre-audit + migration_audit_log)
                                  │
                                  └──► Group 4 (scan_entity_ids port)
                                        │
                                        ├──► Group 5 (_project_meta_json read entity_display)
                                        │
                                        └──► Group 6 (backfill.py port)
                                              │
                                              └──► Group 7 (rename test AC-8.6)

Group 8 (_project_backlog_md) ──► Group 12 (backlog writer port + cleanup_backlog modify)
                                        │
                                        └──► Group 13 (.gitignore + tracked-copy removal)

Group 9 (data_file_guards package) ──► Group 10 (data-file-guard.sh + hooks.json)
                                              │
                                              └──► Group 11 (AST audit + F4-AUDIT comments)

Group 14 (pd_state_diff.py + pre-commit modify) — independent of 9/10/11; depends on 5

Group 15 (down-migration + AC-5.5 round-trip) — depends on 2,3
```

**Parallelizable opportunities:** Groups 9 + 14 can proceed independently. Groups 5/6 can be done in any order after 4. Group 8 is independent of F8 chain.

## Plan Items by Group

### Group 0 — Scaffolding (~30 min)
- **0.1** Append `**/.meta.json`, `docs/backlog.md`, `pd-state.diff.md` to `.gitignore` (FR-4.5, AC-1.4). Verify via `cat .gitignore | grep -E "^(\\*\\*/\\.meta\\.json|docs/backlog\\.md|pd-state\\.diff\\.md)$" | wc -l` returns 3.
- **0.2** Create empty package init `plugins/pd/hooks/lib/data_file_guards/__init__.py`.
- **0.3** Create `plugins/pd/hooks/tests/fixtures/` directory + placeholder fixture files (`test_data_file_guards.json`, `fixture_guard.py`, `fixture_decision.py`).

### Group 1 — Migration 13 stub + pre-flight gate (~60 min)
- **1.1** Add `_migration_13_entity_display(conn)` stub in `plugins/pd/hooks/lib/entity_registry/database.py`. Function body: just runs FR-5.5 pre-flight gate (3-check sequence per design TD-6), aborts on any failure. Registered in `MIGRATIONS[13]`.
- **1.2** Add `_migration_13_entity_display_down(conn)` stub. Registered in `MIGRATIONS_DOWN[13]`.
- **1.3** Test `test_migration_13_safety.py::test_pre_flight_aborts_on_stale_schema` (AC-5.6, AC-5.6b, AC-5.6c): synthetic fixture DBs for 3 stale shapes, assert migration ABORTS with appropriate error per design TD-6.
- **1.4** Test `test_migration_13_safety.py::test_pre_flight_passes_on_clean_post_12_db`: fresh post-12 fixture, assert migration proceeds past gate.

### Group 2 — entity_display table + index + backfill (~90 min)
- **2.1** Implement `_migration_13_entity_display` body inside `BEGIN IMMEDIATE` per design FR-5.1: `PRAGMA foreign_key_check` pre-commit; `CREATE TABLE entity_display(uuid PK, seq, slug, FK ON DELETE CASCADE)`; `CREATE INDEX idx_entity_display_seq`; idempotency early-return per FR-5.2; `PRAGMA user_version = 13` + INSERT into schema_version per FR-5.3.
- **2.2** Backfill INSERT inside same transaction per FR-8.2: `PRAGMA table_info(entities)` runtime introspection (FR-5.6) to confirm `uuid`, `entity_id`, `metadata` columns present; then `INSERT INTO entity_display SELECT uuid, CAST(substr(entity_id, 1, instr(entity_id, '-') - 1) AS INTEGER), substr(entity_id, instr(entity_id, '-') + 1) FROM entities`.
- **2.3** Test `test_migration_13_safety.py::test_entity_display_created_with_correct_schema` (AC-8.1).
- **2.4** Test `test_entity_display_table.py::test_backfill_1to1_with_entities` (AC-8.2).
- **2.5** Test `test_entity_display_table.py::test_backfill_seq_slug_match_entity_id_suffix` (AC-8.3).
- **2.6** Test `test_migration_13_safety.py::test_migration_13_idempotent_replay` (AC-5.2).
- **2.7** Test `test_migration_13_safety.py::test_user_version_and_schema_version_table_set` (AC-5.3).

### Group 3 — Pre-audit + migration_audit_log (~60 min)
- **3.1** Create `migration_audit_log` table inside migration 13 transaction (FR-8.2-pre per design TD-2):
   ```sql
   CREATE TABLE IF NOT EXISTS migration_audit_log (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     migration_version INTEGER NOT NULL,
     event_type TEXT NOT NULL,
     payload TEXT NOT NULL,
     created_at TEXT NOT NULL
   );
   ```
- **3.2** Implement pre-audit SELECT inside migration 13 (FR-8.2-pre); log mismatch rows to `migration_audit_log` with `event_type='mismatch_row'`.
- **3.3** Implement env-var bypass: if mismatch count > 0 AND `os.environ.get('PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS') != '1'`, raise with UUID list. Otherwise INSERT `event_type='bypass_acknowledged'` row with payload `{"mismatch_count": N, "user": getpass.getuser(), "ts": ISO_TS}`.
- **3.4** Test `test_entity_display_table.py::test_pre_audit_clean_db_zero_mismatches` (AC-8.0).
- **3.5** Test `test_entity_display_table.py::test_pre_audit_mismatch_aborts_without_env_bypass`.
- **3.6** Test `test_entity_display_table.py::test_pre_audit_mismatch_with_env_bypass_writes_forensic_rows`.

### Group 4 — scan_entity_ids port (~30 min)
- **4.1** Modify `scan_entity_ids` in `plugins/pd/hooks/lib/entity_registry/database.py:899-906` (FR-8.3a). New SQL: `SELECT COALESCE(MAX(seq), 0) FROM entity_display d JOIN entities e ON d.uuid = e.uuid WHERE e.workspace_uuid = ?`. Replaces regex-on-entity_id.
- **4.2** Test `test_entity_display_table.py::test_scan_entity_ids_uses_entity_display` (AC-8.4) — assert post-migration `scan_entity_ids` returns same max_seq as pre-migration.

### Group 5 — _project_meta_json reads entity_display (~30 min)
- **5.1** Modify `_project_meta_json` in `plugins/pd/mcp/workflow_state_server.py:373,416-418` (FR-8.3b): replace `metadata.get('id')` / `metadata.get('slug')` with JOIN against `entity_display`. Fallback to `metadata` JSON with WARN if entity_display row missing (defense-in-depth).
- **5.2** Test `test_projection_determinism.py::test_meta_json_reads_entity_display` (AC-8.5) — delete `id`/`slug` from `metadata` JSON, re-project, assert output unchanged.

### Group 6 — backfill.py port (~20 min)
- **6.1** Modify `plugins/pd/hooks/lib/entity_registry/backfill.py` to query `entity_display` instead of parsing `entity_id`. Exact old/new text pairs:

**Old (backfill.py — find via grep `re\.match.*entity_id|substr.*entity_id`):**
```python
match = re.match(r"^(\d+)-(.+)", entity_id)
seq, slug = int(match.group(1)), match.group(2)
```

**New:**
```python
row = conn.execute("SELECT seq, slug FROM entity_display WHERE uuid = ?", (uuid,)).fetchone()
if row is None:
    log.warning(f"entity_display row missing for {uuid}; falling back to entity_id parse")
    match = re.match(r"^(\d+)-(.+)", entity_id)
    seq, slug = int(match.group(1)), match.group(2)
else:
    seq, slug = row["seq"], row["slug"]
```

### Group 7 — Rename test + AC-8.6 (~30 min)
- **7.1** Test `test_entity_display_table.py::test_slug_rename_no_entities_table_drift` (AC-8.6): `UPDATE entity_display SET slug='renamed' WHERE uuid = ?` → assert sqlite3 `.dump` of `entities WHERE uuid = ?` byte-identical pre/post; assert full `phase_events` dump byte-identical.
- **7.2** Test `test_entity_display_table.py::test_slug_rename_child_parent_link_intact` (AC-8.7).

### Group 8 — _project_backlog_md function (~90 min)
- **8.1** Add `_project_backlog_md(db) → str` in `plugins/pd/mcp/workflow_state_server.py` per design §4.5. Two-format emission per design TD-10 (flat table for `metadata.format='table_row'`; bullets for `format='bullet_item'`).
- **8.2** Backfill parser: one-shot script parses existing `docs/backlog.md`, assigns `metadata.format`/`section`/`section_intro`/`subsection` per design TD-10 backfill rule. Runs inside migration 13 or as Group 0 setup (decided here: runs in Group 12 alongside the writer-port; Group 0 only creates the empty fixture).
- **8.3** Test `test_projection_determinism.py::test_backlog_md_byte_deterministic` (AC-4.2).
- **8.4** Test `test_projection_determinism.py::test_backlog_md_no_datetime_now_calls` (AC-4.2 static check).
- **8.5** Test `test_projection_determinism.py::test_backlog_md_regenerate_after_delete` (AC-4.4).
- **8.6** Test `compare_backlog_projection.py` script + AC-4.2a whitespace-normalized comparison against current `docs/backlog.md`.

### Group 9 — data_file_guards package (~90 min)
- **9.1** Implement `plugins/pd/hooks/lib/data_file_guards/dispatcher.py` per design §4.3.
- **9.2** Implement `plugins/pd/hooks/lib/data_file_guards/meta_json_decision.py` (re-implements meta-json-guard.sh logic per design §1.1 — checks bootstrap sentinel, permit/deny based on sentinel state).
- **9.3** Implement `plugins/pd/hooks/lib/data_file_guards/backlog_decision.py` (denies direct Write/Edit; reason text mentions `/pd:add-to-backlog or update via DB then re-project`).
- **9.4** Create `plugins/pd/hooks/data_file_guards.json` with the two FR-7.1 entries.
- **9.5** Create `plugins/pd/hooks/tests/probe_fnmatch.py` per design TD-1 (commits fnmatch verified-behavior matrix as executable test).
- **9.6** Test `test_data_file_guards.py::test_fnmatch_matches_per_design_td1` (verifies the TD-1 matrix).

### Group 10 — data-file-guard.sh + hooks.json (~60 min)
- **10.1** Create `plugins/pd/hooks/data-file-guard.sh` per design §4.2 contract: sources `lib/session-start-helpers.sh` (venv load); on venv-fail, exits 0 with allow (R6 fail-open per AC-7.8); else invokes `python3 -m data_file_guards.dispatcher`.
- **10.2** DELETE `plugins/pd/hooks/meta-json-guard.sh` (FR-7.3, AC-7.6).
- **10.3** Modify `plugins/pd/hooks/hooks.json` (NOT `.claude-plugin/hooks.json` per spec rev-4 correction). Exact old/new:

**Old (find via grep `meta-json-guard`):**
```json
{
  "hooks": [{"type": "command", "command": "${CLAUDE_PROJECT_DIR}/plugins/pd/hooks/meta-json-guard.sh"}]
}
```

**New:**
```json
{
  "hooks": [{"type": "command", "command": "${CLAUDE_PROJECT_DIR}/plugins/pd/hooks/data-file-guard.sh"}]
}
```

- **10.4** Create `plugins/pd/hooks/tests/test-data-file-guard.sh`. Migrate 4 existing meta-json-guard tests from `test-hooks.sh` (FR-7.3 explicit callout); add tests for backlog deny path (AC-7.4); add hot-add test using `PD_DATA_FILE_GUARDS_CONFIG`+`PD_DATA_FILE_GUARDS_LIB` fixtures (AC-7.5); add fail-open venv test (AC-7.8); add project-path exclude test (AC-7.7).
- **10.5** Remove migrated tests from `plugins/pd/hooks/tests/test-hooks.sh`.

### Group 11 — AST audit + F4-AUDIT comments (~60 min)
- **11.1** Add `# F4-AUDIT: degraded-mode-only` comment within 5 lines of `_write_meta_json_fallback` at `engine.py:444` (FR-4.1).
- **11.2** Add `# F4-AUDIT: project-type schema differs; ported to feature 111` comment near `init_project_state` at `feature_lifecycle.py:223` (FR-4.1, design §2.3).
- **11.3** Replace `_fix_last_completed_phase` body at `fix_actions.py:52` AND `_fix_completed_timestamp` body at `fix_actions.py:87` with MCP-invoking wrappers per design TD-11 (4 drift classes). Each wrapper has `# F4-AUDIT: MCP-routed (TD-11)` comment.
- **11.4** Add `# F4-AUDIT: annotation-only; not state mutation` comment near `_fix_backlog_annotation` at `fix_actions.py:149`.
- **11.5** Implement `test_audit_writes.py::test_no_unaudited_meta_json_writes` (AC-1.1) — AST walk per design §4.7 (AC-1.1) with allow-list `{_project_meta_json, _write_meta_json_fallback, init_project_state, _fix_last_completed_phase, _fix_completed_timestamp}`. Same-function fp scope per AC-1.1 limitation note.
- **11.6** Implement `test_audit_writes.py::test_no_unaudited_backlog_md_writes` (AC-1.2) with allow-list `{_project_backlog_md, _fix_backlog_annotation}`.
- **11.7** Implement `test_audit_writes.py::test_no_unaudited_meta_json_writes_have_audit_comment` (AC-1.1b proximity check).
- **11.8** Implement `test_audit_writes.py::test_drift_classes_per_td11` (AC-9.1 through AC-9.4 — one assertion per design TD-11 drift class row).

### Group 12 — Backlog writer port + cleanup_backlog modify (~60 min)
- **12.1** Modify `plugins/pd/commands/add-to-backlog.md` Step 5 (currently at lines 51-59 per design §1.1) to: (a) `register_entity(entity_type='backlog', entity_id=<next-id>-<slug>, metadata={"format":"table_row", "section":null})`, (b) invoke `_project_backlog_md` to regenerate `docs/backlog.md`. NO direct file Write.
- **12.2** Modify `plugins/pd/commands/finish-feature.md` Step 5b MED-finding emission (line 414) to use the same pattern: register backlog entries with appropriate `metadata.format` / `section` then re-project.
- **12.3** Modify `plugins/pd/scripts/cleanup_backlog.py` per design §2.3: route archival through existing `update_entity(type_id, status='archived')` MCP (NO new archive_entity MCP added); call `_project_backlog_md` post-archival.
- **12.4** Run one-shot backfill parser (Group 8.2 deliverable) against current `docs/backlog.md`: assigns `metadata.format`/`section`/`section_intro`/`subsection` to each existing backlog entity row. Commit the resulting DB state diff.
- **12.5** Test `test_audit_writes.py::test_no_unaudited_backlog_md_writes` re-run after Group 12 (AC-1.2 verifies no leftover writes after port).

### Group 13 — .gitignore tracked-copy removal (~30 min)
- **13.1** Run `git rm --cached docs/features/*/.meta.json` (132 files per spec FR-4.5). If `git ls-files docs/features/*/.meta.json` returns zero (fresh-worktree edge case), skip without error per spec FR-4.5.
- **13.2** Run `git rm --cached docs/backlog.md`. Same zero-tracked defense.
- **13.3** Test `test_gitignore_drift.py::test_gitignore_contains_required_patterns` (AC-1.4).
- **13.4** Test `test_gitignore_drift.py::test_no_tracked_data_files_post_commit` (AC-1.5).

### Group 14 — pd_state_diff.py + pre-commit modify (~120 min)
- **14.1** Implement `plugins/pd/scripts/pd_state_diff.py` per design §4.1 algorithm (phase_events-replay + backfilled-entity defense per design step 3 update). Output per design TD-9 (with `parent_uuid` column, not `parent_type_id` per design rev-3 correction).
- **14.2** Test `test_pd_state_diff.py::test_clean_checkout_emits_no_changes` (AC-6.1).
- **14.3** Test `test_pd_state_diff.py::test_added_entity_marked` (AC-6.2).
- **14.4** Test `test_pd_state_diff.py::test_missing_base_ref_exits_0` (AC-6.6).
- **14.5** Test `test_pd_state_diff.py::test_performance_median_under_500ms` (AC-6.5) — median-of-5 with 1 warm-up, fixture DB 500 rows, hard 1500ms outlier cap.
- **14.6** Modify `plugins/pd/hooks/pre-commit-guard.sh` per design FR-4.6 / TD-5: append-after-existing pattern — source `lib/session-start-helpers.sh`, invoke `python3 -m pd_state_diff --base ${pd_base_branch:-main}`, write stdout to `${PROJECT_ROOT}/pd-state.diff.md`, fail-open exit 0 on script failure.
- **14.7** Test `test_pd_state_diff.py::test_pre_commit_hook_emits_diff_file` (AC-6.3).
- **14.8** Test `test_pd_state_diff.py::test_backfilled_entity_defense` — entity without phase_events history treated as no-change (design §4.1 step 3 update).

### Group 15 — Down-migration + AC-5.5 round-trip (~45 min)
- **15.1** Implement `_migration_13_entity_display_down(conn)` body: DROP `entity_display`, DROP `idx_entity_display_seq`, DROP `migration_audit_log` (if exists). Decrement `user_version` to 12. DELETE row from schema_version where version=13.
- **15.2** Test `test_migration_13_safety.py::test_down_migration_drops_artifacts` (AC-5.4).
- **15.3** Test `test_migration_13_safety.py::test_up_down_round_trip_byte_identical` (AC-5.5): 100-row fixture DB, up → down, assert `entities`, `workflow_phases`, `phase_events` `.dump` byte-identical to pre-up.
- **15.4** Test `test_audit_writes.py::test_entity_id_parsing_audit_lint` (TD-7b lint AC, design §5 invariant): `grep` for entity_id parsing returns hits ONLY in `_migration_13_*` functions and `test_*.py` files.

## Risks (carried from design §6)

| Risk | Plan AC |
|---|---|
| R3 Backfill mismatch | Group 3.5, 3.6 |
| R4 perf flake | Group 14.5 median-of-5 |
| R5 Doctor autofix regression | Group 11.8 — 4 drift classes |
| R6 venv-load failure | Group 10.4 fail-open test |
| R7 (resolved): algorithm committed | Group 14.5 perf gate |
| R8 backlog projection vs add-to-backlog flow | Group 12.1 (porting) + Group 12.5 (AST verify) |
| R9 Live DB stale schema | Group 1.3 — 3 pre-flight tests |

## Open Questions Resolved at Plan Phase

- **Backfill parser placement (Group 8.2):** Runs in Group 12.4 alongside the writer-port (NOT inside migration 13 transaction — keeps migration transaction focused on schema; parsing operates on stable post-migration DB).
- **`/pd:cleanup-backlog` command fate:** Retained; modified to route through `update_entity` MCP per design §2.3.
- **Test fixture entity_id format constraint:** Test fixtures using `register_entity` with non-standard entity_ids (no `{seq}-{slug}` form) must be either (a) migrated to standard form, or (b) use a new `_register_entity_no_display` test-only helper. Group 2 audits + ports test fixtures as needed.
