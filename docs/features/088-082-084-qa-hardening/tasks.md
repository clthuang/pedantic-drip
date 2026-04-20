# Feature 088: Tasks

All 40 tasks are ordered per plan.md bundle sequence (A → B → G → I → D → E → F → C → H → L → J → K → Final). Each `### Task N.M:` heading uses the implementing skill's required format.

## Phase 0 — Baseline

### Task 0.1: Capture NFR-2 baseline

**Files:** `agent_sandbox/088-baselines.txt` (NEW).

**Steps:**
1. Run `plugins/pd/.venv/bin/python -m pytest --collect-only -q plugins/pd/hooks/lib/semantic_memory/test_maintenance.py plugins/pd/hooks/lib/entity_registry/test_phase_events.py plugins/pd/mcp/test_workflow_state_server.py 2>&1 | tail -5` — capture last 5 lines.
2. Run `git rev-parse HEAD` — capture SHA.
3. Run `grep -c "db._conn" plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` — capture count as DB_CONN_BASELINE.
4. Run `wc -l plugins/pd/hooks/lib/semantic_memory/maintenance.py plugins/pd/hooks/lib/semantic_memory/refresh.py | tail -1` — capture as LOC_BASELINE.
5. Write all four values to `agent_sandbox/088-baselines.txt` with headers.

**DoD:** `agent_sandbox/088-baselines.txt` exists with SHA, pytest count, DB_CONN_BASELINE, LOC_BASELINE.

## Phase A — Shared config utility

### Task A.1: Create `_config_utils.py` with preserved signatures

**Files:** `plugins/pd/hooks/lib/semantic_memory/_config_utils.py` (NEW).

**Steps:**
1. Create new module mirroring existing `maintenance.py:65-129` signatures verbatim: `_warn_and_default(key, raw, default, warned)` and `_resolve_int_config(config, key, default, warned, clamp=None)`.
2. Hardcode stderr prefix `[memory-decay]` inside `_warn_and_default` (both callers use same prefix).

**DoD:** `python -c "from semantic_memory._config_utils import _warn_and_default, _resolve_int_config"` succeeds.

### Task A.2: Migrate maintenance.py to shared helpers

**Files:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`.

**Steps:**
1. Preflight: `grep -rn 'monkeypatch.*_resolve_int_config\|monkeypatch.*_warn_and_default' plugins/pd/hooks/lib/semantic_memory/` — verify tests patch caller binding (e.g., `maintenance._resolve_int_config`), not `_config_utils`.
2. Remove `_warn_and_default` and `_resolve_int_config` definitions at lines 65-129.
3. Add `from ._config_utils import _warn_and_default, _resolve_int_config` after existing imports.

**DoD:** Existing `test_maintenance.py` passes without changes.

### Task A.3: Migrate refresh.py to shared helpers

**Files:** `plugins/pd/hooks/lib/semantic_memory/refresh.py`.

**Steps:** Same pattern as A.2.

**DoD:** Existing tests referencing `refresh.py` pass without changes.

### Task A.4: Verify AC-22 and AC-23

**Files:** None (verification only).

**Steps:**
1. Diff the functions between caller modules — should both be imports now, no local defs.
2. `wc -l maintenance.py refresh.py | tail -1` — total ≥ 50 less than LOC_BASELINE.

**DoD:** AC-22 and AC-23 verified.

## Phase B — Feature 082 correctness

### Task B.1: Timestamp format unification + overflow guard + `_DAYS_*` constants

**Files:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`.

**Steps:**
1. Add `_iso_utc(dt)` helper that returns `dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')`.
2. Add module-level `_DAYS_MIN = 0`, `_DAYS_MAX = 365` constants with comment warning.
3. Replace all `.isoformat()` calls in `decay_confidence` with `_iso_utc(...)` calls (lines ~361-364 `high_cutoff`, `med_cutoff`, `grace_cutoff`, `now_iso`).
4. Wrap cutoff computation in try/except catching `OverflowError` and `ValueError` → route to `_zero_diag(error=..., dry_run=dry_run)`.

**DoD:**
- `grep -nE '\.isoformat\(\)' plugins/pd/hooks/lib/semantic_memory/maintenance.py` returns 0.
- `grep -cE "strftime\('%Y-%m-%dT%H:%M:%SZ'\)" maintenance.py` ≥ 4.
- `grep -n "_DAYS_MIN\|_DAYS_MAX" maintenance.py` returns 2+ matches.

