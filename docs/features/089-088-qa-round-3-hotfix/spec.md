# Feature 089: 088 QA Round 3 Hotfix (Spec + Design + Plan)

Consolidates 32 findings (#00139–#00171) from feature 088's post-release adversarial review: 7 HIGH + 13 MED + 12 test gaps. Model after feature 086 (QA-round-2 for feature 085).

## Problem Statement

Feature 088 shipped 2026-04-19 as a hardening bundle closing 43 findings on features 082 and 084. Its own adversarial review (4 parallel reviewers on 088's implementation) surfaced 32 NEW issues. Most critical: `_coerce_bool` is dead code (strict truthiness hardening never runs), `query_phase_analytics` lacks project_id allowlist (cross-project data disclosure), Bundle L drift detector only checks `completed` events (misses transition-phase failures).

## Scope

### In scope (fix)

All 32 findings #00139–#00171.

### Out of scope

- Splitting `test_workflow_state_server.py` (#00159) — deferred cleanup, not correctness.
- Spec-drift AC amendments (#00145, #00156, #00157, #00158) — applied as `## Amendments (2026-04-20)` section on 088 spec, mirroring 088's treatment of 082.

## Functional Requirements

### FR-1: Security hardening

- **FR-1.1 (#00139 H):** Wire `_coerce_bool` into `read_config()` for known-bool DEFAULTS keys (`memory_decay_enabled`, `memory_decay_dry_run`, `memory_auto_promote`, etc.). Replace frozenset-based truthiness with explicit type-exact check: `if value is True or (isinstance(value, str) and value == 'true') or (isinstance(value, int) and not isinstance(value, bool) and value == 1)`.
- **FR-1.2 (#00140 H):** Add runtime guard to all `*_for_testing` methods in `database.py`: raise `RuntimeError("for-testing helper called outside pytest")` unless `os.environ.get('PD_TESTING')` or `'pytest' in sys.modules`.
- **FR-1.3 (#00141 H):** `_iso_utc(dt)` MUST raise `ValueError('_iso_utc requires timezone-aware datetime')` when `dt.tzinfo is None`. Remove the silent fall-through.
- **FR-1.4 (#00142 H):** Migration 10 schema_version re-check MUST narrow `sqlite3.OperationalError` catch: `if 'no such table' not in str(e).lower(): raise`.
- **FR-1.5 (#00143 H):** `query_phase_analytics` MUST validate `project_id` argument: reject unknown values with `_make_error('forbidden', 'cross-project query requires project_id="*" or current project', ...)`. Accepted: `None` (defaults to current), `"*"` (cross-project opt-in), `_project_id` value (explicit current). Any other string rejected.
- **FR-1.6 (#00144 H):** `execute_test_sql_for_testing` MUST wrap execute+commit in try/except with `self._conn.rollback()` + re-raise on failure.
- **FR-1.7 (#00154 M):** O_NOFOLLOW + fchmod log-open MUST: (a) pre-open stat parent and verify `st_uid == os.getuid()` and `st_mode & 0o077 == 0`; (b) add `O_EXCL` on first creation attempt; (c) on `EEXIST`, re-stat by fd and verify `st_uid == os.getuid()` before writing.

### FR-2: Detection correctness

- **FR-2.1 (#00146 H):** `_detect_phase_events_drift` MUST also check `event_type='started'` against `phase_timing[phase].get('started')` AND `event_type='skipped'` against the `skipped_phases` metadata list. Any phase with a metadata timestamp but no matching phase_events row produces a drift entry with `kind='phase_events_missing_{started|completed|skipped}'`.
- **FR-2.2 (#00150 M):** `_detect_phase_events_drift` MUST use a single bulk `SELECT type_id, phase, event_type FROM phase_events WHERE type_id IN (...)` (chunked to SQLite parameter limit if needed), then diff against `phase_timing` in Python. N+1 pattern eliminated.
- **FR-2.3 (#00151 M):** `entity.get('project_id') or '__unknown__'` MUST become `_resolve_project_id(entity)` helper that: returns `entity['project_id']` if non-empty string; if `None`, returns `'__unknown__'`; if empty string, emits stderr warning `[workflow-state] feature {type_id} has empty project_id (data integrity issue)` and returns `'__unknown__'`. Applied at all 3 call sites in `workflow_state_server.py`.

### FR-3: Consistency / de-duplication

- **FR-3.1 (#00147 M):** Replace hardcoded `limit=500` in `backward_frequency` query (`workflow_state_server.py:1894`) with `_ANALYTICS_EVENT_SCAN_LIMIT`.
- **FR-3.2 (#00148 M):** Move `_iso_utc` to `_config_utils.py` (or a new `_time_utils.py`). Import in both `maintenance.py` and `refresh.py`. Replace refresh.py's inline `strftime('%Y-%m-%dT%H:%M:%SZ')` call with `_iso_utc(datetime.now(timezone.utc))`.
- **FR-3.3 (#00149 M):** Move `_TRUE_VALUES`/`_FALSE_VALUES` inside `_coerce_bool` function body as local constants OR rename to `__TRUE_VALUES`/`__FALSE_VALUES` (double-underscore for name-mangling on module exposure).
- **FR-3.4 (#00152 M):** Remove redundant `schema_version=10` write inside `_migration_10_phase_events` (lines 1599-1603). Rely on outer `_migrate()` loop at `database.py:3847-3851`.
- **FR-3.5 (#00153 M):** `run_memory_decay` MUST use `trap 'export PATH="$PATH_OLD"' RETURN` (bash 4+) for trap-safe PATH restore. Pinned PATH MUST include `/usr/local/bin:/opt/homebrew/bin` so Homebrew gtimeout is findable on Apple Silicon.
- **FR-3.6 (#00155 M):** Add public `reset_warning_state()` function to `maintenance.py` and `refresh.py` that clears ALL module-level dedup flags. Wire into Bundle H autouse fixture (or add new `refresh` autouse fixture).

### FR-4: Spec amendments (088 → Amendments section)

- **FR-4.1 (#00145, #00156, #00157, #00158 H/M):** Append `## Amendments (2026-04-20 — feature 089)` section to `docs/features/088-082-084-qa-hardening/spec.md`. Contents:
  - Amendment A (AC-23): LOC target scope clarified — measures Bundle A's slice only (−77 LOC confirmed); net-pair-LOC unconstrained.
  - Amendment B (AC-10): `strftime('...Z')` count requirement relaxed — `_iso_utc` helper delegates format, so grep for `_iso_utc` matches ≥4 replaces direct strftime count.
  - Amendment C (AC-34b): function name `_coerce` → `_coerce_bool`. Legacy `_coerce` still exists for non-bool string coercion.
  - Amendment D (AC-22): "line-for-line identical" relaxed per FR-6.6's documented-divergence hatch for `warn_on_clamp`.

### FR-5: Test hardening

Address the 12 test gaps from #00160–#00171.

## Acceptance Criteria

### Security ACs

- **AC-1 (FR-1.1, #00139):** `pytest` test `test_coerce_bool_routed_from_read_config`: write config `memory_decay_enabled: 'False'` (capital) → `read_config()` returns dict with `memory_decay_enabled=False` (default) AND stderr matches `r'ambiguous boolean'`. Pre-fix this passes string `'False'` through unchanged (truthy); post-fix this returns False.
- **AC-2 (FR-1.2, #00140):** Test `test_for_testing_helpers_refuse_outside_pytest`: unset `PD_TESTING`, remove `pytest` from `sys.modules`, call `db.execute_test_sql_for_testing('SELECT 1')` → raises `RuntimeError`. (Note: test must re-import after mutating sys.modules to exercise the guard.)
- **AC-3 (FR-1.3, #00141):** Test `test_iso_utc_raises_on_naive_datetime`: `_iso_utc(datetime(2026,1,1,12))` → raises `ValueError`. Tz-aware input returns expected Z-suffix string.
- **AC-4 (FR-1.4, #00142):** Test `test_migration_10_rethrows_non_missing_table_operational_error`: monkeypatch `conn.execute("SELECT version FROM schema_version")` to raise `sqlite3.OperationalError('database is locked')`, call `_migration_10_phase_events` → error propagates (not swallowed).
- **AC-5 (FR-1.5, #00143):** Test `test_query_phase_analytics_rejects_unknown_project_id`: call `query_phase_analytics(project_id='arbitrary-string', query_type='raw_events')` from project A → returns `_make_error('forbidden', ...)`. Call with `project_id='*'` → succeeds. Call with `project_id='__current_project__'` (resolved value) → succeeds.
- **AC-6 (FR-1.6, #00144):** Test `test_execute_test_sql_rolls_back_on_error`: monkeypatch `self._conn.execute` to raise on a specific SQL, call `execute_test_sql_for_testing(...)` → `sqlite3.OperationalError` propagates, `self._conn.in_transaction` is False (rolled back).
- **AC-7 (FR-1.7, #00154):** Test `test_influence_log_refuses_insecure_parent_dir_mode`: create parent dir with mode 0o755 (group-readable), run diagnostic → OSError + no write. Re-run with mode 0o700 → success.

### Detection correctness ACs

- **AC-8 (FR-2.1, #00146):** Test `test_reconcile_detects_drift_for_started_and_skipped_events`: seed entity with `metadata.phase_timing.design.started = "2026-04-01T00:00:00Z"` but no phase_events `started` row. Call reconcile_check → drift entry with `kind='phase_events_missing_started'`. Analogous test for skipped_phases.
- **AC-9 (FR-2.2, #00150):** Test `test_detect_phase_events_drift_uses_bulk_query`: monkeypatch `db.query_phase_events` to track call count. Seed 10 entities with 5 phases each. Call reconcile_check. Assert `query_phase_events` called ≤ 2 times (bulk chunking), not 50+.
- **AC-10 (FR-2.3, #00151):** Test `test_resolve_project_id_distinguishes_none_from_empty`: seed entity with `project_id=''`. Call transition_phase → stderr matches `r'empty project_id'`, phase_events row has `project_id='__unknown__'`. Seed entity with `project_id=None` → no warning, same `__unknown__` fallback.

### Consistency ACs

- **AC-11 (FR-3.1, #00147):** `grep -n "limit=500" plugins/pd/mcp/workflow_state_server.py` returns 0 matches in `backward_frequency` scope; `grep -cE "_ANALYTICS_EVENT_SCAN_LIMIT" plugins/pd/mcp/workflow_state_server.py` returns ≥4 matches.
- **AC-12 (FR-3.2, #00148):** `grep -nE "strftime\('%Y-%m-%dT%H:%M:%SZ'\)" plugins/pd/hooks/lib/semantic_memory/refresh.py` returns 0 (inline format replaced with `_iso_utc` call). `_config_utils.py` exports `_iso_utc`.
- **AC-13 (FR-3.3, #00149):** `_TRUE_VALUES`/`_FALSE_VALUES` are no longer module-level in `config.py` (either local or double-underscore).
- **AC-14 (FR-3.4, #00152):** `grep -n "INSERT INTO _metadata" plugins/pd/hooks/lib/entity_registry/database.py` within `_migration_10_phase_events` function body returns 0.
- **AC-15 (FR-3.5, #00153):** `grep -n "trap.*RETURN" plugins/pd/hooks/session-start.sh` matches inside `run_memory_decay`. Pinned PATH includes `/usr/local/bin` AND `/opt/homebrew/bin`.
- **AC-16 (FR-3.6, #00155):** `reset_warning_state()` exists in both `maintenance.py` and `refresh.py`. Autouse fixture(s) call it.

### Spec amendment ACs

- **AC-17 (FR-4.1):** `docs/features/088-082-084-qa-hardening/spec.md` contains `## Amendments (2026-04-20 — feature 089)` section with 4 sub-amendments. Original AC-10, AC-22, AC-23, AC-34b text unchanged.

### Test-gap ACs (12 tests)

- **AC-18 (#00160):** `test_coerce_bool_ambiguous_variants_parameterized` covering `'TRUE'`, `' true'`, `'1.0'`, `'yes'`, `'01'`, `''`.
- **AC-19 (#00161):** `test_iso_utc_handles_both_branches_directly` — tz-aware (expect Z-suffix string) + tz-naive (expect ValueError per FR-1.3).
- **AC-20 (#00162):** `test_scan_limit_zero_behavior_pinned` — either clamp kicks in (min 1000) or raw 0 yields scanned=0.
- **AC-21 (#00163):** `test_decay_python_subprocess_timeout_fallback` — PATH stripped of gtimeout/timeout, stubbed 30s sleep, hook completes in <20s.
- **AC-22 (#00164):** `test_record_backward_event_ignores_caller_project_id_mismatch` — pass `project_id='fake'` in caller; response shows entity's real project_id resolved server-side.
- **AC-23 (#00165):** `test_dual_write_failure_row_remains_missing_after_subsequent_transition` — 2 transitions, first fails, second succeeds, first's phase_events row permanently missing.
- **AC-24 (#00166):** `test_migration_10_concurrent_with_live_insert_no_duplicate_semantics` — thread A migration (paused after schema check), thread B live INSERT, thread A resume; no dupes.
- **AC-25 (#00167):** `test_reconcile_check_stable_after_manual_phase_events_insert` — drift detected, operator inserts missing row with correct source, next reconcile_check → zero drift.
- **AC-26 (#00168):** `test_warn_unknown_keys_namespace_filter_and_dedup` — typo `memor_decay_enabled` (off-namespace) silently ignored; 3 invocations produce N warnings (pin current behavior, whatever it is).
- **AC-27 (#00169):** `test_detect_phase_events_drift_handles_sqlite_error_gracefully` — monkeypatch `db.list_entities` to raise mid-iteration, reconcile_check response shape stays valid.
- **AC-28 (#00170):** `test_complete_phase_reviewer_notes_exact_boundary_at_mcp_entry` — 10000 accepted, 10001 rejected.
- **AC-29 (#00171):** `test_reconcile_detects_drift_from_real_transition_failure` — end-to-end: run transition_phase with monkeypatched insert_phase_event failure → metadata has phase_timing but phase_events missing → reconcile_check reports drift.

## Non-Functional Requirements

- **NFR-1:** All tests pass: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ plugins/pd/hooks/lib/entity_registry/ plugins/pd/mcp/test_workflow_state_server.py`.
- **NFR-2:** No regression — 457 baseline tests from feature 088 still pass.
- **NFR-3:** `./validate.sh` passes.
- **NFR-4:** No new code files beyond `_time_utils.py` (if chosen for FR-3.2) — existing structure preferred.

## Technical Decisions

- **TD-1:** Use `os.environ.get('PD_TESTING')` OR `'pytest' in sys.modules` for FR-1.2 runtime guard. Both tolerated; either sufficient.
- **TD-2:** `_iso_utc` moves to `_config_utils.py` (not a new `_time_utils.py` module) — keep file count bounded; `_config_utils.py` already the shared helper module.
- **TD-3:** FR-1.5 project_id allowlist: implicit — current project, `"*"` literal, `_project_id` resolved value. No configurable allowlist for now.
- **TD-4:** FR-2.1 expanded drift detection: includes `started`, `completed`, `skipped`. Does NOT include `backward` (those are additive-informational events, not gaps).
- **TD-5:** Spec amendments on 088 spec (not a new retroactive patch) — same pattern as 088 used for 082.

## Design Sketch

### Bundle A — Security hardening (FR-1.1 through FR-1.7)

Files: `plugins/pd/hooks/lib/semantic_memory/config.py`, `database.py`, `maintenance.py`, `refresh.py`, `workflow_state_server.py`, `session-start.sh`.

- **FR-1.1**: In `read_config()`, identify bool keys from DEFAULTS where `isinstance(value, bool)`. For those keys, pass through `_coerce_bool` instead of `_coerce`. Replace `_TRUE_VALUES = frozenset({...})` with type-strict function body.
- **FR-1.2**: At top of each `*_for_testing` method: `if not (os.environ.get('PD_TESTING') or 'pytest' in sys.modules): raise RuntimeError(...)`.
- **FR-1.3**: `_iso_utc`: remove `if dt.tzinfo is not None` check, replace with unconditional `return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')` preceded by `if dt.tzinfo is None: raise ValueError(...)`.
- **FR-1.4**: Narrow OperationalError catch: `except sqlite3.OperationalError as e: if 'no such table' not in str(e).lower(): raise; pass`.
- **FR-1.5**: `query_phase_analytics`: validate `project_id ∈ {None, '*', _project_id}` else `_make_error('forbidden', ...)`.
- **FR-1.6**: `execute_test_sql_for_testing`: `try: ...execute...commit... except Exception: self._conn.rollback(); raise`.
- **FR-1.7**: Pre-open parent stat check; add `O_EXCL` to first open attempt; fall back to append-open on `EEXIST` with post-open fstat verification.

### Bundle B — Detection correctness (FR-2)

Files: `workflow_state_server.py`.

- **FR-2.1**: `_detect_phase_events_drift` extended to check all three event_types. Additionally read `metadata.skipped_phases` and check against `event_type='skipped'`.
- **FR-2.2**: Replace per-entity loop with single bulk query: `db.query_phase_events_bulk(type_ids=[...], event_types=['started','completed','skipped'])` — add new method if needed. Chunk on SQLite parameter limit (999).
- **FR-2.3**: Extract `_resolve_project_id(entity)` helper; apply at 3 call sites.

### Bundle C — Consistency (FR-3)

- **FR-3.1**: One-line replacement at `workflow_state_server.py:1894`.
- **FR-3.2**: Move `_iso_utc` to `_config_utils.py`; update imports in 3 files.
- **FR-3.3**: Move frozensets inside `_coerce_bool`.
- **FR-3.4**: Delete redundant schema_version write in migration 10.
- **FR-3.5**: Add `trap 'export PATH="$PATH_OLD"' RETURN`; extend pinned PATH.
- **FR-3.6**: Add `reset_warning_state()` to both modules; autouse fixture.

### Bundle D — Spec amendments (FR-4)

Append Amendments section to 088 spec. Zero code changes.

### Bundle E — Test hardening (AC-18 through AC-29)

12 new tests across `test_maintenance.py`, `test_phase_events.py`, `test_workflow_state_server.py`, `test-hooks.sh`.

## Implementation Plan

| Bundle | Tasks | Files | Risk |
|--------|-------|-------|------|
| A | 7 (one per FR) | config.py, database.py, maintenance.py, refresh.py, workflow_state_server.py, session-start.sh | HIGH (security) |
| B | 3 | workflow_state_server.py | MED |
| C | 6 | multiple | LOW |
| D | 1 | docs/features/088/spec.md | ZERO |
| E | 12 tests | test files | LOW (additive) |

Total: 29 tasks. Sequential within A/B (same files); parallel-safe otherwise.

Order: A → B → C → D → E.

## Success Criteria

1. All 29 ACs pass.
2. NFR-1 through NFR-4 satisfied.
3. Feature 089 retro.md captures lessons (especially: grep-AC anti-pattern recurrence; verified-false-alarm pattern applied if any #00139–#00171 turn out to be).
4. 088 spec amended with 4 sub-amendments.
