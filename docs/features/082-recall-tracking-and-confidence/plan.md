---
last-invoked: 2026-04-16
feature: 082-recall-tracking-and-confidence
---

# Plan: Confidence Decay Job

## Implementation Order

```
Phase 0: Baselines (test count, warning count, impacted-test audit)
    ↓
Phase 1: maintenance.py helpers — TDD red→green per helper
    ↓
Phase 2: database.py additions — TDD: batch_demote + _execute_chunk + busy_timeout_ms kwarg
    ↓
Phase 3: decay_confidence public function + CLI entry — TDD red→green
    ↓
Phase 4a: Write AC-21/22 session-start integration tests (TDD red)
    ↓
Phase 6: Existing-test audit + remediation (MUST complete before session-start wiring lands)
    ↓
Phase 4b: session-start.sh wiring (main reorder + run_memory_decay + display-prepend) → Phase 4a tests go green
    ↓
Phase 5: Config templates + docs sync                                 [PARALLEL with Phase 4 after Phase 3]
    ↓
Phase 7: Final verification (full test suite, validate.sh, test-hooks.sh, EXPLAIN QUERY PLAN capture for retro)
```

**Critical sequencing (per 081 retrospective learning):** Phase 6 remediation MUST precede Phase 4b (session-start wiring). Although 082 does not inject a new MCP response field like 081 did, the session-start reorder (moving `build_memory_context` to run AFTER `run_memory_decay`) could trip any test that asserts the exact sequence of session-start output sections. The Phase 0 audit enumerates which existing hook tests assert on output-order; Phase 6 remediates them before Phase 4b lands the reorder. Without this ordering, enabling the decay invocation with default session-start would break those tests.

**Parallelism:** Phase 5 (docs/config edits) can run parallel with Phase 4 after Phase 3 — field names are spec-fixed; docs don't depend on wiring. Phase 6 depends on Phase 0 audit (not on Phase 4).

## Phase 0: Baselines (Design Phase Gate 1 + Phase 7 Gate)

**Why:** Capture pre-change state so Phase 7 can verify no regression. Also enumerates the specific tests needing audit per R-6 precedent.
**Why this order:** Zero external dependencies; must run before any edit.
**Complexity:** Low

### Task-level breakdown:
- Task 0.1: Capture `validate.sh` warning count → `agent_sandbox/082-baselines.txt` as `validate_warnings_before_082=N`.
- Task 0.2: Capture existing test counts → same file: `memory_tests_before_082=N` (plugins/pd/hooks/lib/semantic_memory), `hook_tests_before_082=M` (plugins/pd/hooks/tests).
- Task 0.3: Existing-test audit grep → `grep -rn 'run_reconciliation\|run_doctor_autofix\|build_memory_context\|session-start' plugins/pd/hooks/tests/` (result appended to baselines file as comment). Phase 6 reads this list.
- Task 0.4: Capture baseline `test-hooks.sh` pass count → same file: `test_hooks_before_082=101` (expected).

**Done when:** `agent_sandbox/082-baselines.txt` exists with all four values + audit grep output.

## Phase 1: maintenance.py module scaffold + helpers (C-1)

**Why:** All helpers for 082 live here. Must land before Phase 3 (decay_confidence) and before Phase 4a (session-start CLI invocation tests). TDD per helper: red test → green impl.
**Why this order:** Dependency root. Phase 3 imports from maintenance; Phase 4a imports through CLI subprocess.
**Complexity:** Medium (5 helpers + module globals + autouse fixture; each individually small)

