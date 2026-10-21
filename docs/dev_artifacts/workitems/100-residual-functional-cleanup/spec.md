# Specification: Residual Functional Cleanup (100) — AUDIT-ONLY

## Outcome

**Implementation phase findings: ALL 7 HIGH items were already silently shipped by features 088-091.** Feature 100's actual work was a verification audit + backlog closure pass. Zero new code change required.

## Problem Statement (original)

After feature 099 shipped the asymmetric-backlog-detection infrastructure, an honest audit surfaced 7 truly-open HIGH-severity functional items concentrated in `semantic_memory/`, `workflow_state_server.py`, and `session-start.sh`. These appeared to be real primary/secondary defense gaps. Close them in one focused pass.

## Verification Findings

Each item was code-level verified before closure marker was applied:

| ID | Surface checked | Status |
|----|-----------------|--------|
| #00139 | `config.py:51-87, 189` | `_coerce_bool` defined + wired in `read_config()`. Type-exact checks; no frozenset hash collapse. **Shipped feature 089 FR-1.1.** |
| #00140 | `database.py:17, 866, 901, 920, 939` | `_assert_testing_context()` guards all 4 `*_for_testing` helpers. **Shipped feature 088.** |
| #00141 | `maintenance.py:387` (`feature 089 FR-1.3` comment) | `_iso_utc` rejects naive datetimes. **Shipped feature 089 FR-1.3.** |
| #00142 | `database.py:1186-1203` | Migration loop refactored to `BEGIN IMMEDIATE` + global try/raise; no per-migration silent except. **Refactored away.** |
| #00143 | `workflow_state_server.py:1909` (`feature 089 FR-1.5` comment) | `query_phase_analytics` has project_id allowlist. **Shipped feature 089 FR-1.5.** |
| #00146 | `workflow_state_server.py:1054` | `_detect_phase_events_drift` checks `["started", "completed", "skipped"]`. **Extended.** |
| #00172 | `test-hooks.sh:3196+` | Test sources `session-start.sh` and calls `run_memory_decay` directly to exercise the shell selector. **Shipped feature 091.** |

## Closures Applied (this feature's only deliverable)

- `docs/backlog.md` — 7 HIGH items struck through with verified-feature-marker rationale per code-level verification.

## Implication for Backlog Hygiene

The W2 asymmetric-backlog-growth pattern is now concretely measurable: **7 HIGH-severity items remained "active" in backlog.md for 2-3 weeks after their fixes shipped** because no one closed them. Feature 099's `check_active_backlog_size` doctor warning was correctly signaling backlog asymmetry, but the new `/pd:cleanup-backlog` only archives strikethrough/closed items — it cannot detect "shipped but not marked" cases.

This is a **follow-up signal for a future feature:** an automated closure-detector that scans backlog items mentioning `file:line` references against current code to flag items where the cited issue no longer exists. Filed as observation, not a feature commitment.

## Out of Scope

Per project directive ("focus on primary plugin features and primary/secondary defense; anything beyond that is most likely black swan, don't over-invest"):

- The 92 MED/LOW non-testability items still open — likely many are also silently-shipped; would require code-level verification per item. Defer until either: (a) a doctor-detected real production regression, or (b) a future automated closure-detector feature.
- The 57 testability items in `/pd:test-debt-report` — separate triage decision (Option A/B/C/D from earlier).
- Ad-hoc test-hardening of any of the 7 confirmed-shipped fixes.

## Closures NOT applied (architectural decision)

- `#00144` — try/except + rollback in test-only helper. CIRCULAR over-defensive on test infrastructure. Closed with rationale.
- `#00145` — AC-23 LOC accounting. Process artifact, not user-facing defense. Closed with rationale.

## Original Empirical Verifications (kept for reference)

```text
>>> hash(True) == hash(1) == hash(1.0)  → True   (Python hash collapses — frozenset bug rationale for #00139)
>>> {True, 1, 1.0}                       → {True}   (single element due to hash collapse)
```

## Provenance

- 7 HIGH backlog items selected from active backlog post-feature-099 audit.
- Implementation phase verified each item against current code; all 7 found already shipped.
- Project directive: "focus on primary plugin features and primary and secondary defense; anything beyond that is most likely black swan, don't over-invest."

## Triage Filter Applied

Per project directive: focus on **primary plugin features + primary/secondary defense**. Edge cases, circular over-defensive testing, and black-swan scenarios are explicitly out of scope.

