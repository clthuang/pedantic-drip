# Feature 088: Implementation Plan

## Overview

12 bundles (A–L) from design.md mapped to **39 sequential tasks** (plus Task 0 baseline + Final gate = 13 logical groups). Order enforces `TD-I` bundle dependency graph (A→B→G→D→E→F→C→H→I→L→J→K). Tasks within a bundle may run together; cross-bundle parallelism is NOT supported for bundles sharing files (A/B/G on `maintenance.py`; D/E/F on `workflow_state_server.py`).

## Prerequisites (Task 0)

**Task 0.1 — Capture NFR-2 baseline.**
- Run: `plugins/pd/.venv/bin/python -m pytest --collect-only -q plugins/pd/hooks/lib/semantic_memory/test_maintenance.py plugins/pd/hooks/lib/entity_registry/test_phase_events.py plugins/pd/mcp/test_workflow_state_server.py 2>&1 | tail -5`
- Write output to `agent_sandbox/088-baselines.txt` with (a) pre-fix git SHA via `git rev-parse HEAD`, (b) the exact command, (c) the test-count line.
- Also: `grep -c "db._conn" plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` → record as `DB_CONN_BASELINE`.
- Also: `wc -l plugins/pd/hooks/lib/semantic_memory/maintenance.py plugins/pd/hooks/lib/semantic_memory/refresh.py | tail -1` → record as `LOC_BASELINE`.

**Pass criterion:** `agent_sandbox/088-baselines.txt` exists, contains pre-fix SHA, pytest count integer, DB_CONN_BASELINE integer, LOC_BASELINE integer.

## Bundle A — Shared config utility (FR-6.7)

**Task A.1 — Create `_config_utils.py`.**
- File: `plugins/pd/hooks/lib/semantic_memory/_config_utils.py` (NEW).
- **Signature decision:** Mirror the EXISTING signatures at `maintenance.py:65-78` for drop-in replacement — do NOT adopt design Bundle A's new `(key, raw, reason, default, *, prefix, warned)` shape. Keep `_warn_and_default(key, raw, default, warned)` and `_resolve_int_config(config, key, default, warned, clamp=None)` signatures identical. Hardcode the stderr prefix to `[memory-decay]` inside `_warn_and_default` since both callers use the same prefix.
- Pass: `python -c "from semantic_memory._config_utils import _warn_and_default, _resolve_int_config"` succeeds.

**Task A.2 — Migrate maintenance.py to import shared helpers.**
- Remove the local definitions of `_warn_and_default` and `_resolve_int_config` at `maintenance.py:65-129`.
- Add import: `from ._config_utils import _warn_and_default, _resolve_int_config`.
- No call-site changes — signatures preserved per Task A.1.
- Pre-flight: `grep -rn 'monkeypatch.*_resolve_int_config\|monkeypatch.*_warn_and_default' plugins/pd/hooks/lib/semantic_memory/` — verify each test patches the caller module's binding (`maintenance._resolve_int_config`), not `_config_utils` directly. If any target `_config_utils`, migrate them to patch the caller side.
- Pass: existing `test_maintenance.py` passes unchanged.

**Task A.3 — Migrate refresh.py to import shared helpers.**
- Same pattern as A.2 for `refresh.py`.
- Pass: existing tests pass.

**Task A.4 — Verify AC-22, AC-23.**
- Run: `diff <(sed -n '/^def _resolve_int_config/,/^def /p' plugins/pd/hooks/lib/semantic_memory/maintenance.py) <(sed -n '/^def _resolve_int_config/,/^def /p' plugins/pd/hooks/lib/semantic_memory/refresh.py)` → returns empty (both now import; no local def).
- Run: `wc -l plugins/pd/hooks/lib/semantic_memory/maintenance.py plugins/pd/hooks/lib/semantic_memory/refresh.py | tail -1` → total LOC drops by ≥ 50 vs `LOC_BASELINE`.
- Commit: `feat(088): Bundle A — extract shared config utils (FR-6.7)`.

## Bundle B — Feature 082 correctness fixes

