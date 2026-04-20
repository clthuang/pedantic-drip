# Feature 089: Tasks

29 tasks across 5 bundles. Sequential dispatch.

## Bundle A — Security hardening

### Task A.1: Wire `_coerce_bool` into `read_config` (FR-1.1, #00139)
**File:** `plugins/pd/hooks/lib/semantic_memory/config.py`.
**Steps:**
1. In `read_config`, after `_coerce(raw)` call, detect bool keys from DEFAULTS: `is_bool_key = isinstance(DEFAULTS.get(key), bool)`. For those, route through `_coerce_bool(key, raw_value, DEFAULTS[key])`.
2. Rewrite `_coerce_bool` truthiness to type-exact: `if value is True or (isinstance(value, str) and value == 'true') or (isinstance(value, int) and not isinstance(value, bool) and value == 1): return True; elif value is False or ... == 'false' or ... == 0: return False; else: warn + return default`.
3. Remove module-level `_TRUE_VALUES`/`_FALSE_VALUES` frozensets (move logic inline).

**DoD:** AC-1, AC-13 pass. New test: `test_coerce_bool_routed_from_read_config` asserts `memory_decay_enabled: 'False'` → False + warning.

### Task A.2: Runtime guard on `*_for_testing` methods (FR-1.2, #00140)
**File:** `plugins/pd/hooks/lib/semantic_memory/database.py`, `plugins/pd/hooks/lib/entity_registry/database.py`.
**Steps:**
1. Add module-level helper `_assert_testing_context()` at top of each database.py that does `if not (os.environ.get('PD_TESTING') or 'pytest' in sys.modules): raise RuntimeError('for-testing helper called outside pytest')`.
2. Add `_assert_testing_context()` as FIRST statement of each `*_for_testing` method (4 in semantic_memory, 0+ in entity_registry if any exist).

**DoD:** AC-2 passes. Test must manipulate sys.modules to exercise.

### Task A.3: `_iso_utc` raises on tz-naive (FR-1.3, #00141)
**File:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`.
**Steps:**
1. Rewrite `_iso_utc`:
   ```python
   def _iso_utc(dt: datetime) -> str:
       if dt.tzinfo is None:
           raise ValueError('_iso_utc requires timezone-aware datetime')
       return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
   ```

**DoD:** AC-3 passes. Verify `test_rejects_or_normalizes_naive_datetime_now` from feature 088 still passes (calls `decay_confidence` which normalizes `now` before `_iso_utc`).

### Task A.4: Migration 10 narrow OperationalError (FR-1.4, #00142)
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`.
**Steps:**
1. At `_migration_10_phase_events` schema_version re-check (~line 1411):
   ```python
   try:
       v_row = conn.execute("SELECT version FROM schema_version").fetchone()
       if v_row and v_row[0] >= 10:
           return
   except sqlite3.OperationalError as e:
       if 'no such table' not in str(e).lower():
           raise
   ```

**DoD:** AC-4 passes.

### Task A.5: `query_phase_analytics` project_id allowlist (FR-1.5, #00143)
**File:** `plugins/pd/mcp/workflow_state_server.py`.
**Steps:**
1. After `_check_db_available` guard in `query_phase_analytics`:
   ```python
   if project_id is not None and project_id != '*' and project_id != _project_id:
       return _make_error('forbidden', 
           f'cross-project query requires project_id="*" or current project ({_project_id}); got {project_id!r}',
           'Pass project_id=None for current, "*" for all projects')
   ```
2. Keep existing `resolved_project_id` logic unchanged — now only reachable with valid project_id.

**DoD:** AC-5 passes.

### Task A.6: `execute_test_sql_for_testing` rollback on error (FR-1.6, #00144)
**File:** `plugins/pd/hooks/lib/semantic_memory/database.py`.
**Steps:**
1. Wrap execute + commit:
   ```python
   def execute_test_sql_for_testing(self, sql, params=()):
       _assert_testing_context()
       try:
           self._conn.execute(sql, params)
           self._conn.commit()
       except Exception:
           try:
               self._conn.rollback()
           except sqlite3.Error:
               pass
           raise
   ```

**DoD:** AC-6 passes.

