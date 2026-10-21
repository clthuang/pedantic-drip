# Tasks: pd Data-Model + Memory Hardening (Feature 114)

**Plan source:** `plan.md`
**Design source:** `design.md`

Tier-grouped task list. Each task: 5-15 min target. Dependencies pinned. TDD pattern: write tests first (RED), implement (GREEN), refactor (REFACTOR).

---

## Tier 1: Foundational guards + fixtures (parallel within tier)

### Group A.6: Fixture SQL scripts

- [ ] **T1.1**: Create `plugins/pd/hooks/lib/entity_registry/fixtures/` directory
- [ ] **T1.2**: Write `fixtures/m12_stub_trap.sql` — schema_version=12, pre-M12 entities table (entity_type present; type/kind/lifecycle_class absent), 3 seed entity rows
- [ ] **T1.3**: Write `fixtures/pre_m11.sql` — schema_version=10, no workspace_uuid column, 3 seed rows
- [ ] **T1.4**: Write `fixtures/post_m12.sql` — schema_version=12, post-M12 layout (type/kind/lifecycle_class present; entity_type absent), 3 seed rows
- [ ] **T1.5**: Write `fixtures/m12_partial.sql` — schema_version=12, type column present but kind/lifecycle_class absent (mid-application state)
- [ ] **T1.6**: Write `test_fixtures.py` — each fixture loadable via `sqlite3 :memory: <fixture.sql`, asserts expected `PRAGMA table_info` and `SELECT value FROM _metadata WHERE key='schema_version'`

### Group A: M12 guard + fingerprint detector + remediation CLI

- [ ] **T2.1** (RED): Add `test_compute_schema_fingerprint_pre_m12` to `test_database.py` — load fixture, compute fingerprint, assert stable across 2 runs
- [ ] **T2.2** (RED): Add `test_compute_schema_fingerprint_post_m12` to `test_database.py` — same against post_m12 fixture, assert different from pre_m12
- [ ] **T2.3** (GREEN): Implement `_compute_schema_fingerprint(conn)` in `database.py` per IF-1 (whitespace-normalized SQL, name-sorted columns, sha256)
- [ ] **T2.4** (GREEN): Add `_normalize_sql(s)` helper — strip comments, collapse whitespace
- [ ] **T2.5** (RED): Add `test_m12_guard_post_m12_returns_early`, `test_m12_guard_pre_m12_falls_through`, `test_m12_guard_stub_trap_falls_through` to `test_database.py`
- [ ] **T2.6** (GREEN): Modify M12 guard at `database.py:2683` — verify fingerprint before trusting stamp
- [ ] **T2.7**: Compute `_PRE_M12_FINGERPRINT` and `_POST_M12_FINGERPRINT` against fixtures; hardcode as module constants in `database.py`. **Procedure**:
  1. Load fixtures: `sqlite3 /tmp/pre_m12.db < plugins/pd/hooks/lib/entity_registry/fixtures/m12_stub_trap.sql` and same for `post_m12.sql` → `/tmp/post_m12.db`.
  2. Compute: `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c "import sqlite3; from entity_registry.database import _compute_schema_fingerprint; print('PRE:', _compute_schema_fingerprint(sqlite3.connect('/tmp/pre_m12.db'))); print('POST:', _compute_schema_fingerprint(sqlite3.connect('/tmp/post_m12.db')))"`.
  3. Hardcode the two 64-char hex strings as module constants near `_compute_schema_fingerprint` definition.
  4. Verify stability: re-run step 2; outputs MUST match exactly.
- [ ] **T2.8** (RED): Add `test_m13_abort_messages_include_cli_command` — assert all 4 M13 abort RuntimeError strings contain `python -m plugins.pd.hooks.lib.entity_registry.remediate_m12`
- [ ] **T2.9** (GREEN): Update 4 M13 abort messages at `database.py:4027, 4052, 4088, 4112` to embed CLI command
- [ ] **T2.10** (RED): Create `test_remediate_m12.py` — test stub-trap fixture → recovery; already-recovered → no-op; partial → abort with diagnostic
- [ ] **T2.11** (GREEN): Create `plugins/pd/hooks/lib/entity_registry/remediate_m12.py` with `main()` per IF-6
- [ ] **T2.12** (GREEN): Add `_migration_12_polymorphic_taxonomy_and_events_force(conn)` body wrapper that skips idempotency guard (callable from CLI)
- [ ] **T2.13** (GREEN): Add `_diff_fingerprints(conn, expected_fingerprint)` helper for diagnostic output
- [ ] **T2.14** (RED): Add doctor `test_fix_m12_stub_trap` to `test_fix_actions.py` — fixture in stub-trap state, fix function executes recovery
- [ ] **T2.15** (GREEN): Add `_fix_m12_stub_trap(ctx, issue) -> str` to `doctor/fix_actions.py` per IF-7
- [ ] **T2.16** (GREEN): Register fix_action with doctor harness; add detection check that emits warning Issue with fix_hint