### Task B.2: Remove dead `now_iso` parameter (FR-3.3)

**Files:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`.

**Steps:**
1. Modify `_select_candidates` signature: remove `now_iso` param.
2. Update call site in `decay_confidence:~368`.

**DoD:** `python -c "import inspect; from semantic_memory.maintenance import _select_candidates; assert 'now_iso' not in inspect.signature(_select_candidates).parameters"` exits 0.

### Task B.3: `_select_candidates` LIMIT + cursor streaming (FR-9.6)

**Files:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`.

**Steps:**
1. Modify `_select_candidates` to accept `scan_limit` kwarg (default 100000). Add `LIMIT ?` to SQL binding `scan_limit`.
2. Convert to yield-based (generator). Caller wraps with `list(...)`.
3. In `decay_confidence`, resolve `scan_limit = _resolve_int_config(config, 'memory_decay_scan_limit', 100000, _warned, clamp=(1000, 10_000_000))`.
4. Pass `scan_limit=scan_limit` to `_select_candidates`.

**DoD:** `grep -n "LIMIT" plugins/pd/hooks/lib/semantic_memory/maintenance.py` matches in `_select_candidates`. Function is callable via `list(_select_candidates(...))`.

### Task B.4: Add Bundle B tests

**Files:** `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py`.

**Steps:**
1. Add `test_overflow_config_returns_error_dict` (AC-11).
2. Add `test_exact_threshold_boundary_is_not_stale` (AC-37).
3. Add `test_scan_limit_caps_result_set` (AC-32).

**DoD:** All three new tests pass.

## Phase G — Input validation

### Task G.1: DEFAULTS + strict truthiness (FR-10.1)

**Files:** `plugins/pd/hooks/lib/semantic_memory/config.py`.

**Steps:**
1. Add `memory_decay_enabled`, `memory_decay_high_threshold_days`, `memory_decay_medium_threshold_days`, `memory_decay_grace_period_days`, `memory_decay_dry_run`, `memory_decay_scan_limit` to DEFAULTS.
2. Add `_TRUE_VALUES`, `_FALSE_VALUES` frozensets + `_coerce_bool(key, value, default)` function.
3. Add `_warn_unknown_keys(config)` function; wire into session-start config read path.

**DoD:**
- `python -c "from semantic_memory.config import DEFAULTS; assert 'memory_decay_enabled' in DEFAULTS and 'memory_decay_scan_limit' in DEFAULTS"` exits 0.

### Task G.2: CLI uid check in `maintenance._main` (FR-10.2)