**Task B.1 — Timestamp format unification + overflow guard + `_DAYS_*` constants (FR-3.1, FR-3.2).**
- In `maintenance.py`: add `_iso_utc(dt)` helper; add `_DAYS_MIN=0`, `_DAYS_MAX=365` module-level constants with comment warning about overflow audit on widening.
- Replace all `datetime.isoformat()` and non-Z-suffix strftime in `decay_confidence` with `_iso_utc(...)`.
- Wrap cutoff computation in try/except catching `OverflowError` and `ValueError` → routes to `_zero_diag(error=..., dry_run=dry_run)`.
- Pass: `grep -nE '\.isoformat\(\)' plugins/pd/hooks/lib/semantic_memory/maintenance.py` returns 0 (catches both `now.isoformat()` and `datetime.isoformat()` forms). Positive check: `grep -cE "strftime\('%Y-%m-%dT%H:%M:%SZ'\)" plugins/pd/hooks/lib/semantic_memory/maintenance.py` returns ≥ 4. `grep -n "_DAYS_MIN\|_DAYS_MAX" plugins/pd/hooks/lib/semantic_memory/maintenance.py` returns 2+ matches.

**Task B.2 — Remove dead `now_iso` param (FR-3.3).**
- Modify `_select_candidates` signature: remove `now_iso` param. Update call in `decay_confidence:368`.
- Pass: `python -c "import inspect; from semantic_memory.maintenance import _select_candidates; assert 'now_iso' not in inspect.signature(_select_candidates).parameters"` exits 0.

**Task B.3 — `_select_candidates` LIMIT + cursor streaming (FR-9.6).**
- Modify `_select_candidates`: add `scan_limit` kwarg (default 100000). SQL: add `LIMIT ?` binding `scan_limit`. Convert fetchall to yield-based.
- Add `memory_decay_scan_limit` to `config.py` DEFAULTS (covered in Task G.1).
- Wire caller in `decay_confidence` per design final reconciled form:
  ```python
  scan_limit = _resolve_int_config(config, 'memory_decay_scan_limit', 100000, prefix='[memory-decay]', warned=_warned, clamp=(1000, 10_000_000))
  candidates = list(_select_candidates(db, high_cutoff, med_cutoff, grace_cutoff, scan_limit=scan_limit))
  ```
- Pass: `grep -n "LIMIT" plugins/pd/hooks/lib/semantic_memory/maintenance.py` matches in `_select_candidates`.

**Task B.4 — Add tests for B.1/B.2/B.3.**
- New test: `test_overflow_config_returns_error_dict` — widen clamp in test config, pass `now=datetime(MAXYEAR,12,31)`, assert `error` key in result.
- New test: `test_exact_threshold_boundary_is_not_stale` (AC-37) — seed `last_recalled_at = _iso_utc(NOW - timedelta(days=30))`, assert `demoted_high_to_medium == 0`.
- New test: `test_scan_limit_caps_result_set` — seed 10 stale entries, set `scan_limit=5`, assert `scanned <= 5`.
- Pass: all three new tests pass. No existing test regresses.

Commit: `feat(088): Bundle B — timestamp/overflow/scan_limit correctness (FR-3, FR-9.6)`.

## Bundle G — Input validation (FR-10.1, FR-10.2)