### Group M11: M11 guard tightening

- [ ] **T3.1** (RED): Add `test_m11_guard_returns_early_when_workspace_uuid_present` + `test_m11_guard_falls_through_when_absent` to `test_database.py`
- [ ] **T3.2** (GREEN): Modify M11 guards at `database.py:1818, 1899` to add column-presence probe before early-return

---

## Tier 2: Workspace fallback

### Group D

- [ ] **T4.1**: Create `plugins/pd/hooks/lib/_log_helpers.py` with `log_stderr_json(tag, payload)` per IF-4
- [ ] **T4.2** (RED): Add `test_complete_phase_legacy_unknown_workspace` to `test_complete_phase_closes.py` — entity registered with `_UNKNOWN_WORKSPACE_UUID`, server `_workspace_uuid=<fresh UUID>`, expect success (post-fix)
- [ ] **T4.3** (RED): Add `test_complete_phase_arbitrary_cross_workspace_fails` — entity in ws-A, server `_workspace_uuid=<ws-B>`, expect `EntityNotFoundError`
- [ ] **T4.4** (RED): Add `test_complete_phase_fallback_logs_to_stderr` — assert stderr contains `pd.workspace.legacy_fallback` JSON tag with all 4 fields
- [ ] **T4.5** (GREEN): Rewrite `workflow_state_server.py:1184-1192` per FR-D.1 pseudocode (two-pass with strict `_UNKNOWN_WORKSPACE_UUID` gating)
- [ ] **T4.6** (GREEN): Replace `entity_server.py:562` and `:704` `or ""` with `or _UNKNOWN_WORKSPACE_UUID`
- [ ] **T4.7** (REFACTOR): Verify no other `_workspace_uuid or ""` patterns remain via grep

---

## Tier 3: Audit invariant + AST whitelist removal

### Group C.1: Emit insertion

- [ ] **T5.1** (RED): Add `test_update_entity_emits_entity_status_changed` to `test_database.py` — `db.update_entity(uuid, status='completed')` produces exactly one new phase_events row with `event_type='entity_status_changed'` AND metadata `{old_status, new_status}`
- [ ] **T5.2** (RED): Add `test_update_entity_emit_fails_open` — mock `append_phase_event` to raise; assert (a) status UPDATE succeeded, (b) stderr `pd.audit.emit_failed` JSON tag, (c) `_metadata.audit_emit_failed_count` incremented, (d) no exception propagated
- [ ] **T5.3** (RED): Add `test_update_entity_no_op_no_emit` — same-status UPDATE produces 0 new entity_status_changed rows
- [ ] **T5.4** (RED): Add `test_update_entity_counter_write_fail_open` — mock counter UPDATE to raise; assert secondary `pd.audit.counter_write_failed` stderr line + outer emit still attempted
- [ ] **T5.5** (GREEN): Modify `update_entity` (`database.py:7094-7236`) — add post-UPDATE emit block per C10.1
- [ ] **T5.6** (REFACTOR): Verify status UPDATE happens before emit (already committed by the time emit fires)

### Group C.2: F111 manual emit removal (**MUST be SAME COMMIT as C.1 / T5.5** — design risk R-D1)

- [ ] **T6.1** (RED): Add `test_complete_phase_closes_no_double_emit` — after FR-C lands, single emit per closure
- [ ] **T6.2** (GREEN): Remove manual `db.append_phase_event(event_type='entity_status_changed')` block at `workflow_state_server.py:1344-1356`
- [ ] **T6.3** (verify): Run `test_complete_phase_closes.py` full suite — `closed_by_uuid` no longer in metadata; assert via entity_relations correlation test

### Group C.3: Migration 15