**Files:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`.

**Steps:**
1. Before loading config: `st_uid = Path(args.project_root).resolve().stat().st_uid`. If `st_uid != os.getuid()`: stderr warn + return exit code 2.

**DoD:** Test with mocked uid mismatch → exits non-zero with warning.

### Task G.3: Add Bundle G tests

**Files:** `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py`.

**Steps:**
1. Add `test_coerce_false_capital_string_returns_default_with_warning` (AC-34b).
2. Add `test_unknown_key_emits_warning` (AC-34).
3. Add `test_foreign_uid_project_root_refuses` (AC-35).

**DoD:** All three tests pass.

## Phase I — Skill-layer fix (MUST land before D.3)

### Task I.1: Update SKILL.md `handleReviewerResponse`

**Files:** `plugins/pd/skills/workflow-transitions/SKILL.md`.

**Steps:**
1. At lines ~395-415: add explicit `project_id` resolution step BEFORE `record_backward_event` call (read from `.meta.json` or call `get_entity()`).
2. Remove `project_id=project_id` kwarg from the `record_backward_event` call.
3. Preflight: `grep -rn 'record_backward_event' plugins/pd/ docs/` — enumerate additional callers; update each.

**DoD:** `grep -nE 'project_id\s*=' plugins/pd/skills/workflow-transitions/SKILL.md` shows `project_id` assigned as a variable before `record_backward_event`; kwarg is not passed (AC-26).

## Phase D — Cross-project isolation

### Task D.1: `query_phase_analytics` scoping (FR-2.1, FR-6.1)

**Files:** `plugins/pd/mcp/workflow_state_server.py`.

**Steps:**
1. PRESERVE parameter name `feature_type_id` (no rename).
2. Add `err = _check_db_available(); if err: return err` at top of function.
3. Resolve: `resolved_project_id = None if project_id == "*" else (project_id or _project_id)`.
4. Pass `resolved_project_id` to every internal `_db.query_phase_events(...)` call.
5. Add test `test_query_phase_analytics_degraded_mode` (AC-17 part 1).

**DoD:** New test `test_query_analytics_scopes_to_current_project_by_default` (AC-4) passes; degraded-mode test passes.

### Task D.2: Migration 10 hardening (FR-2.2, FR-6.4, FR-6.2)

**Files:** `plugins/pd/hooks/lib/entity_registry/database.py`.

**Steps:**
1. In `_migration_10_phase_events`: move `conn.execute("BEGIN IMMEDIATE")` INSIDE try block.
2. Add schema_version re-check as first statement inside try (return early if ≥ 10).
3. Add scoped dedup DELETE: `DELETE FROM phase_events WHERE source='backfill' AND id NOT IN (SELECT MIN(id) FROM phase_events WHERE source='backfill' GROUP BY type_id, phase, event_type, timestamp)`.
4. Add `CREATE UNIQUE INDEX IF NOT EXISTS phase_events_backfill_dedup ON phase_events(type_id, phase, event_type, timestamp) WHERE source = 'backfill'`.
5. Change backfill loop INSERTs to `INSERT OR IGNORE`.
6. Add `PHASE_EVENTS_COLS` constant and replace `SELECT * FROM phase_events` in `query_phase_events` (line ~2985) with explicit list.

**DoD:**
- `grep -n "SELECT \* FROM phase_events" plugins/pd/hooks/lib/entity_registry/database.py` returns 0 in non-test code.
- New test `test_migration_10_concurrent_idempotent` (AC-5) passes with `threading.Barrier`.

### Task D.3: `record_backward_event` validation (FR-2.3, FR-6.1, FR-2.5)

**Files:** `plugins/pd/mcp/workflow_state_server.py`.

**Prerequisite:** Task I.1 MUST be complete (SKILL.md no longer passes `project_id=`).

**Steps:**
1. Add `_check_db_available` guard.
2. Remove `project_id` from caller-visible signature.
3. Look up entity via `_db.get_entity(type_id)`; return `_make_error("entity_not_found", ...)` if not found.
4. Cap `reason` and `target_phase` at 500 chars.
5. On sqlite error, return `_make_error("insert_failed", ...)` (never raw `str(e)`).
6. Add test `test_record_backward_event_degraded_mode` (AC-17 part 2).

**DoD:** Tests `test_record_backward_event_rejects_unknown_type_id` (AC-6), `test_record_backward_event_error_shape_matches_make_error` (AC-8), `test_record_backward_event_truncates_reason_at_500` (AC-6) pass.

### Task D.4: Migration 10 backfill validation (FR-2.6)

**Files:** `plugins/pd/hooks/lib/entity_registry/database.py`.

**Steps:**
1. Wrap each `timestamp` read from metadata in try/except `datetime.fromisoformat(...)`; skip row with stderr warning on failure.
2. Truncate `backward_reason`/`backward_target` to 500 chars before INSERT.

**DoD:** Tests `test_migration_skips_unparseable_timestamp` (AC-9), `test_migration_truncates_backward_reason_at_500` (AC-9b) pass.

## Phase E — Transaction safety

### Task E.1: Refactor `_process_transition_phase` + `_process_complete_phase` dual-write (FR-5.1)

**Files:** `plugins/pd/mcp/workflow_state_server.py`.

**Steps:**
1. Initialize `entity = None` BEFORE `with _db.transaction()` block.
2. In both functions: capture `entity` inside transaction; perform `update_entity` INSIDE transaction.
3. Move `insert_phase_event` OUTSIDE transaction with its own try/except.
4. On failure, set `phase_events_write_failed=True` and emit stderr warning matching `[workflow-state] phase_events dual-write failed for {type_id}:{phase}: {type(exc).__name__}: {str(exc)[:200]}`.
5. For `_process_complete_phase`: swap existing order so `update_entity(metadata)` runs INSIDE transaction, `insert_phase_event` runs AFTER commit.
6. Use `entity.get('project_id') or '__unknown__'`.

**DoD:** Test `test_dual_write_failure_commits_main_transaction` (AC-15) passes.

### Task E.2: `insert_phase_event` reviewer_notes size guard (FR-2.4 DB-layer)

**Files:** `plugins/pd/hooks/lib/entity_registry/database.py`.

**Steps:**
1. At top of `insert_phase_event`: `if reviewer_notes is not None and len(reviewer_notes) > 10000: raise ValueError("reviewer_notes exceeds 10000 chars")`.

**DoD:** Test `test_insert_phase_event_rejects_oversized_reviewer_notes` passes.

### Task E.3: `_process_complete_phase` entry-point guard + single-parse (FR-2.4)

**Files:** `plugins/pd/mcp/workflow_state_server.py`.

**Steps:**
1. Reject `reviewer_notes > 10000` via `_make_error`.
2. Parse JSON once inside try/except `json.JSONDecodeError` → `_make_error("invalid_reviewer_notes", ...)`.
3. Update BOTH existing call sites (lines ~791 and ~804) to use the pre-parsed `parsed_notes` variable.

**DoD:** Tests `test_complete_phase_rejects_oversized_reviewer_notes` (AC-7), `test_complete_phase_rejects_malformed_json_reviewer_notes` pass.

### Task E.4: Transaction-participation pin test (FR-5.2, AC-16)

**Files:** `plugins/pd/hooks/lib/entity_registry/test_phase_events.py`.

**Steps:**
1. Add `test_insert_phase_event_does_not_prematurely_commit_outer_transaction`: use `db.transaction()` context, call `insert_phase_event`, raise before exit, assert phase_events row NOT persisted.

**DoD:** Test passes. Pinning existing `_commit()` guard at `database.py:1551-1554`.

## Phase F — Analytics pairing

### Task F.1: Rewrite `_compute_durations` (FR-4.1, FR-4.2, FR-6.3)

**Files:** `plugins/pd/mcp/workflow_state_server.py`.

**Steps:**
1. Move `from collections import defaultdict`, `from datetime import datetime`, `from itertools import zip_longest` to module-level imports.
2. Add module-level `_ANALYTICS_EVENT_SCAN_LIMIT = 500`.
3. Rewrite signature to `_compute_durations(events: list[dict]) -> list[dict]`.
4. Iterate `groups_s.keys() | groups_c.keys()` (union).
5. Use `zip_longest(s_list, c_list, fillvalue=None)` for pair iteration.
6. Emit `duration_seconds=None`, `missing_started`, `missing_completed` flags for unpaired rows.
7. Update caller in `query_phase_analytics` (~line 1669) to concatenate results of the two existing filtered `query_phase_events` calls (event_type=started + event_type=completed) into a single list passed to `_compute_durations`.

**DoD:** Tests `test_phase_duration_completed_without_started_emits_null_row` (AC-13), `test_phase_duration_imbalanced_pairs_handled` (AC-14), `test_compute_durations_isolated` (AC-19) pass.

### Task F.2: `iteration_summary` filter-then-limit (FR-7.1)

**Files:** `plugins/pd/mcp/workflow_state_server.py`.

**Steps:**
1. In `query_phase_analytics` iteration_summary branch: fetch with `limit=_ANALYTICS_EVENT_SCAN_LIMIT`; filter `iterations is not None` in Python; sort; `results = results[:limit]`.

**DoD:** Test `test_iteration_summary_filters_nones_before_limit` (AC-24) passes.

## Phase C — Session-start security

### Task C.1: Convert 6 `python3 -c "..."` blocks (FR-1.1)

**Files:** `plugins/pd/hooks/session-start.sh`.

**Steps:**
1. For each `python3 -c "..."` block at lines 60, 105, 188, 437, 599, 642: convert outer double-quotes to single-quotes; move bash vars to positional args; read in Python via `sys.argv[1:]`.

**DoD:** `grep -nE 'python3 -c "[^"]*\$' plugins/pd/hooks/session-start.sh` returns 0.

### Task C.2: Symlink-safe log open (FR-1.2)

**Files:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`, `plugins/pd/hooks/lib/semantic_memory/refresh.py`.