### Task A.7: Harden O_NOFOLLOW + fchmod log-open (FR-1.7, #00154)
**File:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`, `refresh.py`.
**Steps:**
1. Before `os.open(path, flags, 0o600)`, verify parent dir ownership + mode:
   ```python
   try:
       parent_stat = LOG_PATH.parent.stat()
       if parent_stat.st_uid != os.getuid() or (parent_stat.st_mode & 0o077):
           return  # silently decline to write to insecure parent
   except OSError:
       return
   ```
2. Add `O_EXCL` to first attempt; on `FileExistsError`, reopen with append (no O_EXCL) and verify ownership via `os.fstat(fd).st_uid == os.getuid()` before writing.

**DoD:** AC-7 passes.

## Bundle B — Detection correctness

### Task B.1: Extend drift detection to all event types (FR-2.1, #00146)
**File:** `plugins/pd/mcp/workflow_state_server.py::_detect_phase_events_drift`.
**Steps:**
1. Extend iteration: for each `phase_name`, `timing` pair:
   - If `timing.get('started')` exists but no phase_events row with `event_type='started'` for that (type_id, phase): emit drift `kind='phase_events_missing_started'`.
   - If `timing.get('completed')` exists but no `event_type='completed'` row: emit drift (existing behavior).
2. Additionally, read `meta.get('skipped_phases', [])`; for each skipped phase, verify phase_events has `event_type='skipped'` row. If missing: emit `kind='phase_events_missing_skipped'`.

**DoD:** AC-8 passes.

### Task B.2: Bulk query for drift detection (FR-2.2, #00150)
**File:** `plugins/pd/mcp/workflow_state_server.py`, `plugins/pd/hooks/lib/entity_registry/database.py`.
**Steps:**
1. Add `query_phase_events_bulk(type_ids: list[str], event_types: list[str] = None, limit_per: int = 100) -> list[dict]` method to `entity_registry/database.py`. Uses chunked `WHERE type_id IN (...)` with ≤500 params per chunk.
2. Rewrite `_detect_phase_events_drift` to: (a) list active features (once); (b) call `query_phase_events_bulk([...type_ids], event_types=['started','completed','skipped'])`; (c) build `{(type_id, phase, event_type): True}` set; (d) iterate entities Python-side and diff against the set.

**DoD:** AC-9 passes (call count ≤ 2, regardless of entity count).

### Task B.3: `_resolve_project_id` helper (FR-2.3, #00151)
**File:** `plugins/pd/mcp/workflow_state_server.py`.
**Steps:**
1. Add helper:
   ```python
   def _resolve_project_id(entity: dict) -> str:
       pid = entity.get('project_id')
       if pid is None:
           return '__unknown__'
       if not pid:
           sys.stderr.write(f'[workflow-state] feature {entity.get("type_id", "?")} has empty project_id (data integrity issue)\n')
           return '__unknown__'
       return pid
   ```
2. Replace `entity.get('project_id') or '__unknown__'` at 3 call sites (lines ~658, 865, 1779).

**DoD:** AC-10 passes.

## Bundle C — Consistency fixes

### Task C.1: `backward_frequency` uses named constant (FR-3.1, #00147)
**File:** `plugins/pd/mcp/workflow_state_server.py:~1894`.
**Steps:**
1. Replace `limit=500` with `limit=_ANALYTICS_EVENT_SCAN_LIMIT`.

**DoD:** AC-11 passes.

### Task C.2: Move `_iso_utc` to `_config_utils.py` (FR-3.2, #00148)
**File:** `plugins/pd/hooks/lib/semantic_memory/_config_utils.py`, `maintenance.py`, `refresh.py`.
**Steps:**
1. Move `_iso_utc` definition to `_config_utils.py`.
2. Import in `maintenance.py` and `refresh.py`.
3. Replace inline `strftime('%Y-%m-%dT%H:%M:%SZ')` in `refresh.py:180` with `_iso_utc(datetime.now(timezone.utc))`.

**DoD:** AC-12 passes.

### Task C.3: Frozensets inside `_coerce_bool` (FR-3.3, #00149)
**File:** `plugins/pd/hooks/lib/semantic_memory/config.py`.
**Steps:**
1. Covered by Task A.1 (type-exact rewrite removes the frozensets entirely).

**DoD:** AC-13 passes (auto from A.1).

### Task C.4: Remove redundant schema_version write (FR-3.4, #00152)
**File:** `plugins/pd/hooks/lib/entity_registry/database.py:~1599-1603`.
**Steps:**
1. Delete the `INSERT INTO _metadata ... VALUES ('schema_version', '10')` block inside `_migration_10_phase_events`.
2. Verify outer `_migrate()` loop still stamps correctly (at `database.py:~3847`).

**DoD:** AC-14 passes.

### Task C.5: Trap-safe PATH pinning + Homebrew paths (FR-3.5, #00153)
**File:** `plugins/pd/hooks/session-start.sh::run_memory_decay`.
**Steps:**
1. Replace existing save/restore with:
   ```bash
   run_memory_decay() {
       local PATH_OLD="$PATH"
       # trap-safe restore: fires on any function exit including SIGINT
       trap 'export PATH="$PATH_OLD"' RETURN
       export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
       # ... existing body ...
   }
   ```
2. Remove the explicit `export PATH="$PATH_OLD"` at function end (trap handles it).

**DoD:** AC-15 passes.

### Task C.6: Module-state reset hooks (FR-3.6, #00155)
**File:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`, `refresh.py`, test files.
**Steps:**
1. Add `reset_warning_state()` public function to both `maintenance.py` and `refresh.py` — clears module-level dedup flags.
2. Existing Bundle H autouse fixture in test_maintenance.py calls it; add analogous fixture in test_refresh.py (if present) or test_maintenance.py if refresh state needs reset there.