- [ ] **T7.1** (RED): Add `test_migration_15_initializes_counter` — fresh DB → run M15 → assert `audit_emit_failed_count=0`
- [ ] **T7.2** (RED): Add `test_migration_15_resets_existing_counter` — DB with `audit_emit_failed_count=5` → run M15 → assert reset to 0
- [ ] **T7.3** (RED): Add `test_migration_99_does_not_touch_counter` — synthetic M99 that mutates other `_metadata` keys → assert `audit_emit_failed_count` preserved
- [ ] **T7.4** (GREEN): Add `_migration_15_audit_emit_counter(conn)` in `database.py`; register in `MIGRATIONS` dict
- [ ] **T7.5**: Verify M14 still head pre-implement (`grep -cE "_migration_1[5-9]" database.py == 0`)

### Group C.4: AST audit check

- [ ] **T8.1** (RED): Add `test_check_audit_counter_write_path_detects_violations` to `test_check_audit_counter_write_path.py` — synthetic migration body that mutates `audit_emit_failed_count` → AST check fails
- [ ] **T8.2** (GREEN): Create `plugins/pd/hooks/lib/doctor/check_audit_counter_write_path.py` mirroring `check_status_write_path.py` pattern
- [ ] **T8.3** (GREEN): Register check in `doctor/__init__.py`'s CHECK_ORDER list

### Group C.5: Test fixture sweep + whitelist removal

- [ ] **T9.1**: Enumerate test files calling `update_entity(status=...)`: `/opt/homebrew/bin/rg -nU "update_entity\([^)]*status=" plugins/pd/ -g '*.py' -g '!.venv/**'` — subtract the 17 production callers from Pin F.1; remaining paths = test sweep targets. Record list as a scratch comment in `_PERMITTED_TEST_FILES` definition site. Bounds check: if test-caller count > 10, pause and surface to user before proceeding.
- [ ] **T9.2**: For each test file: either refactor to `upsert_entity`/`promote_entity` OR add to `_PERMITTED_TEST_FILES` frozenset
- [ ] **T9.3**: Define `_PERMITTED_TEST_FILES: frozenset[str]` in `check_status_write_path.py` with project-root-relative POSIX paths
- [ ] **T9.4**: Update `check_status_write_path._enclosing_def_at_line` (or equivalent) to consult `_PERMITTED_TEST_FILES` before flagging
- [ ] **T9.5** (RED): Add `test_check_status_write_path_respects_permitted_test_files` — flagged test file at allowlisted path → no violation
- [ ] **T9.6** (GREEN): Remove `'update_entity'` from `_PERMITTED_ENCLOSING_DEFS` at `check_status_write_path.py:37`
- [ ] **T9.7** (verify): Bounds check — re-run Pin F.1 multi-line rg; if >20 results, pause and surface to user
- [ ] **T9.8** (verify): Full `pytest plugins/pd/` passes

---

## Tier 4-pre: B-H4.0 manifest freeze (implement-phase only)

- [ ] **T10.1**: Create `plugins/pd/hooks/lib/semantic_memory/recompute_source_hash.py` with `recompute_all(db, dry_run=True)` per IF-5 (including NULL/empty handling)
- [ ] **T10.2** (RED): Add `test_recompute_all_handles_null_description` — null-description row counted in `null_or_empty_skipped`, not in `shifted_ids`
- [ ] **T10.3** (RED): Add `test_recompute_all_dry_run_writes_nothing` — verify with row-count and source_hash equality before/after
- [ ] **T10.4**: Run dry-run against production memory.db:
  ```
  PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c \
    "from semantic_memory.recompute_source_hash import recompute_all; \
     from semantic_memory.database import MemoryDatabase; \
     import json; \
     db = MemoryDatabase('~/.claude/pd/memory/memory.db'); \
     r = recompute_all(db, dry_run=True); \
     print(json.dumps(r, indent=2))"
  ```
  Capture output. Compute `sha256sum ~/.claude/pd/memory/memory.db` for `memory_db_sha256` field.
- [ ] **T10.5**: Write `plugins/pd/hooks/lib/semantic_memory/fixtures/hash_shift_manifest.json` with schema:
  ```json
  {
    "shifted_ids": ["<from T10.4>"],
    "expected_count": <len(shifted_ids)>,
    "null_or_empty_skipped": <from T10.4>,
    "captured_at": "<ISO8601 UTC>",
    "memory_db_sha256": "<from sha256sum>"
  }
  ```
- [ ] **T10.6**: Commit fixture before Tier 4 migration body lands

---

## Tier 4: Memory hash unify + cleanup

### Group B-H4