**Steps:**
1. In `_emit_decay_diagnostic` (maintenance) and `_emit_influence_diagnostic` (refresh): replace `with open(...)` with `os.open(..., O_NOFOLLOW | O_APPEND | O_CREAT | O_WRONLY, 0o600)` + `os.fchmod(fd, 0o600)` + close-in-finally.
2. Create parent dir with `mode=0o700`.

**DoD:** Test `test_influence_log_refuses_symlink_follow` (AC-2) passes.

### Task C.3: PATH pinning + venv hard-fail + timeout (FR-1.3)

**Files:** `plugins/pd/hooks/session-start.sh`.

**Steps:**
1. In `run_memory_decay`: save PATH, pin to `/usr/bin:/bin:/usr/sbin:/sbin`.
2. Verify `${PLUGIN_ROOT}/.venv/bin/python` exists; exit early if missing.
3. Detect `gtimeout`/`timeout`; fall back to Python `subprocess.run(..., timeout=10)` wrapper.
4. Restore PATH at function end.

**DoD:** `grep -nE 'export PATH="/usr/bin:/bin' plugins/pd/hooks/session-start.sh` matches ≥ 1 within `run_memory_decay`.

### Task C.4: Session-start integration tests (AC-1, AC-3)

**Files:** `plugins/pd/hooks/tests/test-hooks.sh`.