### Task-level breakdown:
- Task 1.1: Create `plugins/pd/hooks/lib/semantic_memory/maintenance.py` skeleton with module docstring + the 4 module-globals per FR-8a (`_decay_warned_fields: set[str] = set()`, `_decay_config_warned: bool = False`, `_decay_log_warned: bool = False`, `_decay_error_warned: bool = False`) + `INFLUENCE_DEBUG_LOG_PATH: Path` constant (re-declared per TD-2).
- Task 1.2: Create `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` scaffold with autouse reset fixture per I-10 (monkeypatch.setattr on all 4 flags + `INFLUENCE_DEBUG_LOG_PATH → tmp_path / "influence-debug.log"`).
- Task 1.3: `_warn_and_default` tests [TDD: red] — AC-11/12/13 prefix regex `\[memory-decay\].*is not an int`, dedup via shared `warned` set.
- Task 1.4: `_warn_and_default` + `_resolve_int_config` implementation [green] — mirror refresh.py:127-183 verbatim except `[memory-decay]` prefix.
- Task 1.5: `_resolve_int_config` tests [TDD: red] — AC-5 parallel variants (bool reject, int accept, string coerce `"30"` → 30, string reject `"thirty"`, clamp `0 → 1`, clamp `500 → 365`, dedup).
- Task 1.6: `_emit_decay_diagnostic` tests [TDD: red] — AC-17 (shape per FR-7), AC-18 (silent when flag off), AC-19 (IsADirectoryError → one stderr warning, 2nd call silent, all demotions still applied).
- Task 1.7: `_emit_decay_diagnostic` implementation [green] — matches FR-7 JSON shape, mkdir inside try/except, `except OSError`, dedup via `_decay_log_warned`.
- Task 1.8: `_build_summary_line` tests [TDD: red] — 4 branches: zero-change normal (empty string), zero-change dry-run (empty string), demotions normal (`"Decay: demoted high->medium: X, medium->low: Y (dry-run: false)"`), demotions dry-run (`"Decay (dry-run): would demote high->medium: X, medium->low: Y"`). ASCII-only assertion (no Unicode).
- Task 1.9: `_build_summary_line` implementation [green] — per I-5 pseudocode.
- Task 1.10: `_select_candidates` tests [TDD: red] — seeded DB, verify partition buckets per I-2 rules (source=import → import_count, confidence=low → floor_count, never-recalled-in-grace → grace_count, staleness-meeting-threshold → high_ids / medium_ids). AC-3, AC-5, AC-7, AC-4 partition evidence.
- Task 1.11: `_select_candidates` implementation [green] — single SELECT + Python partition per I-2.

**Done when:** All `maintenance.py` helper tests green; module imports cleanly; autouse fixture resets all 4 flags.

## Phase 2: database.py additions (C-2)

**Why:** `batch_demote` + `_execute_chunk` + `busy_timeout_ms` kwarg are required by Phase 3's `decay_confidence`. Additive surface area only; existing methods untouched.
**Why this order:** Depends on nothing in 082 (pure additive); blocks Phase 3 (decay_confidence calls batch_demote).
**Complexity:** Low (45 LOC additions + focused tests)

### Task-level breakdown:
- Task 2.1: `test_database.py` additions — `TestBusyTimeoutKwarg` tests [TDD: red] — construct with default (asserts PRAGMA busy_timeout returns 15000); construct with `busy_timeout_ms=1000` (asserts PRAGMA busy_timeout returns 1000).
- Task 2.2: `MemoryDatabase.__init__` extension [green] — add optional `busy_timeout_ms: int = 15000` kwarg, store on `self._busy_timeout_ms`, modify `_set_pragmas` to read from `self._busy_timeout_ms` instead of hardcoded literal. Preserve ordering (`busy_timeout` FIRST per database.py:835 comment), `journal_mode`, `synchronous`, `cache_size` all unchanged.
- Task 2.3: `test_database.py` additions — `TestBatchDemote` tests [TDD: red] — (a) empty ids → returns 0, no SQL issued; (b) invalid new_confidence raises ValueError; (c) single chunk (<500 ids) → demotes all; (d) >500 ids → chunked, all demoted in single transaction; (e) `updated_at < now` guard blocks back-to-back calls with same now; (f) rowcount sum across chunks.
- Task 2.4: `MemoryDatabase.batch_demote` + `_execute_chunk` implementation [green] — per I-7. Chunk at 500 via `ids[i:i+500]`. ValueError for invalid confidence. `BEGIN IMMEDIATE` / try-commit / except-rollback-raise pattern parallel to `merge_duplicate`.
- Task 2.5: `test_database.py` additions — `TestExecuteChunkSeam` [TDD: red] — monkeypatch `_execute_chunk` to raise on 2nd call; invoke `batch_demote` with 2000 ids; assert rollback (all rows still at original confidence).
- Task 2.6: AC-20b-1 concurrent-writer test in `test_database.py` [TDD: red] → [green via reusing existing WAL + busy_timeout_ms=1000] — two-connection contention, A sleeps 100ms before COMMIT, decay on B succeeds.
- Task 2.7: AC-20b-2 concurrent-writer-timeout test in `test_database.py` [TDD: red] → [green via busy_timeout_ms=1000] — A sleeps 2.0s, decay on B returns with OperationalError properly.