- [ ] **T11.1** (RED): Add `test_migration_6_unify_source_hash_consumes_manifest` — load fixture memory.db with synthetic drift rows, run M6, assert shifted IDs match frozen manifest
- [ ] **T11.2** (RED): Add `test_migration_6_aborts_on_manifest_mismatch` — inject a non-manifest drift row, expect abort
- [ ] **T11.3** (RED): Add `test_migration_7_cleanup_inflated_observations` — fixture with `observation_count=1438` rows, run M7, assert reset to 1
- [ ] **T11.4** (GREEN): Add `_migration_6_unify_source_hash(conn)` in `semantic_memory/database.py` reading manifest + calling `recompute_all(dry_run=False)`
- [ ] **T11.5** (GREEN): Add `_migration_7_cleanup_inflated_observations(conn)` running the cleanup UPDATE
- [ ] **T11.6**: Verify memory.db current head still 5 pre-implement: `grep -cE "def _migration_[67]_" plugins/pd/hooks/lib/semantic_memory/database.py` expects 0. If non-zero, M6/M7 are already taken — renumber proposed migrations upward and update T11.4/T11.5/T11.7 + design TD-5.
- [ ] **T11.7** (GREEN): Register M6 + M7 in semantic_memory's MIGRATIONS dict
- [ ] **T11.8**: Update writer.py's `source_hash` call to match canonical (use `description`, not `raw_chunk`)

---

## Tier 5: Memory cleanup hygiene

### Group B-H3: _apply_quality_gates extraction

- [ ] **T12.1**: Define `QualityGateResult` dataclass in `memory_server.py` per IF-2
- [ ] **T12.2** (RED): Add `test_apply_quality_gates_too_short` — description<20 chars → `passed=False, reason='too_short'`
- [ ] **T12.3** (RED): Add `test_apply_quality_gates_near_dup` — 0.95 match → `passed=False, reason='near_dup'`
- [ ] **T12.4** (RED): Add `test_apply_quality_gates_dedup_merge` — 0.90 match → `passed=False, reason='deduped', merged_entry_id=<id>`
- [ ] **T12.5** (GREEN): Implement `_apply_quality_gates(description, db, config)` in `memory_server.py` per IF-2
- [ ] **T12.6** (GREEN): Refactor `_process_store_memory:92-147` to call `_apply_quality_gates`; remove inline duplicate gate logic
- [ ] **T12.7** (GREEN): Refactor `writer.py:main` (around line 300-328) to call `_apply_quality_gates` before `db.upsert_entry`
- [ ] **T12.8** (RED): Add `test_writer_main_rejects_short_input` integration test
- [ ] **T12.9** (RED): Add `test_writer_main_rejects_near_dup` integration test
- [ ] **T12.10** (verify): AST/grep check — 20-char-min / 0.95 / 0.90 thresholds appear exactly once in `memory_server.py`

### Group B-H2: Capture hook simplification

- [ ] **T13.1**: Locate canonical hook registration (likely `plugins/pd/.claude-plugin/plugin.json`). If user-local, pause and surface (per FR-B-H2.1 contingency).
- [ ] **T13.2**: Delete `plugins/pd/hooks/capture-tool-failure.sh:147-157` (heuristic detection branch)
- [ ] **T13.3**: Update hook registration to ONLY register for `PostToolUseFailure`
- [ ] **T13.4** (RED): Add `test_capture_hook_only_writes_on_real_failure` integration test
- [ ] **T13.5**: Add cleanup query `DELETE FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'` to **`_migration_6_unify_source_hash` body** in `semantic_memory/database.py`, BEFORE the hash-recompute loop. Dry-run gate: expect 414-514 deletions; abort migration if outside range. (M7 is reserved for inflated-observation cleanup — distinct concern.)

---

## Tier 6: Cross-workspace gates + triage + severity contract (parallel)

### Group E: Gates