**Task G.1 — Config DEFAULTS expansion + strict truthiness (FR-10.1, #00096 part B).**
- In `config.py`: add `memory_decay_*` keys (incl. `memory_decay_scan_limit=100000`) to DEFAULTS.
- Add `_TRUE_VALUES = frozenset({True, 'true', '1', 1})`, `_FALSE_VALUES = frozenset({False, 'false', '0', 0, ''})`.
- Add `_coerce_bool(key, value, default)` function per design G.1 sketch.
- Add `_warn_unknown_keys(config)` function per design G.2 — called at session-start entry.
- Pass: `python -c "from semantic_memory.config import DEFAULTS; assert 'memory_decay_enabled' in DEFAULTS and 'memory_decay_scan_limit' in DEFAULTS"` exits 0.

**Task G.2 — CLI uid check in `maintenance._main` (FR-10.2).**
- Before loading config: `st_uid = Path(args.project_root).resolve().stat().st_uid`. If `st_uid != os.getuid()`: stderr warn + return exit code 2.
- Pass: test with mocked `os.getuid()` and `os.stat` returning foreign uid → CLI exits non-zero.

**Task G.3 — Add tests for G.1/G.2.**
- New test: `test_coerce_false_capital_string_returns_default_with_warning` (AC-34b) — call `_coerce_bool('memory_decay_enabled', 'False', True)`, assert returns `True` (default) + capsys contains `r'ambiguous boolean'`.
- New test: `test_unknown_key_emits_warning` (AC-34) — `_warn_unknown_keys({'memory_decay_enabaled': True})`, assert capsys matches `r'unknown key'`.
- New test: `test_foreign_uid_project_root_refuses` (AC-35) — mock stat/getuid, call `_main` with `--project-root /foreign/path`, assert exit code 2.
- Pass: all three tests pass.

Commit: `feat(088): Bundle G — config defaults + strict coercion + uid check (FR-10.1, FR-10.2)`.

## Bundle D — Cross-project isolation + MCP guards (FR-2, FR-6.1, FR-6.2, FR-6.4)

**Task D.1 — `query_phase_analytics` scoping (FR-2.1).**
- PRESERVE existing parameter name `feature_type_id` on the MCP tool — DO NOT rename to `type_id`.
- Add `err = _check_db_available(); if err: return err` at top of function body.
- Add `resolved_project_id = None if project_id == "*" else (project_id or _project_id)` after the degraded-mode check.
- Pass `resolved_project_id` to every internal `_db.query_phase_events(...)` call.
- Add test `test_query_phase_analytics_degraded_mode` — asserts `_make_error` shape when `_db_unavailable=True` (AC-17, part 1).
- Pass: new test `test_query_analytics_scopes_to_current_project_by_default` (AC-4) seeds two projects, asserts default call returns only current-project rows.

**Task D.2 — Migration 10 hardening (FR-2.2, FR-6.4, FR-6.2).**
- In `_migration_10_phase_events`: move `conn.execute("BEGIN IMMEDIATE")` INSIDE try (FR-6.4).
- Add schema_version re-check as first statement inside try (return early if ≥ 10).
- Add scoped dedup DELETE for `source='backfill'` duplicates.
- Add `CREATE UNIQUE INDEX IF NOT EXISTS phase_events_backfill_dedup ON phase_events(type_id, phase, event_type, timestamp) WHERE source = 'backfill'`.
- Change backfill loop INSERTs to `INSERT OR IGNORE`.
- Replace `SELECT * FROM phase_events` at line ~2985 with explicit `PHASE_EVENTS_COLS` constant (FR-6.2).
- Pass: `grep -n "SELECT \* FROM phase_events" plugins/pd/hooks/lib/entity_registry/database.py` returns 0 in non-test code. New test `test_migration_10_concurrent_idempotent` (AC-5) spins two threads via `threading.Barrier`; final row count equals single-run count.

**Task D.3 — `record_backward_event` validation (FR-2.3, FR-6.1).**
- **ORDERING NOTE**: Bundle I (Task I.1) MUST land BEFORE this task — SKILL.md currently passes `project_id=project_id` to `record_backward_event`; if D.3 removes the parameter first, any session invoking workflow-transitions between D-commit and I-commit raises TypeError. Swap sequence: I.1 first, then D.3.
- Add `_check_db_available` guard.
- Remove `project_id` from caller-visible signature (after Task I.1 stops passing it).
- Look up entity via `_db.get_entity(type_id)`; return `_make_error("entity_not_found", ...)` if not found.
- Cap `reason` and `target_phase` at 500 chars.
- On sqlite error, return `_make_error("insert_failed", ...)` (FR-2.5) — never raw `str(e)`.
- Pre-flight: `grep -rn 'record_backward_event' plugins/pd/ docs/` — enumerate all call sites. Remove any `project_id=` kwargs from callers/tests.
- Add test `test_record_backward_event_degraded_mode` — asserts `_make_error` shape when `_db_unavailable=True` (AC-17, part 2).
- Pass: new tests `test_record_backward_event_rejects_unknown_type_id` (AC-6), `test_record_backward_event_error_shape_matches_make_error` (AC-8), `test_record_backward_event_truncates_reason_at_500` (AC-6) all pass.

**Task D.4 — Migration 10 backfill validation (FR-2.6).**
- Wrap each `timestamp` read from `metadata` in try/except `datetime.fromisoformat(...)`; skip row with stderr warning on failure.
- Truncate `backward_reason`/`backward_target` to 500 chars before INSERT.
- Pass: new tests `test_migration_skips_unparseable_timestamp` (AC-9), `test_migration_truncates_backward_reason_at_500` (AC-9b) pass.

Commit: `feat(088): Bundle D — cross-project scoping, migration 10 hardening (FR-2, FR-6.1/6.2/6.4)`.

## Bundle E — Transaction safety (FR-5, FR-2.4)

**Task E.1 — Refactor `_process_transition_phase` + `_process_complete_phase` dual-write (FR-5.1).**
- Initialize `entity = None` BEFORE entering `with _db.transaction()` to guard against the `get_entity` raising (variable always bound in post-commit scope).
- In `_process_transition_phase` (workflow_state_server.py:~629): capture `entity` inside transaction; move `insert_phase_event` OUTSIDE; on failure, set `phase_events_write_failed=True` and emit stderr warning matching spec format. Before the post-commit phase_events write, check `if entity is None: return ...` (transaction aborted — no valid entity to reference).
- In `_process_complete_phase` (~796): same pattern + swap ordering so `update_entity(metadata)` runs INSIDE transaction, `insert_phase_event` runs AFTER commit.
- Use `entity.get('project_id') or '__unknown__'` (NOT `, '__unknown__'`).
- Pass: new test `test_dual_write_failure_commits_main_transaction` (AC-15) monkeypatches `insert_phase_event` to raise; asserts entity metadata update persisted, response has `phase_events_write_failed: true`, stderr warning matched.

**Task E.2 — `insert_phase_event` reviewer_notes size guard (FR-2.4, DB-layer defense).**
- Add `if reviewer_notes is not None and len(reviewer_notes) > 10000: raise ValueError(...)` at top of `insert_phase_event`.
- Pass: new test `test_insert_phase_event_rejects_oversized_reviewer_notes` in `test_phase_events.py`.

**Task E.3 — `_process_complete_phase` entry-point guard + single-parse (FR-2.4).**
- Reject `reviewer_notes > 10000` via `_make_error`.
- Parse JSON once inside try/except `json.JSONDecodeError` → `_make_error("invalid_reviewer_notes", ...)`.
- Update BOTH call sites (existing lines 791 and 804) to use the pre-parsed `parsed_notes` variable.
- Pass: new test `test_complete_phase_rejects_oversized_reviewer_notes` (AC-7), `test_complete_phase_rejects_malformed_json_reviewer_notes`.

**Task E.4 — Transaction-participation pin test (FR-5.2, AC-16).**
- New test `test_insert_phase_event_does_not_prematurely_commit_outer_transaction`: use `db.transaction()` context, call `insert_phase_event`, raise inside `with`, assert phase_events row NOT persisted.
- This PINS existing `_commit()` guard at `database.py:1551-1554`. No code change beyond E.2's ValueError.
- Pass: test passes. Retro notes #00134 as verified-false-alarm.

Commit: `feat(088): Bundle E — dual-write refactor + reviewer_notes hardening (FR-5, FR-2.4)`.

## Bundle F — Analytics pairing (FR-4, FR-7, FR-6.3)

**Task F.1 — Rewrite `_compute_durations` (FR-4.1, FR-4.2, FR-6.3).**
- Move imports `from collections import defaultdict`, `from datetime import datetime`, `from itertools import zip_longest` to module-level.
- Add module-level `_ANALYTICS_EVENT_SCAN_LIMIT = 500` (FR-7.2).
- Rewrite function signature: `_compute_durations(events: list[dict]) -> list[dict]`.
- Iterate `groups_s.keys() | groups_c.keys()` (union).
- Use `zip_longest(s_list, c_list, fillvalue=None)` for pair iteration.
- Emit `duration_seconds=None`, `missing_started`, `missing_completed` flags for unpaired rows.
- Update caller in `query_phase_analytics` (~line 1669) to pass a single merged events list.
- Pass: new tests `test_phase_duration_completed_without_started_emits_null_row` (AC-13), `test_phase_duration_imbalanced_pairs_handled` (AC-14), `test_compute_durations_isolated` (AC-19 direct unit test).

**Task F.2 — `iteration_summary` filter-then-limit (FR-7.1).**
- Fetch with `limit=_ANALYTICS_EVENT_SCAN_LIMIT`; filter `iterations is not None` in Python; sort; `results[:limit]`.
- Pass: new test `test_iteration_summary_filters_nones_before_limit` (AC-24) — seed 5 rows with iterations=None and 5 with iterations=3; limit=5; assert all 5 iterations=3 rows returned.

Commit: `feat(088): Bundle F — analytics pairing + filter-then-limit (FR-4, FR-7)`.

## Bundle C — Session-start security (FR-1)

**Task C.1 — Convert 6 `python3 -c "..."` blocks (FR-1.1).**
- Lines 60, 105, 188, 437, 599, 642: convert each from `python3 -c "..."` (double-quoted) to `python3 -c '...'` (single-quoted) with bash values passed as positional args and read via `sys.argv`.
- Pass: `grep -nE 'python3 -c "[^"]*\$' plugins/pd/hooks/session-start.sh` returns 0 matches.

**Task C.2 — Symlink-safe log open (FR-1.2).**
- In `maintenance.py::_emit_decay_diagnostic` (and parallel in `refresh.py`): replace `with open(...)` with `os.open(path, os.O_APPEND|os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW, 0o600)` + `os.fchmod` + `os.close` in finally.
- Create parent dir with `mode=0o700`.
- Pass: new test `test_influence_log_refuses_symlink_follow` (AC-2) — pre-create symlink, enable debug log, run decay, assert symlink target unchanged + no new file at symlink path.

**Task C.3 — PATH pinning + venv hard-fail + timeout (FR-1.3).**
- In `run_memory_decay`: save PATH, pin to `/usr/bin:/bin:/usr/sbin:/sbin`, verify `${PLUGIN_ROOT}/.venv/bin/python` exists (exit early if missing), detect `gtimeout`/`timeout`, fall back to Python subprocess wrapper with timeout=10.
- Pass: `grep -nE 'export PATH="/usr/bin:/bin' plugins/pd/hooks/session-start.sh` matches at least once. New hook test `test_decay_timeout_does_not_block_hook` (AC-40 fourth test) stubs CLI with `time.sleep(30)`; hook completes in <20s.

**Task C.4 — Session-start poisoned-meta integration test (AC-1, AC-3).**
- Add to `test-hooks.sh`: create test fixture with `.meta.json` containing `"project_id": "'; import os; os.system('touch /tmp/pd-088-pwned') #"`; run session-start.sh; assert `/tmp/pd-088-pwned` NOT created.
- AC-3: rename plugin venv Python temporarily; run session-start; assert no decay section in additionalContext but hook exits 0.
- Pass: both integration tests pass.

Commit: `feat(088): Bundle C — session-start heredoc fix, symlink-safe logs, PATH+timeout (FR-1)`.

## Bundle H — Test hardening (FR-10)

**Task H.1 — Autouse fixture for workflow_state_server globals (FR-6.5).**
- Add to `test_workflow_state_server.py` top-of-file:
  ```python
  @pytest.fixture(autouse=True)
  def _reset_workflow_state_globals():
      import plugins.pd.mcp.workflow_state_server as m
      saved_db, saved_unavailable = m._db, m._db_unavailable
      yield
      m._db, m._db_unavailable = saved_db, saved_unavailable
  ```
- Remove try/finally `_db` mutations in individual tests (AC-21).
- Pass: `grep -Pzo '(?s)try:.{0,200}finally:.{0,200}_db = ' plugins/pd/mcp/test_workflow_state_server.py` returns 0 matches in feature-084 test classes.

**Task H.2 — Migrate `db._conn` call sites in `test_maintenance.py` (FR-10.3, AC-36).**
- Add `MemoryDatabase.insert_test_entry(**kwargs)` public method for test seeding (or reuse existing `add_entry`).
- Replace 25+ `db._conn.execute(...)` calls in `_get_row`, `_seed_entry`, `_bulk_seed` with public method calls.
- Rename module-level `NOW` to `_TEST_EPOCH` (AC-33).
- Pass: `grep -c "db._conn" plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` returns 0.

**Task H.3 — Boundary + error-path + integration tests.**
- Add FR-10.6 integration tests: `test_concurrent_decay_and_record_influence_both_succeed_eventually`, `test_fts5_queries_still_work_after_bulk_decay` (AC-39).
- Add FR-10.7 tests: `test_empty_db_returns_all_zeros_with_no_error`, `test_nan_infinity_and_negative_zero_threshold_values_fall_back_to_default`, `test_sqlite_error_during_select_phase_returns_error_dict`, `test_session_start_decay_timeout_does_not_block_hook` (AC-40).
- Add FR-9.5 test: `test_concurrent_writer_via_decay_confidence` (AC-31) — thread A holds write lock past busy_timeout, thread B calls `decay_confidence`, asserts error-dict returned (not raised).
- Add FR-9.2 tests: augment `test_ac11a/b/c` with `capsys.readouterr()` assertions matching `r'\[memory-decay\].*memory_decay_high_threshold_days'` (AC-28).
- Add FR-10.5 test: `test_rejects_or_normalizes_naive_datetime_now` (AC-38) — pass tz-naive `now=datetime(2026,4,16,12)` to `decay_confidence`; assert behavior matches current normalization path at `maintenance.py:316-324` (attach UTC). The test PINS this branch so a future refactor that drops the normalization is caught.
- Pass: all tests pass.

**Task H.4 — Feature 084 test additions (FR-10.10, AC-43).**
- Add `test_phase_duration_handles_mismatched_started_completed_counts`.
- Add `test_insert_phase_event_rejects_invalid_event_type_and_source` (CHECK constraint negative test).
- Add `test_migration_10_rerun_on_pre_existing_rows_does_not_duplicate_backfill`.
- Add `test_record_backward_event_returns_error_json_under_db_lock`.
- Add `test_dual_write_metadata_and_phase_events_consistency_on_partial_failure`.
- Add `test_insert_phase_event_does_not_prematurely_commit_outer_transaction` (already E.4).
- Strengthen `test_ac19_metadata_still_has_phase_timing` to assert `iterations==2` and `reviewerNotes` survive round-trip (AC-41).
- Pass: all tests pass.

Commit: `feat(088): Bundle H — test hardening, 25+ db._conn migrations, 10+ new tests (FR-10)`.

## Bundle I — Skill-layer fix (FR-8)

**Task I.1 — Update `workflow-transitions/SKILL.md` `handleReviewerResponse`.**
- At lines 402-412: add explicit `project_id` resolution step BEFORE `record_backward_event` call. Drop `project_id=project_id` kwarg from the call.
- Pre-flight: `grep -rn 'record_backward_event.*project_id' plugins/pd/ docs/` — migrate any remaining callers.
- Pass: `grep -nE 'project_id\s*=' plugins/pd/skills/workflow-transitions/SKILL.md` matches variable assignment before `record_backward_event` call (not used undefined) (AC-26).

Commit: `fix(088): Bundle I — SKILL.md project_id resolution before record_backward_event (FR-8)`.

## Bundle L — Reconcile drift detection (FR-10.9)

**Task L.1 — Add `_detect_phase_events_drift` helper.**
- In `workflow_state_server.py`: add `from entity_registry.metadata import parse_metadata` import.
- Add `_detect_phase_events_drift(db, feature_type_id)` per design Bundle L.1 (Python-side status filter).
- Pass: function is callable; empty DB returns `[]`.

**Task L.2 — Wire into `_process_reconcile_check` + `_process_reconcile_apply`.**
- Extend both serialization to include `phase_events_drift` sibling JSON key.
- `_process_reconcile_apply` emits stderr warning per drift entry; does NOT modify `phase_events`.
- Pass: new tests `test_reconcile_check_reports_phase_events_drift` (AC-42), `test_reconcile_apply_does_not_modify_phase_events` (AC-42b).

Commit: `feat(088): Bundle L — reconcile drift detection for phase_events vs metadata (FR-10.9)`.

## Bundle J — Spec patches (FR-9)

**Task J.1 — Append Amendments section to 082 spec.md.**
- Add section `## Amendments (2026-04-19 — feature 088)` at end of `docs/features/082-recall-tracking-and-confidence/spec.md` with three amendments (A: AC-10 skipped_floor, B: FR-2 NULL branch, C: AC-11 capsys).
- Verify no in-place edits to original text.
- Pass: `grep -n "## Amendments" docs/features/082-recall-tracking-and-confidence/spec.md` returns exactly 1 (AC-27). Original AC-10 text `skipped_floor == 1` still present via `grep -c "skipped_floor == 1"`.

**Task J.2 — Correct maintenance.py docstring I-3 (AC-28 half).**
- Locate docstring I-3 block in `maintenance.py` claiming "clamped silently"; correct to reflect warn-on-clamp behavior.
- Pass: `grep -n "clamped silently" plugins/pd/hooks/lib/semantic_memory/maintenance.py` returns 0.

**Task J.3 — Regenerate `agent_sandbox/082-eqp.txt` (FR-9.4, AC-30).**
- Write a small reproducer script that seeds 10000 entries with `source != 'import'` (matching the 082 `test_performance_10k_entries` fixture shape), calls `decay_confidence`, captures the returned `diag` dict (`scanned`, `skipped_import`, `elapsed_ms`).
- Write `scanned=10000 skipped_import=0 elapsed_ms=<N>` to `agent_sandbox/082-eqp.txt`.
- Pass: `grep -n "skipped_import=0" agent_sandbox/082-eqp.txt` matches.

Commit: `docs(088): Bundle J — spec 082 amendments + EQP regen (FR-9)`.

## Bundle K — Process backfill (FR-11)

**Task K.1 — Create 084 retro.md.**
- Write `docs/features/084-structured-execution-data/retro.md` with AORTA sections (Aims, Outcomes, Reflections, Tune, Adopt).
- Include: list of all 084 post-release findings (#00080–#00084 known + #00117–#00137 088-discovered), lessons (SELECT *, dual-write-inside-txn anti-pattern, missing `_check_db_available`, project_id scoping), Adopt = dual-write ONLY with analytics OUTSIDE transaction.
- Pass: file exists with ≥ 50 lines (AC-44).

**Task K.2 — Add backlog #00138 for deferred sub-items (TD-6).**
- Append entry to `docs/backlog.md`: `#00138` enumerating the remaining #00116 / #00136 sub-items not covered by FR-10.7 / FR-10.10 minimums.
- Pass: `grep -n "#00138" docs/backlog.md` matches.

Commit: `docs(088): Bundle K — retroactive 084 retro.md + backlog #00138 (FR-11)`.

## Final Validation

**Task Final — NFR verification gate.**
- NFR-1: Run pytest suite `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_maintenance.py plugins/pd/hooks/lib/entity_registry/test_phase_events.py plugins/pd/mcp/test_workflow_state_server.py -v`. All pass.
- NFR-2: Post-fix test-count ≥ baseline.
- NFR-3: `./validate.sh` passes.
- NFR-5: `bash plugins/pd/hooks/tests/test-hooks.sh` passes.
- AC count: `grep -cE "^- \*\*AC-[0-9]+[a-z]?" docs/features/088-082-084-qa-hardening/spec.md` returns 47.
- Pass: all NFRs satisfied; no regression in existing tests.

## Task Count Summary

| Bundle | Tasks | Dependencies |
|--------|-------|--------------|
| 0 | 1 (baseline) | — |
| A | 4 | 0 |
| B | 4 | A |
| G | 3 | A (shares maintenance.py with B) |
| D | 4 | 0 (independent file set) |
| E | 4 | D |
| F | 2 | E (shares workflow_state_server.py) |
| C | 4 | A, B, G (C.2 modifies maintenance.py and refresh.py — serialize after A/B/G) |
| H | 4 | B, D, E, F (test updates reference new APIs) |
| I | 1 | 0 — **MUST land before D.3** (SKILL.md must stop passing project_id= before D removes the MCP parameter) |
| L | 2 | D (wires into reconcile alongside D's changes) |
| J | 3 | 0 |
| K | 2 | 0 |
| Final | 1 | ALL |

**Total: 39 tasks across 13 bundles.** Most tasks are single-file, ≤30 LOC; complex ones (E.1, F.1, D.2) are ≤100 LOC.

## Risk Register (from design, restated)

Already enumerated in design.md "Risks" section. No new risks introduced at planning time.

## Success Criteria

Plan is complete when:
1. Every design bundle has ≥ 1 task. ✓
2. Every AC has a task that verifies it. ✓ (via AC→Test mapping in design.md)
3. Dependencies are explicit (bundle ordering per TD-I). ✓
4. Each task has a concrete pass criterion. ✓
5. Final validation gate covers all NFRs. ✓