**Done when:** All `test_database.py` new tests green; existing `test_database.py` tests pass unchanged; `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -v` passes.

## Phase 3: decay_confidence public entry + CLI (C-1 public surface)

**Why:** Main public function + CLI entry. Depends on all Phase 1 helpers + Phase 2 batch_demote.
**Why this order:** Last Python-layer work before session-start wiring.
**Complexity:** Medium (pseudocode in design I-1 + I-6)

### Task-level breakdown:
- Task 3.1: `decay_confidence` tests [TDD: red] — AC-1 (high → medium), AC-2 (medium → low), AC-3 (low stays at floor), AC-4 (one-tier-per-run), AC-5 (grace period), AC-6 (past grace decays), AC-7 (source=import excluded), AC-8 (disabled no-op), AC-9 (dry-run), AC-10 (intra-tick idempotency).
- Task 3.2: `decay_confidence` implementation [green] — per I-1 pseudocode. NFR-3 flag-check first; type-check `now`; resolve config via `_resolve_int_config`; semantic-coupling warning dedup; call `_select_candidates`; call `db.batch_demote` in non-dry-run branch; populate diag; emit diagnostic if flag on; return.
- Task 3.3: AC-10b-1 + AC-10b-2 cross-tick re-decay tests [TDD: red → green] — freshly-seeded medium with NOW_2 = NOW_1 + 31 days + existing helpers.
- Task 3.4: AC-14 semantic-coupling warning test [TDD: red → green via existing impl] — medium < high inverted, 1 warning, 2nd call silent.
- Task 3.5: AC-15 dedup test [TDD: red → green] — 3 consecutive malformed-config warnings, exactly 1 stderr line.
- Task 3.6: AC-20 DB error test [TDD: red → green via implementation] — monkeypatch `batch_demote` to raise OperationalError, assert `"error"` key + 1 stderr warning + demoted counts 0.
- Task 3.7: AC-23 promotion-after-decay integration test [TDD: red → green via existing merge_duplicate] — seed entry with source="retro", demote via decay, re-promote via merge_duplicate, assert confidence back to high.
- Task 3.8: AC-24 performance test [TDD: red → green] — seed 10k entries, invoke decay, assert `elapsed_ms < 5000`, print `[AC-24 local] elapsed_ms=... (target: 500ms)` per I-6 canonical mechanism.
- Task 3.9: AC-31 threshold-equality edge test [TDD: red → green via one-tier invariant].
- Task 3.10: AC-32 IN-list chunking test at decay level [TDD: red → green] — seed 2000 high stale entries, invoke decay, assert all 2000 demoted; plus partial-failure via `_execute_chunk` monkeypatch.
- Task 3.11: CLI entry `_main()` implementation per I-6 — argparse, project-root validation with `.resolve().is_dir()`, NFR-3 short-circuit before DB open, `MemoryDatabase(db_path)` no busy_timeout kwarg, finally close.
- Task 3.12: AC-29 CLI dry-run override test [TDD: red → green] — subprocess invocation with `--dry-run` + config `memory_decay_dry_run: false`, assert dry-run mode honored, DB unchanged.
- Task 3.13: AC-8 (disabled) + NFR-3 CLI-level short-circuit test — subprocess invocation with `memory_decay_enabled: false`, assert no DB file created on fresh system.

**Done when:** All decay_confidence + CLI tests pass; AC-1 through AC-15, AC-20, AC-23, AC-24, AC-29, AC-31, AC-32 covered.

## Phase 4: session-start.sh integration (C-3)

**Why:** The actual injection point. Depends on Phase 3 (CLI entry available).
**Why this order:** Parallel-eligible with Phase 5. Precedes Phase 6 (existing-test remediation) = FALSE. Phase 4a (tests) first, then Phase 6 (remediate existing tests), then Phase 4b (gate landing).
**Complexity:** Medium (bash function + main() reorder + display-prepend, no new logic)