- [ ] **T14.1**: Define `CrossWorkspaceError(ValueError)` exception class in `database.py` per IF-3
- [ ] **T14.2** (RED): Add `test_assert_same_workspace_pairwise_same_ws_passes` — two entities in same ws → no raise
- [ ] **T14.3** (RED): Add `test_assert_same_workspace_pairwise_mismatch_raises` — entities in different ws → `CrossWorkspaceError`
- [ ] **T14.4** (RED): Add `test_assert_same_workspace_pairwise_allowlist_exempts` — mismatched entities allowlisted → no raise
- [ ] **T14.5** (RED): Add `test_assert_same_workspace_pairwise_allowlist_both_orderings` — allowlist entry order doesn't matter
- [ ] **T14.6** (GREEN): Implement `_assert_same_workspace_pairwise(db, pair, op_name)` in `database.py` per IF-3
- [ ] **T14.7** (RED): Add `test_set_parent_cross_workspace_forbidden` — MCP `set_parent` with cross-workspace UUIDs → JSON envelope `error_type=cross_workspace_forbidden`
- [ ] **T14.8** (RED): Add `test_add_dependency_cross_workspace_forbidden` (same pattern)
- [ ] **T14.9** (RED): Add `test_add_okr_alignment_cross_workspace_forbidden` (same pattern)
- [ ] **T14.10** (GREEN): Update `_process_set_parent` in `server_helpers.py:483` to invoke assert
- [ ] **T14.11** (GREEN): Update `_process_add_dependency` in `entity_server.py` to invoke assert
- [ ] **T14.12** (GREEN): Update `_process_add_okr_alignment` in `entity_server.py` to invoke assert
- [ ] **T14.13** (GREEN): Add `CrossWorkspaceError` translator branch in MCP error-envelope handler (entity_server.py + server_helpers.py)

### Group E.2: Triage tool + Migration 17 allowlist

- [ ] **T15.1** (RED): Add `test_migration_17_creates_cross_workspace_allowlist` — assert `PRAGMA table_info(cross_workspace_allowlist)` returns 6 columns
- [ ] **T15.2** (RED): Add `test_migration_17_cascade_delete` — delete an entity, assert allowlist row auto-removed
- [ ] **T15.3** (GREEN): Add `_migration_17_cross_workspace_allowlist(conn)` per FR-E.2.1 schema
- [ ] **T15.4**: Register M17 in MIGRATIONS dict (sequenced after M16)
- [ ] **T15.5** (RED): Add `test_fix_triage_re_attribute_parent` — choose option (a) → parent's workspace_uuid updated
- [ ] **T15.6** (RED): Add `test_fix_triage_re_attribute_child` — choose option (b) → child's workspace_uuid updated
- [ ] **T15.7** (RED): Add `test_fix_triage_delete_relation` — choose option (c) → parent_uuid set to NULL
- [ ] **T15.8** (RED): Add `test_fix_triage_grandfather` — choose option (d) → allowlist row inserted
- [ ] **T15.9** (GREEN): Add `_parse_triage_choice(fix_hint)` helper
- [ ] **T15.10** (GREEN): Add `_fix_triage_cross_workspace_link(ctx, issue) -> str` per IF-8
- [ ] **T15.11** (GREEN): Add detection check that emits one warning Issue per unallowlisted cross-workspace row
- [ ] **T15.12** (GREEN): Add doctor-harness `_collect_user_choice_for_issue(issue)` to gather AskUserQuestion choice into `issue.fix_hint`

### Group E-Sev: Severity contract

- [ ] **T16.1** (RED): Add `test_doctor_severity_summary_present_in_output` — JSON output contains `severity_summary` with int counts
- [ ] **T16.2** (RED): Add `test_doctor_exit_code_zero_with_warnings_only` — seed warning-only conditions, assert exit code 0
- [ ] **T16.3** (RED): Add `test_doctor_issue_severity_is_info_warning_or_error` — JSON schema validation against all emitted records
- [ ] **T16.4** (GREEN): Update `doctor/__main__.py` to compute and emit `severity_summary` from collected issues
- [ ] **T16.5** (GREEN): Verify all existing checks emit explicit `severity` field; add where missing
- [ ] **T16.6** (verify): Existing `Exit code is always 0` contract preserved

---

## Cross-Tier Verification

- [ ] **TV.1**: Full `pytest plugins/pd/` passes from project root with 0 failures
- [ ] **TV.2**: Manual verification: `python -m plugins.pd.hooks.lib.entity_registry.remediate_m12 --dry-run --db <stub-trap-fixture-path>` produces expected output
- [ ] **TV.3**: Run `./validate.sh` if exists — all checks pass
- [ ] **TV.4**: Run `bash plugins/pd/hooks/tests/test-hooks.sh` if relevant — passes
- [ ] **TV.5**: Verify no new test failures in pre-existing test suites (regression check)
- [ ] **TV.6**: Production-DB simulation: against `~/.claude/pd/entities/entities.db` (currently at schema_version=11 post-manual-rollback), confirm M12 → M13 → M14 chain runs cleanly with tightened guards

---

## Acceptance Gate

All 91 tasks complete + TV.1-TV.6 pass. Then proceed to `/pd:finish-feature`.