**Steps:**
1. Add test with poisoned `.meta.json` containing injection payload; run session-start.sh; assert `/tmp/pd-088-pwned` NOT created.
2. Add test with renamed venv python (restore after); run session-start; assert exit 0 with no decay section.

**DoD:** Both integration tests pass.

## Phase H — Test hardening

### Task H.1: Autouse fixture for workflow_state_server globals (FR-6.5)

**Files:** `plugins/pd/mcp/test_workflow_state_server.py`.

**Steps:**
1. Add module-level autouse fixture saving/restoring `_db` and `_db_unavailable`.
2. Remove try/finally `_db` mutations in feature-084 test classes.

**DoD:** Multiline grep for `try:.*finally:.*_db = ` in feature-084 test sections returns 0.

### Task H.2: Migrate `db._conn` test-helper call sites + `NOW` rename

**Files:** `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py`, `plugins/pd/hooks/lib/semantic_memory/database.py`.

**Steps:**
1. Add `MemoryDatabase.insert_test_entry(**kwargs)` public method for test seeding (or identify existing public API).
2. Replace all 25+ `db._conn.execute(...)` in `_get_row`, `_seed_entry`, `_bulk_seed` with public API calls.
3. Rename module-level `NOW` to `_TEST_EPOCH` (preserve `_days_ago` default behavior).

**DoD:** `grep -c "db._conn" plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` returns 0. All existing tests pass.

### Task H.3a: Concurrency + integration tests

**Files:** `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py`.

**Steps:**
1. Add `test_concurrent_writer_via_decay_confidence` (AC-31).
2. Add `test_concurrent_decay_and_record_influence_both_succeed_eventually` (AC-39 part 1).
3. Add `test_fts5_queries_still_work_after_bulk_decay` (AC-39 part 2).
4. Add `test_rejects_or_normalizes_naive_datetime_now` (AC-38).

**DoD:** All 4 tests pass.

### Task H.3b: Boundary + error-path + augmentation tests

**Files:** `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py`, `plugins/pd/hooks/tests/test-hooks.sh`.

**Steps:**
1. Add `test_empty_db_returns_all_zeros_with_no_error`.
2. Add `test_nan_infinity_and_negative_zero_threshold_values_fall_back_to_default`.
3. Add `test_sqlite_error_during_select_phase_returns_error_dict`.
4. Add `test_session_start_decay_timeout_does_not_block_hook` to test-hooks.sh.
5. Augment existing `test_ac11a/b/c` with `capsys.readouterr()` + regex assertion (AC-28).

**DoD:** All 5 tests pass.

### Task H.4: Feature 084 test additions (FR-10.10, AC-43)

**Files:** `plugins/pd/mcp/test_workflow_state_server.py`, `plugins/pd/hooks/lib/entity_registry/test_phase_events.py`.

**Steps:**
1. Add `test_phase_duration_handles_mismatched_started_completed_counts`.
2. Add `test_insert_phase_event_rejects_invalid_event_type_and_source`.
3. Add `test_migration_10_rerun_on_pre_existing_rows_does_not_duplicate_backfill`.
4. Add `test_record_backward_event_returns_error_json_under_db_lock`.
5. Add `test_dual_write_metadata_and_phase_events_consistency_on_partial_failure`.
6. Strengthen `test_ac19_metadata_still_has_phase_timing` to assert `iterations==2` + `reviewerNotes` round-trip (AC-41).