### Task-level breakdown:
- Task 4.1 (Phase 4a — TDD red): Write AC-21 session-start integration test as a bash test in `plugins/pd/hooks/tests/test-memory-decay-session-start.sh` (NEW file) — seed DB with 2 decay candidates via `test_database.py` setup helper, set config `memory_decay_enabled: true`, run `bash plugins/pd/hooks/session-start.sh`, assert hook exits 0, JSON output well-formed via `python3 -c 'import sys, json; json.load(sys.stdin)'`, `additionalContext` contains ASCII substring `"Decay: demoted high->medium: X"` for X≥1.
- Task 4.2 (Phase 4a — TDD red): Write AC-22 tolerance-of-missing-module test — temporarily rename `maintenance.py → maintenance.py.bak`, run `bash plugins/pd/hooks/session-start.sh`, assert hook exits 0, JSON well-formed, `additionalContext` does NOT contain "Decay:" line; restore rename.
- Task 4.3 (Phase 6 — audit + remediate): Read `agent_sandbox/082-baselines.txt` audit output → list of impacted hook tests (expected count: 0-5). For each impacted test: update per the pattern used for 081 Phase 6 remediation (option (a) set `memory_decay_enabled: false` in test config; option (b) update test to ignore ordering of new decay summary section).
- Task 4.4 (Phase 6 verification): Run `bash plugins/pd/hooks/tests/test-hooks.sh` — must report ≥ `test_hooks_before_082` passing. Capture delta if any.
- Task 4.5 (Phase 4b — landing): Add `run_memory_decay()` bash function to `session-start.sh` per I-8 authoritative body (10s timeout via platform-aware detection, `$PLUGIN_ROOT/.venv/bin/python` fallback to `python3`, PYTHONPATH, `2>/dev/null || true`).
- Task 4.6 (Phase 4b — main reorder): Edit session-start.sh line 701 to insert `decay_summary=$(run_memory_decay)` BEFORE `memory_context=$(build_memory_context)`; keep `run_reconciliation` and `run_doctor_autofix` unchanged in their positions.
- Task 4.7 (Phase 4b — display-prepend): Add decay display-prepend block per I-8 between the existing doctor_summary block (733-739) and cron_schedule_context block (741-747).
- Task 4.8 (verification): Run Phase 4a tests (Tasks 4.1 + 4.2) — MUST go green.

**Done when:** AC-21 + AC-22 tests pass; all pre-existing hook tests still pass; session-start.sh runs end-to-end without errors; JSON output well-formed.

## Phase 5: Config templates + docs sync (C-4)

**Why:** User-visible surface. Field names are fixed by spec FR-3 so no code dependency.
**Why this order:** Parallel-eligible after Phase 3; completed before Phase 7 verification.
**Complexity:** Low (pure text edits)

### Task-level breakdown:
- Task 5.1: Append 5 fields to `plugins/pd/templates/config.local.md` with exact comments per spec FR-3 / design C-4 (`memory_decay_enabled: false`, `memory_decay_high_threshold_days: 30`, `memory_decay_medium_threshold_days: 60`, `memory_decay_grace_period_days: 14`, `memory_decay_dry_run: false`).
- Task 5.2: Append same 5 fields to `.claude/pd.local.md` (repo config). `memory_decay_enabled: false` default (opt-in per spec). No debug-collection value flip.
- Task 5.3: Append 5 bullet lines to `README_FOR_DEV.md` memory config table (after `memory_refresh_limit` from 081).
- Task 5.4: AC-25 + AC-26 verification greps — `grep -c "^memory_decay_" plugins/pd/templates/config.local.md` returns 5, same in `.claude/pd.local.md`, `grep -c "memory_decay_" README_FOR_DEV.md` returns ≥5.

**Done when:** All three files contain the 5 new fields; verification greps pass.

## Phase 6: Existing-test audit + remediation (R-6 mitigation)

**Why:** Per design Phase Gate 1 + 081 retrospective learning, existing session-start hook tests may break from the main() reorder or the new output section. Phase 0 audit enumerated them; this phase updates them.
**Why this order:** Must follow Phase 4a (tests exist so shape is observable) and precede Phase 4b (gate landing).
**Complexity:** Low (mechanical per-test updates — expected count: 0-5; may be zero since decay defaults to disabled).

### Task-level breakdown:
- Task 6.1: Narrow-grep for tests that ASSERT ON session-start output ordering (not just mention session-start). Write filtered list to `agent_sandbox/082-impacted-tests.txt`.
- Task 6.2: For each impacted test, apply remediation per audit output.
- Task 6.3: Re-run `bash plugins/pd/hooks/tests/test-hooks.sh`; pass count ≥ `test_hooks_before_082`.