**DoD:** AC-16 passes.

## Bundle D — Spec amendments

### Task D.1: Append Amendments section to 088 spec (FR-4.1)
**File:** `docs/features/088-082-084-qa-hardening/spec.md`.
**Steps:**
1. Append new section:
   ```markdown
   ## Amendments (2026-04-20 — feature 089)

   ### Amendment A (AC-23 scope clarification)
   **Original:** `wc -l maintenance.py refresh.py` total drops by ≥ 50 lines vs baseline.
   **Corrected:** LOC measurement scopes to Bundle A's extraction (−77 LOC confirmed in _config_utils.py). Net-pair total LOC is unconstrained because Bundles B/C.2/G add intentional complexity (overflow guard, symlink safety, uid check).

   ### Amendment B (AC-10 delegated-helper)
   **Original:** grep count ≥ 4 for `strftime('%Y-%m-%dT%H:%M:%SZ')`.
   **Corrected:** Post-fix uses `_iso_utc()` helper; `grep -cE '_iso_utc\\(' plugins/pd/hooks/lib/semantic_memory/maintenance.py ≥ 4` replaces direct strftime count. The helper itself contains the literal strftime.

   ### Amendment C (AC-34b function name)
   **Original:** `_coerce('False')` MUST return default + warning.
   **Corrected:** Implementation added separate `_coerce_bool(key, value, default)` — legacy `_coerce(raw)` preserved for non-bool string coercion. `_coerce_bool` carries the strict-truthiness contract.

   ### Amendment D (AC-22 warn_on_clamp divergence)
   **Original:** line-for-line identical between maintenance.py and refresh.py.
   **Corrected:** Per FR-6.6's documented-divergence hatch, `warn_on_clamp=True` (maintenance) vs `warn_on_clamp=False` (refresh) is intentional. `_config_utils.py` docstring captures the divergence.
   ```

**DoD:** AC-17 passes.

## Bundle E — Test hardening (12 tests)

### Task E.1: Add 12 new tests per ACs 18-29
**Files:** `test_maintenance.py`, `test_phase_events.py`, `test_workflow_state_server.py`, `test-hooks.sh`.

Tests to add (full enumerated list from spec ACs):
1. `test_coerce_bool_ambiguous_variants_parameterized` (AC-18)
2. `test_iso_utc_handles_both_branches_directly` (AC-19)
3. `test_scan_limit_zero_behavior_pinned` (AC-20)
4. `test_decay_python_subprocess_timeout_fallback` (AC-21, in test-hooks.sh)
5. `test_record_backward_event_ignores_caller_project_id_mismatch` (AC-22)
6. `test_dual_write_failure_row_remains_missing_after_subsequent_transition` (AC-23)
7. `test_migration_10_concurrent_with_live_insert_no_duplicate_semantics` (AC-24)
8. `test_reconcile_check_stable_after_manual_phase_events_insert` (AC-25)
9. `test_warn_unknown_keys_namespace_filter_and_dedup` (AC-26)
10. `test_detect_phase_events_drift_handles_sqlite_error_gracefully` (AC-27)
11. `test_complete_phase_reviewer_notes_exact_boundary_at_mcp_entry` (AC-28)
12. `test_reconcile_detects_drift_from_real_transition_failure` (AC-29)

**DoD:** All 12 tests added and passing.

## Final Validation

### Task Final.1
Run:
```
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ plugins/pd/hooks/lib/entity_registry/ plugins/pd/mcp/test_workflow_state_server.py
./validate.sh
bash plugins/pd/hooks/tests/test-hooks.sh
```

**DoD:** All pass; NFR-2 regression count ≥ 457 (088 baseline).
