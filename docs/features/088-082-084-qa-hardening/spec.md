# Feature 088: Features 082 & 084 QA Hardening — Specification

## Problem Statement

8 parallel adversarial reviewers (2 per reviewer class × 2 features) surfaced 43 NEW findings on features 082 (recall-tracking-and-confidence, released 2026-04-18) and 084 (structured-execution-data, released 2026-04-18) beyond the known post-release QA backlog (#00075–#00084). The findings are documented as backlog items #00095–#00137 with precise file:line anchors and fix hints.

**Severity distribution:** 14 HIGH, 22 MED, 7 LOW.

**Adversarial reviewer coverage:**
- pd:security-reviewer (× 2) — heredoc injection, symlink clobber, cross-project leakage, migration races
- pd:code-quality-reviewer (× 2) — SELECT *, duplication, dead code, degraded-mode handling
- pd:implementation-reviewer (× 2) — spec vs code drift, vacuous test coverage, missing retros
- pd:test-deepener (× 2) — boundary equality, tz handling, transaction participation, reconciliation drift

This hardening bundle is modeled after feature 086 (QA-round-2 follow-up to feature 085).

## Scope

### In scope (fix)

All 43 findings from #00095–#00137. Spec organizes them into 9 Functional Requirement (FR) categories.

### Out of scope

- Pre-existing patterns in unrelated modules (e.g. refresh.py `.open()` patterns already accepted out-of-scope in feature 085 TD-5)
- Adding new analytics query types beyond the 4 already shipped in 084
- Rewriting migration 10 schema (only harden it)
- Reworking the semantic-memory decay algorithm (only fix correctness gaps)
- Cosmetic unicode vs ASCII in config templates (finding below the bar)

### Explicit non-goals

- **NO** new features, only hardening.
- **NO** backward-compatibility shims (per repo convention).
- **NO** rewrites — minimal surgical patches.

## Functional Requirements

### FR-1: Security — Session-Start Hook Hardening

**Findings covered:** #00095, #00097, #00112

**FR-1.1 (from #00095):** `plugins/pd/hooks/session-start.sh` MUST NOT interpolate bash variables sourced from `.meta.json` (feature slugs, project_id, artifacts_root_val) or filesystem paths into Python heredoc source code via single-quoted literals. All such values MUST be passed as `sys.argv` and read inside Python via `sys.argv[N]`.

**FR-1.2 (from #00097):** `plugins/pd/hooks/lib/semantic_memory/maintenance.py:_emit_decay_diagnostic` (and the parallel path in `refresh.py` for `influence-debug.log`) MUST open the log with `os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)` and (where supported) call `os.fchmod(fd, 0o600)` on the returned file descriptor to enforce mode regardless of umask. Symlink at the target path MUST cause the write to fail (not follow).

**FR-1.3 (from #00112):** `plugins/pd/hooks/session-start.sh::run_memory_decay` MUST (a) sanitize `PATH` to a known-safe value (`/usr/bin:/bin:/usr/sbin:/sbin`) for the subprocess invocation, and (b) hard-fail (skip decay) if the plugin venv Python binary is missing, rather than silently falling back to user `$PATH`-resolved `python3`.

### FR-2: Security — Cross-Project Isolation and Input Validation (Feature 084)

**Findings covered:** #00117, #00118, #00119, #00125, #00126, #00127

**FR-2.1 (from #00117):** `plugins/pd/mcp/workflow_state_server.py::query_phase_analytics` MUST default the project scope to the current `_project_id` (mirroring `list_features_by_phase:1314`). Cross-project queries MUST require an explicit `project_id="*"` opt-in. Unqualified calls (`project_id=None`) MUST NOT return rows from other projects.

**FR-2.2 (from #00118):** `plugins/pd/hooks/lib/entity_registry/database.py::_migration_10_phase_events` MUST be idempotent under concurrent invocation. Either (a) re-check `schema_version` as the first statement inside `BEGIN IMMEDIATE` and early-return if already ≥ 10, OR (b) add a UNIQUE index on `(type_id, phase, event_type, timestamp, source)` and use `INSERT OR IGNORE` in the backfill loop. A concurrent double-invocation MUST produce the same row-count as a single invocation.

**FR-2.3 (from #00119):** `plugins/pd/mcp/workflow_state_server.py::record_backward_event` MUST (a) reject nonexistent `type_id` (verify via `_db.get_entity(type_id)` lookup), (b) resolve `project_id` server-side from the entity record rather than trusting caller input, and (c) cap `reason` length to 500 characters (harmonized with FR-2.6 backfill cap; operators see truncation warning when exceeding).

**FR-2.4 (from #00125):** `_process_complete_phase` MUST reject `reviewer_notes` payloads exceeding 10,000 bytes at the MCP entry point, parse the JSON exactly once (not twice). In addition, defense-in-depth: `insert_phase_event` at the DB layer MUST also reject `reviewer_notes` longer than 10,000 chars (raise `ValueError` before SQL execution) — this is the authoritative bypass guard for callers that invoke the DB method directly. Migration 10 does NOT need a SQL CHECK constraint; Python-layer validation is sufficient.

**FR-2.5 (from #00126):** `record_backward_event` error path MUST use `_make_error('insert_failed', ..., ...)` consistent with sibling tools. Raw `str(e)` exception leak (`workflow_state_server.py:1643`) MUST NOT be returned to the caller.

**FR-2.6 (from #00127):** Migration 10 backfill MUST validate every timestamp value parsed from `entities.metadata` blobs via `datetime.fromisoformat(...)` inside a try/except before INSERT. Rows with unparseable timestamps MUST be skipped with a stderr warning (matching the existing malformed-metadata warning at `database.py:1423`). `backward_reason` and `backward_target` MUST be truncated to 500 characters before INSERT.

### FR-3: Correctness — Timestamp Format and Overflow Guards (Feature 082)

**Findings covered:** #00096, #00099, #00106

**FR-3.1 (from #00099):** All timestamp writes and comparisons in `plugins/pd/hooks/lib/semantic_memory/maintenance.py` MUST use a single consistent format: `strftime('%Y-%m-%dT%H:%M:%SZ')` (Z-suffix UTC). The current mixed use of `datetime.isoformat()` (produces `+00:00` suffix) and `strftime('...Z')` MUST be eliminated. The `cutoff` timestamps at `maintenance.py:361-364` MUST be regenerated via strftime.

**FR-3.2 (from #00096, part A — OverflowError):** `maintenance.py::decay_confidence` MUST wrap `timedelta(days=...)` and `now - timedelta(...)` arithmetic in a try/except that catches both `OverflowError` and `ValueError`, routing failures through the existing sqlite3.Error path (empty diagnostic, `error` field set). Config integer clamp bounds MUST be promoted to module-level named constants (`_DAYS_MIN`, `_DAYS_MAX`) with a comment warning that widening the bounds requires re-auditing overflow safety.

**NOTE:** Finding #00096 has TWO parts. Part A (OverflowError escape) is addressed here (AC-11). Part B (bool coercion for `'False'` capital-string truthiness bug) is addressed in FR-10.1 / AC-34b. Both parts MUST land for #00096 to be considered closed.

**FR-3.3 (from #00106):** The unused `now_iso` parameter in `maintenance.py::_select_candidates` MUST be removed from both the function signature and the call site at `decay_confidence:368`.

### FR-4: Correctness — Analytics Pairing (Feature 084)

**Findings covered:** #00123, #00136-zip (sub-item)

**FR-4.1 (from #00123):** `plugins/pd/mcp/workflow_state_server.py::_compute_durations` MUST iterate the UNION of `groups_s.keys()` and `groups_c.keys()`. For (type_id, phase) pairs where `started` events exist but `completed` do not, or vice-versa, the function MUST emit a result row with `duration_seconds=None` and a diagnostic marker (`missing_started: true` or `missing_completed: true`). Silently dropping unpaired rows is forbidden.

**FR-4.2 (from zip truncation in #00136):** Within a (type_id, phase) group, `_compute_durations` MUST use `itertools.zip_longest(s_list, c_list, fillvalue=None)` instead of `zip(...)`. Imbalanced pairs (e.g., 3 started + 2 completed from a crash mid-transition) MUST produce N result rows where unpaired entries have `duration_seconds=None`.

### FR-5: Transaction Safety (Feature 084)

**Findings covered:** #00124, #00134

**FR-5.1 (from #00124):** `_process_transition_phase` (`workflow_state_server.py:629-647`) and `_process_complete_phase` (`:796-807`) MUST move the `insert_phase_event` call OUTSIDE the `with db.transaction():` block. The phase_events INSERT MUST run AFTER the main transaction commits, with its own try/except. On failure, the handler MUST (a) emit stderr warning `[workflow-state] phase_events dual-write failed for {type_id}:{phase}: {type(exc).__name__}: {summary}` where `{summary}` is `str(exc)[:200]` (truncated single-line repr), and (b) include `phase_events_write_failed: true` in the response metadata dict. `entity.get('project_id') or '__unknown__'` MUST be used instead of the `entity.get('project_id', '__unknown__')` pattern (which does not apply the default when the key exists with `None` value).

**FR-5.2 (from #00134):** `plugins/pd/hooks/lib/entity_registry/database.py::insert_phase_event` MUST honor spec 084 FR-3 ("participates in existing transaction when called from within one"). Implementation: guard `self._commit()` with `if not self._conn.in_transaction` (the sqlite3 Connection attribute). When `in_transaction` is True (an outer transaction is active), the INSERT must NOT auto-commit — the outer transaction's boundary takes over. This is the standard pysqlite3 detection mechanism.

### FR-6: Code Quality — Degraded Mode, Column Lists, Helpers

**Findings covered:** #00120, #00121, #00128, #00129, #00130, #00098, #00105

**FR-6.1 (from #00120):** Both `record_backward_event` (`workflow_state_server.py:1614`) and `query_phase_analytics` (`:1653`) MUST invoke `err = _check_db_available(); if err: return err` as the FIRST statement of their body. Degraded-mode responses MUST be shape-consistent with every other MCP tool.

**FR-6.2 (from #00121):** `plugins/pd/hooks/lib/entity_registry/database.py::query_phase_events` (line ~2985) MUST replace `SELECT * FROM phase_events{where}` with an explicit column list: `SELECT id, type_id, project_id, phase, event_type, timestamp, iterations, reviewer_notes, backward_reason, backward_target, source, created_at FROM phase_events{where}`.

**FR-6.3 (from #00128):** `workflow_state_server.py::_compute_durations` MUST move `from collections import defaultdict` and `from datetime import datetime` to module-level imports. At least one direct unit test of `_compute_durations` in isolation MUST exist.

**FR-6.4 (from #00129):** `_migration_10_phase_events` MUST wrap `conn.execute("BEGIN IMMEDIATE")` inside the try block (not before it), closing the window where an exception between BEGIN and try leaves an open transaction.

**FR-6.5 (from #00130):** `plugins/pd/mcp/test_workflow_state_server.py` (and any new tests added in this feature) MUST use a pytest autouse fixture with `yield` to save/restore `workflow_state_server._db` and `_db_unavailable` globals — not try/finally inside individual test methods.

**FR-6.6 (from #00098):** `maintenance.py::_resolve_int_config` clamp behavior MUST be aligned with `refresh.py`. Either both clamp silently (no stderr warning) or both emit warnings. The docstring claim "verbatim mirror — only the stderr prefix differs" MUST be true after the fix, or updated to accurately document any intentional divergence.

**FR-6.7 (from #00105):** `_warn_and_default` and `_resolve_int_config` MUST be extracted to a shared module `plugins/pd/hooks/lib/semantic_memory/_config_utils.py`. Both `maintenance.py` and `refresh.py` MUST import from the shared module. Duplication MUST drop from ~56 lines to 0.

### FR-7: Code Quality — Dead Code and Filter Ordering

**Findings covered:** #00132, #00133

**FR-7.1 (from #00132):** `query_phase_analytics` iteration_summary branch MUST filter `iterations IS NOT NULL` BEFORE applying the caller-supplied limit. Implementation: fetch with `limit=_ANALYTICS_EVENT_SCAN_LIMIT` (the internal 500 cap), filter in Python, then `results = results[:limit]`.

**FR-7.2 (from #00133):** The internal `_ANALYTICS_EVENT_SCAN_LIMIT = 500` constant MUST be named and documented in `workflow_state_server.py`. Its effect on caller-supplied `limit` MUST be documented in the `query_phase_analytics` docstring.

### FR-8: Skill-Layer Fix (Feature 084)

**Findings covered:** #00122

**FR-8.1:** `plugins/pd/skills/workflow-transitions/SKILL.md::handleReviewerResponse` (lines 402-412) MUST resolve `project_id` explicitly before calling `record_backward_event`. Resolution order: (a) read from feature `.meta.json` if populated, else (b) call `get_entity(feature_type_id)` and extract `project_id` from the response, else (c) fall back to `None` (letting the MCP validation in FR-2.3 reject the call rather than silently passing `'__unknown__'`).

### FR-9: Spec Patches (Feature 082)

**Patch style:** All spec patches to `docs/features/082-recall-tracking-and-confidence/spec.md` are appended as an `## Amendments (2026-04-19 — feature 088)` section at the END of that spec. The amendment section lists each patched text with old-text / new-text pairs. The original spec body is left unchanged to preserve historical auditability. This preserves the "retrospective acknowledged the spec bug" signal without rewriting history.

**Findings covered:** #00100, #00101, #00107, #00108, #00109, #00110, #00111

**FR-9.1 (from #00101):** `docs/features/082-recall-tracking-and-confidence/spec.md::AC-10` MUST be patched from `skipped_floor == 1` to `skipped_floor == 2`, with an inline note explaining why (the originally-seeded low entry plus the newly-demoted medium-stale entry both count as floor on tick 2). Retro 082 has already acknowledged this.

**FR-9.2 (from #00100):** `docs/features/082-recall-tracking-and-confidence/spec.md::AC-11` MUST be patched so the success criterion explicitly requires an `assert re.search(r'\[memory-decay\].*memory_decay_high_threshold_days', captured.err)` style check. `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py::test_ac11a/b/c` MUST add `capsys` fixture usage and assert the stderr warning. The conflicting docstring I-3 in `maintenance.py` claiming "clamped silently" MUST be corrected to match the implemented warn-on-clamp behavior.

**FR-9.3 (from #00109):** `docs/features/082-recall-tracking-and-confidence/spec.md::FR-2` NULL-branch text MUST be expanded to: "If `last_recalled_at IS NULL`: first verify grace has elapsed (`created_at < now - grace_period_days`); if inside grace, skip (`skipped_grace`). If past grace, apply the tier staleness check using `created_at` as the staleness timestamp." Current text only describes the grace comparison and contradicts AC-5/AC-6.

**FR-9.4 (from #00110):** `agent_sandbox/082-eqp.txt` evidence file MUST be regenerated from the actual AC-24 test fixture (which contains zero `source=import` rows) OR the fixture MUST be expanded to include the 25% import mix claimed in the EQP. Numbers in retro.md and EQP MUST match fixture reality under FR-1's import exclusion.

**FR-9.5 (from #00108):** A new end-to-end concurrent-writer test via `decay_confidence` (not `batch_demote`) MUST be added to `test_maintenance.py`. The test MUST exercise the decay-layer `sqlite3.Error` catch under real connection-B-timing-out-while-A-holds-lock contention.

**FR-9.6 (from #00107):** `_select_candidates` SELECT MUST add `LIMIT 100000` (configurable via `memory_decay_scan_limit` config, default 100000) AND stream results via cursor iteration (not `fetchall()`). Unbounded scan must not be possible in production.

**FR-9.7 (from #00111):** The module-level `NOW = datetime(...)` in `test_maintenance.py:453` MUST be renamed `_TEST_EPOCH` (signaling test-only constant) with an accompanying module-level docstring note, OR converted to a pytest fixture. The current implicit `base=NOW` default in `_days_ago` MUST remain functional post-rename.

### FR-10: Test Hardening

**Findings covered:** #00102, #00103, #00104, #00113, #00114, #00115, #00116, #00131, #00135, #00136

**FR-10.1 (from #00102):** `plugins/pd/hooks/lib/semantic_memory/config.py::DEFAULTS` MUST register all `memory_decay_*` keys with correct types. An unknown-key warning pass MUST run at session-start for typos like `memory_decay_enabaled`. `_coerce` MUST canonicalize truthiness: accept `{True, 'true', '1', 1}` → `True` and `{False, 'false', '0', 0, ''}` → `False`, rejecting `'False'` / `'True'` capital variants with a warning.

**FR-10.2 (from #00103):** `maintenance.py::_main` CLI MUST reject invocations where `project_root.stat().st_uid != os.getuid()` with a stderr warning and non-zero exit. Cross-project config poisoning via symlinked or user-foreign project_roots MUST be blocked.

**FR-10.3 (from #00104):** `test_maintenance.py` helpers (`_get_row`, `_seed_entry`, `_bulk_seed`) MUST replace direct `db._conn.execute` access with either public API calls (`db.get_entry`, `db.add_entry`) or a new test-only method `db.insert_test_entry(...)` behind a `_for_testing` suffix. 25+ call sites MUST be migrated.

**FR-10.4 (from #00113):** `test_maintenance.py` MUST add `test_exact_threshold_boundary_is_not_stale` that seeds `last_recalled_at = iso(NOW - timedelta(days=30))` exactly and asserts `demoted_high_to_medium == 0`. Mutation `<` → `<=` at `maintenance.py:259/262` MUST fail this test.

**FR-10.5 (from #00114):** `test_maintenance.py` MUST add `test_rejects_or_normalizes_naive_datetime_now`. The implementation MUST choose: either raise `ValueError` on tz-naive `now`, or normalize by attaching UTC. Whichever is chosen MUST be pinned by the test.

**FR-10.6 (from #00115):** `test_maintenance.py` MUST add two cross-feature integration tests:
- `test_concurrent_decay_and_record_influence_both_succeed_eventually` — thread A runs `record_influence(...)` in a loop; thread B runs `decay_confidence` once; both complete.
- `test_fts5_queries_still_work_after_bulk_decay` — seed 50 stale high entries with keywords; run decay → all demote; run FTS5 MATCH query; all 50 still returned with post-decay confidence.

**FR-10.7 (from #00116):** `test_maintenance.py` MUST add boundary/error/state-transition tests:
- `test_empty_db_returns_all_zeros_with_no_error`
- `test_nan_infinity_and_negative_zero_threshold_values_fall_back_to_default`
- `test_sqlite_error_during_select_phase_returns_error_dict`
- `test_session_start_decay_timeout_does_not_block_hook`

(Remaining #00116 sub-items optional per project judgment.)

**FR-10.8 (from #00131):** `test_workflow_state_server.py::test_ac19_metadata_still_has_phase_timing` MUST be strengthened to assert `phase_timing['brainstorm']['iterations'] == 2` and, when `reviewer_notes` is passed, that `reviewerNotes` survives metadata round-trip.

**FR-10.9 (from #00135):** `plugins/pd/mcp/workflow_state_server.py::reconcile_check` / `reconcile_apply` MUST be extended to detect drift between `entities.metadata.phase_timing` and `phase_events` table rows. A drift report MUST surface when `phase_timing['phase']['completed']` exists but no `phase_events` row with `event_type='completed'` exists for that (type_id, phase). Fix-apply behavior: emit a warning; do NOT auto-insert phase_events (additive-safe).

**FR-10.10 (from #00136):** Test coverage additions for feature 084:
- `test_phase_duration_handles_mismatched_started_completed_counts`
- `test_insert_phase_event_rejects_invalid_event_type_and_source` (CHECK constraint negative)
- `test_migration_10_rerun_on_pre_existing_rows_does_not_duplicate_backfill`
- `test_record_backward_event_returns_error_json_under_db_lock`
- `test_dual_write_metadata_and_phase_events_consistency_on_partial_failure`
- `test_insert_phase_event_does_not_prematurely_commit_outer_transaction`

(Remaining #00136 sub-items optional per project judgment.)

### FR-11: Process — Retroactive Retro for Feature 084

**Findings covered:** #00137

**FR-11.1:** `docs/features/084-structured-execution-data/retro.md` MUST be created retroactively. Minimum content: (a) AORTA-style sections (Aims, Outcomes, Reflections, Tune, Adopt), (b) list of post-release QA findings (#00080–#00084 + this feature's 084-scoped findings), (c) lessons encoded for knowledge bank (especially the `SELECT *` regression, the dual-write-inside-transaction anti-pattern, the missing `_check_db_available` pattern).

## Acceptance Criteria

Each finding ID maps to one AC. ACs below are grouped by FR. Test files referenced are under `plugins/pd/hooks/lib/**/test_*.py` and `plugins/pd/mcp/test_*.py`.

### Security ACs

- **AC-1 (FR-1.1, #00095):** Crafted `.meta.json` containing `project_id: "'; import os; os.system('touch /tmp/pwned')  #"` in a test feature directory MUST NOT cause file creation when session-start runs. Verify: no `/tmp/pwned` after running `bash plugins/pd/hooks/session-start.sh` with the poisoned fixture. Additionally: all `python3 <<EOF` heredocs that previously interpolated bash vars MUST either (a) use single-quoted delimiter `<<'EOF'` (which disables expansion) and read vars via `sys.argv`, or (b) be converted to `python3 -c "..."` with arguments. Verify: `grep -nE "python3 <<EOF|python3 <<-EOF" plugins/pd/hooks/session-start.sh` MUST find zero matches (all remaining heredocs use quoted delimiter or argv-passing form).
- **AC-2 (FR-1.2, #00097):** A test that creates a symlink from `~/.claude/pd/memory/influence-debug.log` to `/tmp/target_file` before enabling `memory_influence_debug=true`, runs decay, and verifies the symlink was NOT followed (write fails; target file unchanged). Use `os.O_NOFOLLOW` semantics.
- **AC-3 (FR-1.3, #00112):** Test with plugin venv renamed / deleted: `run_memory_decay` exits cleanly (no decay run) rather than using `$PATH`-resolved `python3`. `grep -n "^PATH=" plugins/pd/hooks/session-start.sh` finds the sanitization line.
- **AC-4 (FR-2.1, #00117):** Seed two entities in different `project_id`s. Call `query_phase_analytics()` without `project_id` from project A context. Result MUST contain only project-A events. Call again with `project_id="*"`. Result MUST contain both projects.
- **AC-5 (FR-2.2, #00118):** Two concurrent threads, each opening its own DB connection at `schema_version=9`, call `_migration_10_phase_events` simultaneously (aligned via `threading.Barrier`). Final `phase_events` row count MUST equal a control single-threaded run's count. Test tolerates either implementation path (BEGIN IMMEDIATE re-check OR UNIQUE index + `INSERT OR IGNORE`).
- **AC-6 (FR-2.3, #00119):** `record_backward_event(type_id="feature:nonexistent-xyz", ...)` MUST return error JSON (not insert). `record_backward_event(type_id=real, reason="x" * 3000)` MUST truncate reason to 500 chars (matches FR-2.3 harmonized cap).
- **AC-7 (FR-2.4, #00125):** `_process_complete_phase(..., reviewer_notes="x" * 20000)` MUST return error JSON rejecting the oversized payload.
- **AC-8 (FR-2.5, #00126):** `record_backward_event` error response MUST match `{error: True, error_type: str, message: str, recovery_hint: str}` shape.
- **AC-9 (FR-2.6, #00127):** Test: seed an entity with `metadata.phase_timing.design.started = "not-a-date"`. Run `_migration_10_phase_events`. Row MUST be skipped; stderr warning emitted; no unparseable timestamp in phase_events table.
- **AC-9b (FR-2.6, #00127 truncation):** Seed an entity with `metadata.backward_history = [{"reason": "x" * 800, "target": "y" * 800, "timestamp": "2026-04-01T00:00:00Z"}]`. Run `_migration_10_phase_events`. Resulting `phase_events.backward_reason` and `backward_target` MUST have `length() == 500` (truncated). Original `entities.metadata` blob unchanged.

### Correctness ACs

- **AC-10 (FR-3.1, #00099):** `grep -n "datetime.isoformat()" plugins/pd/hooks/lib/semantic_memory/maintenance.py` finds zero matches. `grep -n "strftime('%Y-%m-%dT%H:%M:%SZ')" plugins/pd/hooks/lib/semantic_memory/maintenance.py` finds ≥ 4 matches (cutoffs + now).
- **AC-11 (FR-3.2, #00096):** With clamp widened to 10_000_000 days in a test-config and `now = datetime(MAXYEAR, 12, 31)`, `decay_confidence` MUST return the error-dict shape (not raise `OverflowError`). Named constants `_DAYS_MIN` / `_DAYS_MAX` exist at module scope.
- **AC-12 (FR-3.3, #00106):** `inspect.signature(maintenance._select_candidates)` MUST NOT contain `now_iso` parameter.
- **AC-13 (FR-4.1, #00123):** Seed 3 phase_events rows for (type_id=X, phase=design): completed@T1, completed@T2 (no started rows). Call `query_phase_analytics(query_type='phase_duration')`. Result MUST contain a row for (X, design) with `duration_seconds=None` and `missing_started=true`.
- **AC-14 (FR-4.2, #00136):** Seed 3 started + 2 completed for (X, design). Result MUST contain 3 rows; the third started pair has `duration_seconds=None`.

### Transaction ACs

- **AC-15 (FR-5.1, #00124):** Monkeypatch `insert_phase_event` to raise `sqlite3.IntegrityError`. Call `transition_phase(...)`. Main transaction MUST commit (assert entity metadata update landed). Response dict MUST contain `phase_events_write_failed: true`. stderr (via capsys) MUST match `r'\[workflow-state\] phase_events dual-write failed for'`. Baseline: before the fix, both writes rollback silently.
- **AC-16 (FR-5.2, #00134):** Test a wrapper that opens an outer `db.transaction()`, calls `insert_phase_event`, then raises inside the wrapper. On rollback, the phase_events row MUST NOT persist (proving it participated in the outer transaction, not auto-committed).

### Quality ACs

- **AC-17 (FR-6.1, #00120):** With `_db_unavailable=True`, `record_backward_event(...)` and `query_phase_analytics(...)` return the standard `_make_error` shape.
- **AC-18 (FR-6.2, #00121):** `grep -n "SELECT \\* FROM phase_events" plugins/pd/hooks/lib/entity_registry/database.py` finds zero matches (except inside test files).
- **AC-19 (FR-6.3, #00128):** Direct unit test `test_compute_durations_isolated(...)` exists. `grep -n '^from collections import defaultdict' plugins/pd/mcp/workflow_state_server.py` returns exactly one match whose line number is strictly less than the first line matching `def _compute_durations`. Same semantic check for `from datetime import datetime`.
- **AC-20 (FR-6.4, #00129):** `_migration_10_phase_events` code layout: `try:` line precedes `conn.execute("BEGIN IMMEDIATE")` line.
- **AC-21 (FR-6.5, #00130):** `grep -n "try:.*finally:.*_db = " plugins/pd/mcp/test_workflow_state_server.py` (multiline) finds zero matches in feature-084 test classes.
- **AC-22 (FR-6.6, #00098):** Both `maintenance.py::_resolve_int_config` and `refresh.py::_resolve_int_config` MUST be line-for-line identical (except for docstring prefix string). Verify via diff after extracting the shared helper per FR-6.7.
- **AC-23 (FR-6.7, #00105):** `plugins/pd/hooks/lib/semantic_memory/_config_utils.py` exists with `_warn_and_default` and `_resolve_int_config` functions. Both `maintenance.py` and `refresh.py` import from it. `wc -l maintenance.py refresh.py` total drops by ≥ 50 lines vs baseline.
- **AC-24 (FR-7.1, #00132):** Seed 10 completed events; 5 have `iterations=None`, 5 have `iterations=3`. Call `query_phase_analytics(query_type='iteration_summary', limit=5)`. Result MUST contain all 5 rows with `iterations=3` (filter-then-limit).
- **AC-25 (FR-7.2, #00133):** `grep -n "_ANALYTICS_EVENT_SCAN_LIMIT" plugins/pd/mcp/workflow_state_server.py` matches.

### Skill ACs

- **AC-26 (FR-8.1, #00122):** `grep -n "project_id" plugins/pd/skills/workflow-transitions/SKILL.md` (lines 395-415) shows `project_id` variable assigned before the `record_backward_event` call (not used undefined).

### Spec Patch ACs

- **AC-27 (FR-9.1, #00101):** `docs/features/082-recall-tracking-and-confidence/spec.md` contains a section titled `## Amendments (2026-04-19 — feature 088)` with an entry for AC-10 replacing `skipped_floor == 1` with `skipped_floor == 2`. `grep -n "## Amendments" docs/features/082-recall-tracking-and-confidence/spec.md` matches exactly once. Original AC-10 in-place text is NOT modified.
- **AC-28 (FR-9.2, #00100):** Tests `test_ac11a/b/c` include `capsys.readouterr()` and `assert re.search(r'\[memory-decay\].*memory_decay_high_threshold_days', captured.err)`.
- **AC-29 (FR-9.3, #00109):** Spec 082 Amendment section (per patch style above) contains a FR-2 NULL-branch revision matching the reproducible text in FR-9.3. Original FR-2 in-place text is NOT modified.
- **AC-30 (FR-9.4, #00110):** **Preferred (option A — zero code change):** `agent_sandbox/082-eqp.txt` is regenerated to reflect `scanned=10000, skipped_import=0` matching the existing AC-24 fixture. Verify via `grep -n "skipped_import=0" agent_sandbox/082-eqp.txt`. **Option B** acceptable only if implementer documents in feature 088 retro.md why an expanded fixture adds value; then `grep -n "skipped_import=2500" agent_sandbox/082-eqp.txt` AND the updated fixture in `test_maintenance.py` seed includes 2500 `source=import` rows.
- **AC-31 (FR-9.5, #00108):** New test `test_concurrent_writer_via_decay_confidence` in `test_maintenance.py` exists. Thread A holds write lock; thread B calls `decay_confidence` which hits busy_timeout; B returns error-dict (not raises).
- **AC-32 (FR-9.6, #00107):** `grep -n "LIMIT" plugins/pd/hooks/lib/semantic_memory/maintenance.py` matches in `_select_candidates`. Default limit is 100000.
- **AC-33 (FR-9.7, #00111):** `grep -n "^_TEST_EPOCH\|^NOW " plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` matches `_TEST_EPOCH` (or pytest fixture).

### Config ACs

- **AC-34 (FR-10.1, #00102):** `plugins/pd/hooks/lib/semantic_memory/config.py::DEFAULTS` contains `memory_decay_enabled`, `memory_decay_high_threshold_days`, `memory_decay_medium_threshold_days`, `memory_decay_grace_period_days`, `memory_decay_dry_run` keys. Typo `memory_decay_enabaled: true` in config emits stderr warning at session-start.
- **AC-34b (FR-10.1, #00096 part B):** `_coerce` accepts `{True, 'true', '1', 1}` as True and `{False, 'false', '0', 0, ''}` as False (case-sensitive lowercase). `_coerce('False')` (capital F) MUST return the default value (not True) AND emit stderr warning matching `r'ambiguous boolean'`. `_coerce('True')` (capital T) same. Test pins both via `capsys.readouterr()`.
- **AC-35 (FR-10.2, #00103):** Running `maintenance.py --project-root /foreign/user/path` (simulated with mock uid) exits non-zero with stderr warning.
- **AC-36 (FR-10.3, #00104):** `grep -n "db._conn" plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` finds fewer matches than baseline (migrated to public API or `_for_testing` method).

### Test ACs

- **AC-37 (FR-10.4, #00113):** `test_exact_threshold_boundary_is_not_stale` exists and asserts `demoted_high_to_medium == 0`.
- **AC-38 (FR-10.5, #00114):** `test_rejects_or_normalizes_naive_datetime_now` exists.
- **AC-39 (FR-10.6, #00115):** Both integration tests exist and pass with strengthened assertions:
  - `test_concurrent_decay_and_record_influence_both_succeed_eventually`: post-run, assert `entries` table shows decay happened (≥1 row has `confidence='medium'` for previously-high seeded entries) AND `influence_log` table has ≥ N rows from the record_influence loop (N = loop iteration count).
  - `test_fts5_queries_still_work_after_bulk_decay`: seed 50 entries with a distinctive shared keyword. After decay: (a) FTS5 `MATCH 'keyword'` query returns all 50 rows, (b) all returned rows have `confidence IN ('medium', 'low')`, (c) `last_recalled_at` on those rows is unchanged (decay does not touch recall timestamps).
- **AC-40 (FR-10.7, #00116):** All 4 enumerated tests exist with concrete assertions:
  - `test_empty_db_returns_all_zeros_with_no_error`: run `decay_confidence` on empty DB; return dict has `scanned=0, demoted_*=0, skipped_*=0, error` key absent.
  - `test_nan_infinity_and_negative_zero_threshold_values_fall_back_to_default`: pass `memory_decay_high_threshold_days=float('nan')` and `float('inf')`; assert default (30) used and stderr warning emitted.
  - `test_sqlite_error_during_select_phase_returns_error_dict`: monkeypatch `db._conn.execute` for SELECT path to raise `sqlite3.OperationalError('disk I/O error')`; assert return dict has `error` key, demoted counts 0.
  - `test_session_start_decay_timeout_does_not_block_hook`: stub the maintenance CLI with `time.sleep(30)`; run `bash session-start.sh` with timeout enforced via `subprocess.run(..., timeout=5)` from the pytest wrapper (portable Python-side enforcement); assert `TimeoutExpired` NOT raised on the hook wrapper (hook itself honored its internal timeout budget and returned early), exit code 0, script completes in < 10s wall time, no 'Decay:' line in JSON additionalContext.
- **AC-41 (FR-10.8, #00131):** Strengthened `test_ac19_metadata_still_has_phase_timing` includes both `iterations == 2` and `reviewerNotes` assertions.
- **AC-42 (FR-10.9, #00135):** `reconcile_check` returns a drift entry for metadata-vs-phase_events mismatch; test seeds the mismatch and asserts.
- **AC-42b (FR-10.9, #00135):** After `reconcile_check` reports drift, `reconcile_apply` MUST NOT modify `phase_events` table rows. Assert: post-apply `phase_events` row count equals pre-apply count; stderr warning emitted via capsys.
- **AC-43 (FR-10.10, #00136):** All 6 enumerated tests exist and pass.

### Process ACs

- **AC-44 (FR-11.1, #00137):** `docs/features/084-structured-execution-data/retro.md` exists with non-empty content (≥ 50 lines) including AORTA sections.

## Non-Functional Requirements

- **NFR-1:** All new tests MUST pass with the correct venv: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_maintenance.py plugins/pd/hooks/lib/entity_registry/test_phase_events.py plugins/pd/mcp/test_workflow_state_server.py`.
- **NFR-2:** No regression in existing tests. Before any code change, run `plugins/pd/.venv/bin/python -m pytest --collect-only -q plugins/pd/hooks/lib/semantic_memory/test_maintenance.py plugins/pd/hooks/lib/entity_registry/test_phase_events.py plugins/pd/mcp/test_workflow_state_server.py 2>&1 | tail -5` and record output to `agent_sandbox/088-baselines.txt`. The file MUST include: (a) pre-fix git SHA, (b) exact pytest command, (c) final integer test-count line. Post-fix invocation of the same command MUST return count ≥ baseline. No existing test function may be deleted.
- **NFR-3:** `./validate.sh` MUST pass.
- **NFR-4:** No new files under `plugins/pd/` that do not fit the existing structure. New shared helper `_config_utils.py` is acceptable per the structure.
- **NFR-5:** Hook integration tests `bash plugins/pd/hooks/tests/test-hooks.sh` MUST pass.
- **NFR-6:** Changes MUST NOT modify features 082's retro.md (it is historical).

## Technical Decisions

- **TD-1:** No `backward_history` analytics changes — out of scope.
- **TD-2:** ReDoS-style defensive timeouts (as done in feature 086 #00085) are NOT required for feature 082's regex work, since decay has no regex-generated-sample path. N/A.
- **TD-3:** The `_check_db_available` addition for new 084 MCP handlers is the authoritative fix; no reorder of MCP tool decoration order.
- **TD-4:** Spec 082 patches (FR-9.1 through FR-9.7) modify a completed feature's spec. This is permitted because: (a) retro acknowledges the spec bug, (b) no implementation changes to 082 follow from the spec patch itself (only the EQP regen in FR-9.4 and tests in FR-9.2/9.5/9.6/9.7 require code changes). Pre-fix, the spec misled future maintainers.
- **TD-5:** Retroactive retro for 084 (FR-11.1) is backfill documentation, not rewriting history. The retro describes what happened and captures the missed learnings for the knowledge bank.
- **TD-6:** FR-10.7 mandates exactly the 4 enumerated tests (boundary-empty-DB, NaN/Inf config, sqlite-error-during-select, session-start-timeout). FR-10.10 mandates exactly the 6 enumerated tests. Any remaining sub-items from #00116 or #00136 listed in the original QA report are PRE-DEFERRED to backlog item #00138 ("082/084 remaining test-gap sub-items, deferred from feature 088"), which MUST be added to docs/backlog.md before the implement phase concludes. This prevents silent scope reduction.
- **TD-7:** FR-6.7 extracts duplicated helpers to `_config_utils.py`. Despite being a refactor, this is accepted as hardening because the duplication was the ROOT CAUSE of finding #00098 (silent divergence between `maintenance.py` and `refresh.py`). Keeping two copies risks the same bug re-emerging.
- **TD-8:** `agent_sandbox/082-eqp.txt` is acknowledged as non-ephemeral evidence. CLAUDE.md's "temporary files" description is aspirational; retro evidence files persist. A follow-up backlog item may migrate them to `docs/features/{feature}/evidence/` but that is out of scope here.
- **TD-9:** AC count may exceed finding count when a single finding requires multiple ACs (e.g., #00096 split to AC-11 + AC-34b, #00135 split to AC-42 + AC-42b, #00127 split to AC-9 + AC-9b). Final AC count at implementation start: 47 (AC-1 through AC-44 plus AC-9b, AC-34b, AC-42b). Success Criteria #1 updated accordingly.

## Dependencies

- Feature 086 autouse-fixture pattern for module globals (already in repo).
- `os.O_NOFOLLOW` availability on macOS/Linux (both supported; Windows not supported — session-start hook is bash-only so N/A).
- `itertools.zip_longest` (stdlib).
- `shlex.quote` if adopted for FR-1.1 (stdlib).

## Success Criteria

Feature 088 is complete when:
1. All 47 ACs pass (AC-1 through AC-44 plus AC-9b, AC-34b, AC-42b). Verify count via `grep -cE "^- \*\*AC-[0-9]+[a-z]?" docs/features/088-082-084-qa-hardening/spec.md` equals 47.
2. `NFR-1` through `NFR-5` are satisfied.
3. Retro.md for feature 088 captures lessons (including the "adversarial parallel review surfaces 43 findings in ~15 min" meta-learning).
4. Retro.md for feature 084 exists (FR-11.1).
5. Spec 082 patches land (FR-9.1–9.3).