**Done when:** All previously-passing tests still pass; no test was skipped or deleted. Default-disabled config means most test environments will not trigger the decay path at all. See tasks.md Phase 6 section for detailed task breakdown (Tasks 6.1, 6.2, 6.3).

## Phase 7: Final verification

**Why:** Ship gate. Verifies no regression, warning count ≤ baseline, full suite green, retro-capture evidence present.
**Why this order:** Last.
**Complexity:** Low (verification-only)

### Task-level breakdown:
- Task 7.1: Run `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v`. Must be all green; counts ≥ `memory_tests_before_082` + new tests from Phase 1-3.
- Task 7.2: Run `bash plugins/pd/hooks/tests/test-hooks.sh`. Must be ≥ `test_hooks_before_082` (101 or whatever baseline captured).
- Task 7.3: Run `./validate.sh`. Must be 0 errors; warning count ≤ `validate_warnings_before_082`.
- Task 7.4: Capture `EXPLAIN QUERY PLAN` for the I-2 SELECT against a 10k-row test DB; record in feature retro.md "Performance" section per R-6 implementation-evidence requirement.
- Task 7.5: Record actual `elapsed_ms` from AC-24 CI run in retro.md alongside hardware context per spec AC-24 canonical mechanism.
- Task 7.6: Delete `agent_sandbox/082-baselines.txt` (temp file, not committed).

**Done when:** All three gates green; retro.md has Performance section populated; temp baseline file removed.

## Risks (from design)

- **R-1 Unexpected demotions after operator enable** — mitigated by `memory_decay_dry_run: true` + HP-2 measurement procedure. Operator responsibility.
- **R-2 BEGIN IMMEDIATE contention on session-start** — mitigated by 15s default busy_timeout; AC-20b-1/2 cover both branches.
- **R-3 Chunked UPDATE new to codebase** — mitigated by explicit 500 chunk size + AC-32 >500 test + `_execute_chunk` partial-failure seam.
- **R-4 INFLUENCE_DEBUG_LOG_PATH triplication** — documented in TD-2 + TD-4 note in 081's refresh.py; future 4th-caller triggers extract to shared module.
- **R-5 Inverted threshold config** — mitigated by AC-14 semantic-coupling warning.
- **R-6 Performance regression** — CI-enforced AC-24 ≤5000ms; 500ms local target in retro; EXPLAIN QUERY PLAN captured per Task 7.4.

## Deliverables Summary

**New files:**
- `plugins/pd/hooks/lib/semantic_memory/maintenance.py` — new module (~200 LOC production + CLI).
- `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` — new test file (~450 LOC).
- `agent_sandbox/082-baselines.txt` — temp file, deleted in Task 7.5 on success.
- `agent_sandbox/082-impacted-tests.txt` — temp file (Phase 6 audit output), deleted in Task 7.5.
- `agent_sandbox/082-eqp.txt` — EQP + perf evidence, preserved for retrospective.

**Edited files:**
- `plugins/pd/hooks/lib/semantic_memory/database.py` — `+batch_demote` (~30 LOC), `+_execute_chunk` (~10 LOC), `+busy_timeout_ms` kwarg on `__init__` + `+get_busy_timeout_ms()` public accessor (~5 LOC change to `_set_pragmas` + accessor).
- `plugins/pd/hooks/lib/semantic_memory/test_database.py` — new test classes `TestBusyTimeoutKwarg` + `TestBatchDemote` + `TestExecuteChunkSeam` + concurrent-writer tests.
- `plugins/pd/hooks/session-start.sh` — `+run_memory_decay` function (~25 LOC), reorder main() (1-line insert before build_memory_context), display-prepend block (~6 LOC).
- `plugins/pd/hooks/tests/test-hooks.sh` — `+test_memory_decay_session_start` inline function (AC-21) + `+test_memory_decay_missing_module` inline function (AC-22) + 2 new call sites in main(). Matches existing inline-test pattern.
- `plugins/pd/templates/config.local.md` — +5 field lines.
- `.claude/pd.local.md` — +5 field lines.
- `README_FOR_DEV.md` — +5 memory-config table rows.

**Test delta:**
- New unit tests in `test_maintenance.py` covering AC-1..AC-19, AC-23..AC-32 (and variants).
- New tests in `test_database.py` covering AC-20, AC-20b-1, AC-20b-2.
- New bash test for AC-21 + AC-22.
- Existing tests unchanged (Phase 6 expected zero-remediation — default-disabled config means no test environment triggers the decay code path).