**DoD:** All tests pass; AC-41 strengthened test passes.

## Phase L — Reconcile drift detection

### Task L.1: Add `_detect_phase_events_drift` helper

**Files:** `plugins/pd/mcp/workflow_state_server.py`.

**Steps:**
1. Add `from entity_registry.metadata import parse_metadata` import.
2. Add `_detect_phase_events_drift(db, feature_type_id)` function per design Bundle L.1 (Python-side status filter using list_entities + Python filter).

**DoD:** Function callable; empty DB returns `[]`.

### Task L.2: Wire into reconcile_check and reconcile_apply

**Files:** `plugins/pd/mcp/workflow_state_server.py`.

**Steps:**
1. Modify `_process_reconcile_check` to include `phase_events_drift` sibling JSON key.
2. Modify `_process_reconcile_apply` to emit stderr warning per drift entry WITHOUT modifying phase_events.

**DoD:** Tests `test_reconcile_check_reports_phase_events_drift` (AC-42), `test_reconcile_apply_does_not_modify_phase_events` (AC-42b) pass.

## Phase J — Spec patches

### Task J.1: Append Amendments section to 082 spec

**Files:** `docs/features/082-recall-tracking-and-confidence/spec.md`.

**Steps:**
1. Append `## Amendments (2026-04-19 — feature 088)` section at END of file.
2. Include three amendments (A: AC-10 skipped_floor=2, B: FR-2 NULL branch tier-threshold text, C: AC-11 capsys note).

**DoD:** `grep -n "## Amendments" docs/features/082-recall-tracking-and-confidence/spec.md` returns 1. Original AC-10 text unchanged (`grep -c "skipped_floor == 1"` still ≥ 1).

### Task J.2: Correct maintenance.py docstring I-3

**Files:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`.

**Steps:**
1. Locate docstring I-3 block claiming "clamped silently"; correct to describe warn-on-clamp behavior.

**DoD:** `grep -n "clamped silently\|clamped SILENTLY" plugins/pd/hooks/lib/semantic_memory/maintenance.py` returns 0.

### Task J.3: Regenerate `agent_sandbox/082-eqp.txt`

**Files:** `agent_sandbox/082-eqp.txt`, `agent_sandbox/088-eqp-regen.py` (temp).

**Steps:**
1. Create `agent_sandbox/088-eqp-regen.py` that seeds 10000 entries with `source != 'import'` + calls `decay_confidence` + writes `scanned=... skipped_import=... elapsed_ms=...` to `agent_sandbox/082-eqp.txt`.
2. Run the script once.
3. Delete the script.

**DoD:** `grep -n "skipped_import=0" agent_sandbox/082-eqp.txt` matches; `agent_sandbox/088-eqp-regen.py` does NOT exist.

## Phase K — Process backfill

### Task K.1: Create retroactive 084 retro.md

**Files:** `docs/features/084-structured-execution-data/retro.md` (NEW).

**Steps:**
1. Write AORTA retro (Aims, Outcomes, Reflections, Tune, Adopt) with ≥ 50 lines.
2. List all 084 post-release findings (#00080–#00084 + #00117–#00137).
3. Include lessons: SELECT * anti-pattern, dual-write-inside-transaction anti-pattern, missing `_check_db_available`, project_id scoping convention, dual-write OUTSIDE transaction pattern.

**DoD:** `wc -l docs/features/084-structured-execution-data/retro.md` ≥ 50 (AC-44).

### Task K.2: Add backlog #00138 for deferred sub-items

**Files:** `docs/backlog.md`.

**Steps:**
1. Append `#00138` entry enumerating deferred #00116 / #00136 sub-items not covered by FR-10.7 / FR-10.10.

**DoD:** `grep -n "#00138" docs/backlog.md` matches.

## Final Validation

### Task Final.1: NFR verification gate

**Files:** None (verification only).

**Steps:**
1. Run NFR-1 pytest suite; capture count.
2. Verify count ≥ baseline from Task 0.1.
3. Run `./validate.sh`.
4. Run `bash plugins/pd/hooks/tests/test-hooks.sh`.
5. Verify AC count: `grep -cE "^- \*\*AC-[0-9]+[a-z]?" docs/features/088-082-084-qa-hardening/spec.md` returns 47.

**DoD:** All NFRs pass; AC count matches.