**Items dropped per filter (closed in backlog.md with rationale, NOT in this feature's scope):**
- `#00144` — try/except + rollback inside test-only helper (`execute_test_sql_for_testing`). Defensive code on testing infrastructure = the recursive test-hardening anti-pattern feature 096 closed. #00140's tripwire catches the only realistic harm scenario.
- `#00145` — AC-23 LOC accounting drift. Process artifact, not user-facing defense.

**Items already shipped silently (closed with `(fixed in feature:097)` markers):**
- `#00247-#00252` — TestIso8601PatternSourcePins coverage gaps. Verified at lines 2289-2417 of `test_database.py`.

## Success Criteria

- [ ] All 7 in-scope HIGH items have closure markers in `docs/backlog.md` (`(fixed in feature:100)`).
- [ ] `./validate.sh` exits 0.
- [ ] No new pytest regressions vs develop baseline (3264 passing).
- [ ] `bash plugins/pd/scripts/doctor.sh` runs in < 3s and shows the same Project Hygiene structure as feature 099 (no new warnings).
- [ ] Each FR has at least one behavioral test pinning the fix.

## In Scope (7 FRs, one per HIGH)

### FR-1 (#00139): Wire `_coerce_bool` and replace frozenset truthiness in `config.py`

**Surface:** `plugins/pd/hooks/lib/semantic_memory/config.py:59`
**Defense layer:** Primary correctness — claimed AC-34b strict-truthiness hardening doesn't actually ship today.
**Fix:**
1. Wire known-bool DEFAULTS keys through `_coerce_bool` in `read_config()`.
2. Replace `frozenset({True, 'true', '1', 1})` with type-exact checks (`value is True OR value == 'true' OR value == '1'`). The frozenset collapses `1`/`True`/`1.0` via Python's hash-equality.
3. Add unit test asserting strict truthiness: `_coerce_bool('k', 1, False)` rejects integer 1, accepts only string `'true'` / `'1'` / boolean `True`.

**Empirical:**
```text
>>> hash(True) == hash(1) == hash(1.0)  → True   (Python hash collapses)
>>> {True, 1, 1.0}                       → {True}   (single element due to hash collapse — frozenset bug)
```

**AC:** Test asserts `_coerce_bool` rejects integer `2` and accepts only canonical truthy strings + booleans. Production uses `_coerce_bool` for at least one DEFAULTS key after the fix (`grep -E '_coerce_bool\(' config.py read_config.py | wc -l` ≥ 1).

### FR-2 (#00140): Production-bypass tripwire on `*_for_testing` helpers

**Surface:** `plugins/pd/hooks/lib/semantic_memory/database.py:875-920`
**Defense layer:** Secondary — production callers should never reach test helpers; this is a tripwire, not a primary control.
**Fix:** Add minimal guard at function entry:
```python
def execute_test_sql_for_testing(self, sql, params=()):
    if 'pytest' not in sys.modules and not os.environ.get('PD_TESTING'):
        raise RuntimeError("execute_test_sql_for_testing called outside test context")
    ...
```
Apply to all 4 helpers: `execute_test_sql_for_testing`, `fetch_row_for_testing`, `insert_test_entry_for_testing`, `insert_test_entries_bulk_for_testing`.

**AC:** Test asserts that calling `execute_test_sql_for_testing` from a subprocess WITHOUT `PD_TESTING=1` AND without pytest in sys.modules raises RuntimeError.

### FR-3 (#00141): Reject tz-naive in `_iso_utc(dt)`

**Surface:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py:68` (also `_config_utils.py` per feature 096 relocation)
**Defense layer:** Primary correctness — non-UTC host + naive `datetime.now()` → wrong cutoffs → wrong decay decisions.
**Fix:** Replace silent `if dt.tzinfo is not None: dt = dt.astimezone(timezone.utc)` conditional with explicit `if dt.tzinfo is None: raise ValueError("_iso_utc requires tz-aware datetime")`.

**Empirical:**
```text
>>> from datetime import datetime, timezone
>>> dt_naive = datetime(2026, 4, 29, 12, 0, 0)
>>> dt_naive.tzinfo is None                   → True   (would have silently produced wrong cutoff)
>>> dt_aware = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
>>> dt_aware.tzinfo is timezone.utc           → True
```

**AC:** Test asserts `_iso_utc(datetime.now())` (naive) raises `ValueError`. Production callers in maintenance.py and refresh.py confirmed tz-aware via grep (`grep -E 'datetime\.now\(\)' maintenance.py refresh.py | wc -l` returns 0; all use `datetime.now(timezone.utc)`).

### FR-4 (#00142): Narrow Migration 10 except clause

**Surface:** `plugins/pd/hooks/lib/semantic_memory/database.py:1411`
**Defense layer:** Primary defense — silent DB corruption masking would let migrations proceed against a locked or partially-migrated DB.
**Fix:** Replace bare `except sqlite3.OperationalError:` with narrow check:
```python
except sqlite3.OperationalError as e:
    if 'no such table' not in str(e).lower():
        raise
    # Original behavior only when table genuinely missing
```

**AC:** Test asserts that a non-`no such table` `OperationalError` (e.g., `database is locked`) propagates instead of being silently caught.

### FR-5 (#00143): Allowlist `project_id` in `query_phase_analytics`

**Surface:** `plugins/pd/hooks/lib/workflow_engine/workflow_state_server.py:1840`
**Defense layer:** Primary security — cross-project data leak. Session in project A can dump project B analytics today.
**Fix:** Validate `project_id` parameter against `{current_project, '*' (with explicit caller intent), allowlist from config}`. Reject unknown project_ids with a clear error JSON.

**AC:** Test asserts `query_phase_analytics(project_id='other-project')` returns error JSON when `other-project` is not the current project AND not in allowlist. Test asserts `project_id='*'` is accepted only when explicit `cross_project=True` flag is also set.

### FR-6 (#00146): Extend drift detection to non-completed events

**Surface:** `plugins/pd/hooks/lib/workflow_engine/workflow_state_server.py:1019`
**Defense layer:** Primary observability — operators currently never see warnings for failed transitions.
**Fix:** Extend `_detect_phase_events_drift` to cross-check:
1. `phase_timing[phase]['started']` against `event_type='started'` rows.
2. `skipped_phases` against `event_type='skipped'` rows.
3. Existing `completed` check unchanged.

**AC:** Test asserts that a transition with `started` event but missing `phase_timing.started` is flagged as drift. Same for `skipped`.

### FR-7 (#00172): Exercise the shell selector in AC-21 test

**Surface:** `plugins/pd/hooks/tests/test-hooks.sh:~2996-3029` (AC-21 `test_decay_python_subprocess_timeout_fallback`) + `plugins/pd/hooks/session-start.sh::run_memory_decay`
**Defense layer:** Primary — the shell selector (`if command -v gtimeout/timeout`) IS production code path; testing it bypasses the actual selector.
**Fix:** Replace inline-Python wrapper with subprocess invocation that sources session-start.sh and calls `run_memory_decay`:
```bash
bash -c 'source plugins/pd/hooks/session-start.sh; PATH=/var/empty run_memory_decay'
```
Assert wall-time < 20s + `subprocess timeout (10s)` stderr message.

**AC:** Replacing `gtimeout` with `false` (always-fail) AND `timeout` with `false` AND ensuring `python3 -c subprocess.run(timeout=10)` is the active fallback path: test still passes.

## Out of Scope

- Testability MEDs (57 items in `/pd:test-debt-report`) — separate triage decision.
- Quality LOW items in archived sections.
- The 6 testability HIGHs already silently shipped by feature 097 (already closed).
- W8 KB ↔ semantic-memory DB divergence (#00018, #00053) — separate project decision.
- Refactoring or simplification beyond what each FR requires.
- Adding tests beyond the one AC-pinning test per FR. Per project directive: avoid circular over-defensive testing.

## Non-Functional Requirements

**NFR-1 (Surgical scope):** Each FR is a 5-30 LOC change. Total feature LOC delta < 200 lines (excluding test LOC). No refactoring beyond what each fix requires.

**NFR-2 (Backwards compatibility):** No breaking API changes. Production callers of `execute_test_sql_for_testing` remain compatible (they're test-only callers; they'll set PD_TESTING=1 in conftest.py if not already in pytest context). FR-3 tz-aware requirement is enforced via runtime error, not API change.

**NFR-3 (No regressions):** `plugins/pd/.venv/bin/python -m pytest plugins/pd/` produces zero new failures vs develop baseline.

**NFR-4 (Test discipline per directive):** ONE behavioral test per FR. NO test-deepening, NO mutation testing, NO above-spec-coverage assertions. The test exists to pin the fix; broader coverage is explicit out-of-scope per the recursive-hardening anti-pattern.

## Provenance

- 7 HIGH backlog items selected from active backlog post-feature-099 audit.
- 2 HIGH items closed-with-rationale (circular over-defensive / process artifact).
- 6 HIGH items closed-with-marker (already shipped by feature 097).
- Project directive: "focus on primary plugin features and primary and secondary defense; anything beyond that is most likely black swan, don't over-invest."
