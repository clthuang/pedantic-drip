# Tasks: Confidence Decay Job (Feature 082)

Each task is 5-15 minutes of focused work. Parallel groups marked with `[PARALLEL: group-X]`. Dependencies marked with `requires:`.

## Serialization rules (critical)

- **Within Phase 1:** all tasks share `test_maintenance.py` and `maintenance.py` → MUST be serialized. No parallel worktree dispatch.
- **Within Phase 2:** all tasks share `test_database.py` and `database.py` → MUST be serialized. No parallel worktree dispatch.
- **Within Phase 3:** all tasks share `test_maintenance.py` and `maintenance.py` → MUST be serialized.
- **Within Phase 4:** bash-file edits serialized; Phase 4a tests + Phase 6 remediate + Phase 4b wiring MUST interleave in the order shown.
- **Parallelism permitted ONLY** between Phase 5 tasks (pure text file edits to different files) and across Phase 5 ↔ later tasks (Phase 5 has no code dependency after Phase 3 completes).

## TDD red/green convention

- `[TDD red]` = write failing test; do NOT land any production code.
- `[TDD green]` = land minimal production code to make the red test pass; no new test logic.
- `[TDD red → green]` = single step where the red test and a trivial implementation land together because the impl depends only on previously-landed code (no new logic in current step). Used for acceptance tests that exercise already-implemented behavior.

---

## Phase 0: Baselines

- [ ] **0.1** Capture `validate.sh` warning count to baselines file.
  - Action: `./validate.sh 2>&1 | grep -c 'WARNING' > agent_sandbox/082-baselines.txt.warn.tmp`; write `validate_warnings_before_082=$(cat ...)` format to `agent_sandbox/082-baselines.txt`.
  - Done: baselines file exists with `validate_warnings_before_082=N`.
  - Size: 5 min.

- [ ] **0.2** Capture pytest counts for semantic_memory and hook tests from LIVE runs (no hardcoded values).
  - Action 1: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ --collect-only -q 2>&1 | tail -3` → parse the collected count and append `memory_tests_before_082=N` line.
  - Action 2: `bash plugins/pd/hooks/tests/test-hooks.sh 2>&1 | grep -E 'TESTS_PASSED|passed' | tail -1` → parse the reported pass count and append `test_hooks_before_082=M` line. DO NOT hardcode; capture whatever the current live count is. (081 shipped with ~101; exact count may have drifted with other features.)
  - Done: baselines file has both counts captured from live runs.
  - Size: 10 min. `[PARALLEL: phase-0]` `requires: 0.1`

- [ ] **0.3** Grep for session-start ordering assertions in hook tests.
  - Action: `grep -rn 'run_reconciliation\|run_doctor_autofix\|build_memory_context\|additionalContext' plugins/pd/hooks/tests/ >> agent_sandbox/082-baselines.txt`. Head the file with `# Phase 0 audit — tests that may be impacted by session-start main() reorder`.
  - Done: baselines file has grep output appended.
  - Size: 5 min. `[PARALLEL: phase-0]` `requires: 0.1`

---

## Phase 1: maintenance.py module + helpers (TDD)

- [ ] **1.1** Create `plugins/pd/hooks/lib/semantic_memory/maintenance.py` skeleton with stub functions.
  - Contents: module docstring, imports (`sys`, `json`, `argparse`, `sqlite3`, `time`, `datetime`, `timedelta`, `timezone`, `Path`), 4 module-globals (`_decay_warned_fields: set[str] = set()`, `_decay_config_warned: bool = False`, `_decay_log_warned: bool = False`, `_decay_error_warned: bool = False`), `INFLUENCE_DEBUG_LOG_PATH: Path = Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"` constant with TD-2 duplication comment. **Stub bodies** for each function defined in Phases 1-3: `_warn_and_default`, `_resolve_int_config`, `_emit_decay_diagnostic`, `_build_summary_line`, `_select_candidates`, `decay_confidence`, `_main` — each raises `NotImplementedError`. Rationale: enables test_maintenance.py to import by name without collection failure during Phase 1's red-test steps.
  - Done: file exists; `python -c "from semantic_memory import maintenance; maintenance._warn_and_default"` works without AttributeError.
  - Size: 15 min. `requires: 0.3`

- [ ] **1.2** Create `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` skeleton with autouse fixture per design I-10.
  - Contents: imports pytest + maintenance module, autouse fixture `reset_decay_state(monkeypatch, tmp_path)` that `monkeypatch.setattr(maintenance, ...)` for all 4 flags + INFLUENCE_DEBUG_LOG_PATH → tmp_path.
  - Done: file exists, `pytest plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` runs (zero tests, zero failures).
  - Size: 10 min. `requires: 1.1`

- [ ] **1.3** Write `TestWarnAndDefault` tests [TDD red].
  - Cases: (a) invalid value + unseen key → 1 stderr line matching `\[memory-decay\].*is not an int` regex + key added to warned set + returns default; (b) same key second call → NO new stderr line (dedup) + still returns default.
  - Done: tests written, fail (helper not implemented yet).
  - Size: 10 min. `requires: 1.2`

- [ ] **1.4** Implement `_warn_and_default(key, raw, default, warned) -> int` [TDD green].
  - Copy refresh.py:127-140 body; replace `[refresh]` with `[memory-decay]`.
  - Done: Task 1.3 tests pass.
  - Size: 5 min. `requires: 1.3`

- [ ] **1.5** Write `TestResolveIntConfig` tests [TDD red].
  - Cases: (a) int accepted pass-through; (b) bool rejected → default + warning; (c) numeric string `"30"` → 30 via `int(raw)`; (d) non-numeric string `"thirty"` → default + warning; (e) None → default + warning; (f) float 5.7 → default + warning; (g) clamp `0 → 1` with `clamp=(1, 365)`; (h) clamp `500 → 365`; (i) `clamp=None` branch returns raw value unclamped; (j) dedup: 3 consecutive bad values for same key → 1 warning total.
  - Done: ~10 red tests.
  - Size: 15 min. `requires: 1.4`

- [ ] **1.6** Implement `_resolve_int_config(config, key, default, *, clamp=None, warned) -> int` [TDD green].
  - Copy refresh.py:143-183 body verbatim; stderr prefix handled by `_warn_and_default`.
  - Done: Task 1.5 tests pass.
  - Size: 5 min. `requires: 1.5`

- [ ] **1.7** Write `TestEmitDecayDiagnostic` tests [TDD red].
  - Cases: (a) normal write → file contains exactly 1 JSON line matching `"event":\s*"memory_decay"` with all required fields per FR-7; (b) disabled flag → file does NOT exist or zero lines; (c) mkdir failure / IsADirectoryError → 1 stderr warning + `_decay_log_warned = True`, 2nd call silent; (d) diagnostic dict fields verified against FR-7 schema.
  - Done: ~4 red tests.
  - Size: 15 min. `requires: 1.6`

- [ ] **1.8** Implement `_emit_decay_diagnostic(diag)` [TDD green].
  - Per I-4: mkdir+open inside try/except OSError, json.dumps with FR-7 fields, one-shot dedup via `_decay_log_warned`.
  - Done: Task 1.7 tests pass.
  - Size: 10 min. `requires: 1.7`

- [ ] **1.9** Write `TestBuildSummaryLine` tests [TDD red].
  - 4 branches per I-5: zero-change normal (`""`), zero-change dry-run (`""`), demotions normal (`"Decay: demoted high->medium: 1, medium->low: 2 (dry-run: false)"`), demotions dry-run (`"Decay (dry-run): would demote high->medium: 1, medium->low: 2"`). Plus: assert no Unicode chars `→` anywhere in output.
  - Done: 5 red tests.
  - Size: 10 min. `requires: 1.8`

- [ ] **1.10** Implement `_build_summary_line(diag) -> str` [TDD green].
  - Per I-5 pseudocode.
  - Done: Task 1.9 tests pass.
  - Size: 5 min. `requires: 1.9`

- [ ] **1.11** Write `TestSelectCandidates` tests [TDD red].
  - Seed DB with 6 entries (one per bucket): source=import + stale, confidence=low + stale, never-recalled-in-grace, never-recalled-past-grace + medium, confidence=high + stale, confidence=medium + stale.
  - Assert partition: `import_count=1, floor_count=1, grace_count=1, medium_ids=[2 entries — grace-past + medium-stale], high_ids=[1 entry — high-stale]`.
  - Done: 1 comprehensive test.
  - Size: 15 min. `requires: 1.10`

- [ ] **1.12** Implement `_select_candidates(db, high_cutoff, med_cutoff, grace_cutoff, now_iso)` [TDD green].
  - Per I-2: single SELECT with WHERE `(last_recalled_at IS NOT NULL AND last_recalled_at < ?) OR (last_recalled_at IS NULL AND created_at < ?)`. Python-side partition per bucket rules.
  - Done: Task 1.11 test passes.
  - Size: 15 min. `requires: 1.11`

---

## Phase 2: database.py additions (TDD)

- [ ] **2.1** Write `TestBusyTimeoutKwarg` tests in `test_database.py` [TDD red].
  - **Public accessor contract (avoids `db._conn` anti-pattern):** Tasks 2.1/2.2 introduce a trivial public accessor `MemoryDatabase.get_busy_timeout_ms(self) -> int` that returns `self._busy_timeout_ms`. Tests assert on this public accessor, NOT on `db._conn.execute('PRAGMA busy_timeout')`. This respects engineering memory's "never access `db._conn` directly" anti-pattern while verifying the kwarg was applied.
  - Cases: (a) default `MemoryDatabase(':memory:').get_busy_timeout_ms() == 15000`; (b) override `MemoryDatabase(':memory:', busy_timeout_ms=1000).get_busy_timeout_ms() == 1000`.
  - Done: 2 red tests (fail because `get_busy_timeout_ms` not yet on MemoryDatabase).
  - Size: 10 min. `requires: 1.1`

- [ ] **2.2** Extend `MemoryDatabase.__init__`, add public accessor, and `_set_pragmas` [TDD green].
  - Add `*, busy_timeout_ms: int = 15000` kwarg to `__init__`; store `self._busy_timeout_ms = int(busy_timeout_ms)`; modify `_set_pragmas` to read from `self._busy_timeout_ms` instead of hardcoded literal. Preserve PRAGMA ordering, `row_factory`, `_detect_fts5`, `_migrate` unchanged. Also add public accessor method `def get_busy_timeout_ms(self) -> int: return self._busy_timeout_ms`.
  - Done: Task 2.1 tests pass via the public accessor; existing test_database.py tests still pass.
  - Size: 10 min. `requires: 2.1`

- [ ] **2.3** Write `TestBatchDemote` tests [TDD red].
  - Cases: (a) empty ids → returns 0, no SQL issued; (b) ValueError on invalid new_confidence (e.g., `'extreme'`); (c) single chunk (<500 ids) → all demoted; (d) >500 ids (pass 600 ids) → all 600 demoted; (e) intra-tick `updated_at < now` guard → back-to-back with same now, 2nd call demotes 0; (f) rowcount sum across chunks.
  - Done: 6 red tests.
  - Size: 15 min. `requires: 2.2`

- [ ] **2.4** Implement `MemoryDatabase.batch_demote` + `MemoryDatabase._execute_chunk` [TDD green].
  - Per I-7: BEGIN IMMEDIATE, loop `ids[i:i+500]`, call `_execute_chunk` for each, commit. `_execute_chunk` issues one UPDATE with IN-list + `updated_at < ?` guard, returns `cursor.rowcount`. Empty-ids early-return 0. ValueError for `new_confidence not in ('medium', 'low')`.
  - Done: Task 2.3 tests pass.
  - Size: 15 min. `requires: 2.3`

- [ ] **2.5** Write `TestExecuteChunkSeam` test [TDD red → green].
  - Monkeypatch `MemoryDatabase._execute_chunk` with side_effect counter raising `sqlite3.OperationalError` on 2nd call. Invoke `batch_demote` with 2000 ids. Assert: all 2000 still at original confidence (transaction rolled back), exception propagates from batch_demote.
  - Because Task 2.4 already implemented `_execute_chunk` as the chunking seam, this test passes as soon as it is written (no additional impl work required). [red → green] semantics apply — the red is momentary (until test runs against the existing impl) and the green is "the existing impl makes this pass."
  - Done: 1 test passes against the Task 2.4 implementation.
  - Size: 10 min. `requires: 2.4`

- [ ] **2.6** Write AC-20b-1 concurrent-writer-success test [TDD red → green via busy_timeout_ms=1000].
  - Two MemoryDatabase connections with `busy_timeout_ms=1000`. A-thread: `BEGIN IMMEDIATE; INSERT (dummy row); time.sleep(0.1); COMMIT`. B invokes `batch_demote` directly (not decay_confidence — focus on DB seam). Assert: decay succeeds, A's INSERT visible post-join.
  - Done: 1 test passes.
  - Size: 15 min. `requires: 2.4`

- [ ] **2.7** Write AC-20b-2 concurrent-writer-timeout test [TDD red → green via busy_timeout_ms=1000].
  - Same setup with `time.sleep(2.0)` before COMMIT. A.join() THEN verification SELECTs. B's batch_demote catches `sqlite3.OperationalError`. Assert per I-1 error-handling: no partial UPDATE visible on either connection.
  - Done: 1 test passes.
  - Size: 15 min. `requires: 2.6`

---

## Phase 3: decay_confidence public function + CLI (TDD)

Phase 3 is split into sub-stages to keep the sequential chain under the 15-task-per-stage cap:
- **Phase 3a (Tasks 3.1-3.7):** TDD red→green core for `decay_confidence` implementation + basic tier tests.
- **Phase 3b (Tasks 3.8-3.24):** Acceptance-test coverage sweep (mostly [red → green via existing impl]).

The serialization rule (no parallel dispatch) applies to ALL Phase 3 tasks (3a + 3b share test_maintenance.py). Phase 3b starts after Phase 3a completes.

### Phase 3a: Core implementation

- [ ] **3.1** Write AC-1, AC-2, AC-3 tests in `test_maintenance.py` (basic tier transitions) [TDD red].
  - AC-1: seed 1 high stale entry, invoke decay with thresholds, assert demoted to medium + counters correct.
  - AC-2: same with medium → low.
  - AC-3: low + stale → no-op, `skipped_floor=1`, `updated_at` unchanged.
  - Done: 3 red tests.
  - Size: 15 min. `requires: 1.12, 2.4`

- [ ] **3.2** Write AC-4 one-tier-per-run test [TDD red].
  - Seed 1 high entry with last_recalled_at 90 days old (meets both thresholds). Assert: decays to medium only (not low), `demoted_high_to_medium=1, demoted_medium_to_low=0`.
  - Done: 1 red test.
  - Size: 10 min. `requires: 3.1`

- [ ] **3.3** Write AC-5, AC-6 grace-period tests [TDD red].
  - AC-5: never-recalled medium + created 10 days ago + grace=14 → skipped_grace=1.
  - AC-6: never-recalled medium + created 80 days ago + grace=14, med=60 → demoted to low.
  - Done: 2 red tests.
  - Size: 10 min. `requires: 3.2`

- [ ] **3.4** Write AC-7 source=import exclusion test [TDD red].
  - Seed high + source=import + stale → confidence still high + `skipped_import=1`.
  - Done: 1 red test.
  - Size: 5 min. `requires: 3.3`

- [ ] **3.5** Write AC-8 disabled no-op test [TDD red].
  - `memory_decay_enabled: false` config, seed a would-be candidate, invoke → all counters 0, DB state unchanged.
  - Done: 1 red test.
  - Size: 5 min. `requires: 3.4`

- [ ] **3.6** Write AC-9 dry-run test [TDD red].
  - `memory_decay_dry_run: true` config, seed a candidate, invoke → `demoted_high_to_medium=1, dry_run=True`, DB state unchanged (confidence + updated_at).
  - Done: 1 red test.
  - Size: 10 min. `requires: 3.5`

- [ ] **3.7** Implement `decay_confidence` [TDD green].
  - Per I-1 pseudocode: NFR-3 flag check first; type-check `now`; resolve 3 config ints via `_resolve_int_config`; semantic-coupling warning dedup; compute cutoffs; call `_select_candidates`; non-dry-run: call `db.batch_demote` for each tier; dry-run: populate counts without UPDATE; elapsed_ms; emit diagnostic if debug flag; return.
  - Done: Tasks 3.1-3.6 tests pass.
  - Size: 15 min. `requires: 3.6`

### Phase 3b: Acceptance-test coverage sweep

Starts after Phase 3a (Tasks 3.1-3.7) completes. All tests below exercise already-implemented behavior via `[red → green via existing impl]` — red tests land with minimal or no new production code.

- [ ] **3.8** Write AC-10 intra-tick idempotency test [TDD red → green via existing guard].
  - Seed 3 candidates, invoke twice with same `now=NOW`. 1st call: expected demotions. 2nd call: `demoted_* == 0`, `skipped_floor==1` for already-demoted-to-low.
  - Done: 1 test passes.
  - Size: 10 min. `requires: 3.7`

- [ ] **3.9** Write AC-10b-1 cross-tick (freshly-seeded medium) test [TDD red → green].
  - Invoke at NOW_1 (no-op); advance to NOW_2 = NOW_1 + 31 days; seed NEW medium + last_recalled_at = NOW_2 - 61 days. Invoke. Assert demoted to low.
  - Done: 1 test.
  - Size: 10 min. `requires: 3.8`

- [ ] **3.10** Write AC-10b-2 cross-tick (demoted-high-now-medium) test [TDD red → green].
  - Seed 1 high + last_recalled_at = NOW_1 - 30 days. Invoke at NOW_1 → demoted to medium. Advance to NOW_2 = NOW_1 + 31 days (last_recalled_at now ~61 days old, > 60 med threshold). Invoke. Assert demoted to low. Also assert `last_recalled_at` unchanged (decay invariant).
  - Done: 1 test.
  - Size: 15 min. `requires: 3.9`

- [ ] **3.11** Write AC-11, AC-12, AC-13 config coercion tests [TDD red → green via existing `_resolve_int_config`].
  - AC-11: `high_threshold_days=0 → 1 + warning regex match`; `=500 → 365 + warning`.
  - AC-12: `high_threshold_days=True` → default 30 + warning; `enabled=True` → True (bool is correct type here).
  - AC-13: `"thirty"` → default 30 + warning.
  - Done: 3-5 tests pass.
  - Size: 10 min. `requires: 3.10`

- [ ] **3.12** Write AC-14 semantic-coupling warning test [TDD red → green].
  - Config `high=60, medium=30` (inverted). Invoke twice. Assert: 1st call emits 1 stderr warning matching `\[memory-decay\].*medium_threshold_days.*<.*high_threshold_days`. 2nd call: zero new warnings (dedup via `_decay_config_warned`).
  - Done: 1 test passes.
  - Size: 10 min. `requires: 3.11`

- [ ] **3.13** Write AC-15 dedup test [TDD red → green via `_decay_warned_fields` reuse].
  - 3 consecutive invocations with same malformed field (e.g., `high_threshold_days="thirty"`). Assert stderr contains exactly 1 warning line cumulatively.
  - Done: 1 test passes.
  - Size: 10 min. `requires: 3.12`

- [ ] **3.14** Write AC-16 idempotency of source=import skip test [TDD red → green].
  - Seed 1 import + stale; invoke twice; assert `skipped_import==1` on both calls; DB state unchanged.
  - Done: 1 test passes.
  - Size: 5 min. `requires: 3.13`

- [ ] **3.15** Write AC-17 + AC-18 diagnostic emission tests [TDD red → green].
  - AC-17: `memory_influence_debug: true` + invoke → file contains exactly 1 `"event":"memory_decay"` line with all FR-7 fields.
  - AC-18: flag off → file does not exist OR 0 matching lines.
  - Done: 2 tests pass.
  - Size: 10 min. `requires: 3.14`

- [ ] **3.16** Write AC-19 log-write failure test [TDD red → green].
  - Monkeypatch `INFLUENCE_DEBUG_LOG_PATH` to a directory. Enable debug. Invoke twice. Assert 1 stderr warning total, demotions applied normally in both calls.
  - Done: 1 test passes.
  - Size: 10 min. `requires: 3.15`

- [ ] **3.17** Write AC-20 DB error test [TDD red → green].
  - Monkeypatch `MemoryDatabase.batch_demote` to raise `sqlite3.OperationalError('mock')` (MUST be `sqlite3.OperationalError` — a subclass of `sqlite3.Error` — because the design I-1 `except sqlite3.Error` clause catches sqlite3 subclasses but NOT generic `Exception`/`ValueError`. Using `Exception()` in the mock would silently escape the except and crash decay_confidence, falsely passing the test by raising). Invoke decay. Assert: no exception propagates, return dict has `"error"` key containing 'mock', 1 stderr warning matching `\[memory-decay\]` (dedup via `_decay_error_warned`), `demoted_*` counts 0.
  - Done: 1 test passes.
  - Size: 10 min. `requires: 3.16`

- [ ] **3.18** Write AC-23 promotion-after-decay integration test [TDD red → green].
  - Seed `source="retro"` entry at high. Invoke decay (demoted to medium). Invoke `merge_duplicate` with enough observations to trip `medium → high` promotion path. Assert confidence back to high.
  - Done: 1 test passes.
  - Size: 15 min. `requires: 3.17`

- [ ] **3.19** Write AC-24 performance test [TDD red → green].
  - Seed 10,000 entries (mix of confidence, source, age). **Seeding contract:** use a single raw SQL `INSERT ... VALUES (...)` via `executemany` with one commit (NOT per-row `upsert_entry` loop) to keep seeding under ~2s. Invoke decay. Assert `elapsed_ms < 5000`. Print canonical line `print(f"[AC-24 local] elapsed_ms={result['elapsed_ms']} (target: 500ms)")` for `pytest -s` capture.
  - Done: 1 test passes; seed+decay+assert under ~3s total.
  - Size: 15 min. `requires: 3.18`

- [ ] **3.20** Write AC-31 threshold-equality edge test [TDD red → green].
  - `memory_decay_high_threshold_days == memory_decay_medium_threshold_days == 30`. Seed 1 high + stale 30 days. Assert demoted to medium only (`demoted_high_to_medium=1, demoted_medium_to_low=0`).
  - Done: 1 test passes.
  - Size: 10 min. `requires: 3.19`

- [ ] **3.21** Write AC-32 IN-list chunking happy-path test (decay-level) [TDD red → green].
  - Seed 2000 high stale (via batched `executemany` — not per-row — for <2s seeding time). Invoke decay. Assert all 2000 demoted to medium. **Scope:** decay-level happy path ONLY. The partial-failure-with-_execute_chunk-monkeypatch is the authoritative test for Task 2.5 at the DB layer; Task 3.21 does NOT duplicate that seam. Rationale: spec AC-32 calls for ONE authoritative seam test; DB-layer ownership per NFR-5 scope exception 1.
  - Done: 1 test passes.
  - Size: 15 min. `requires: 3.20, 2.5`

- [ ] **3.22** Write AC-30 decay → refresh end-to-end integration test [TDD red → green via existing refresh_memory_digest].
  - Seed 1 medium entry with `last_recalled_at = now - 61 days` (stale past `memory_decay_medium_threshold_days: 60`). Seed 5 fresh medium/high entries with matching keywords to a test feature slug. Invoke `decay_confidence(db, config, now=NOW)` — stale entry demoted to low. Invoke 081's `refresh_memory_digest(db, provider, query, limit, *, config=..., feature_type_id=..., completed_phase=...)` per the signature at `plugins/pd/hooks/lib/semantic_memory/refresh.py:273-282`. Use `_FixedSimilarityProvider` (either imported from `test_memory_server.py` or defined inline in test_maintenance.py) so query matching is deterministic. Assert: (a) stale entry confidence is 'low'; (b) stale entry's `name` is NOT in `digest["entries"]`; (c) all 5 fresh entries' names ARE in `digest["entries"]`.
  - Done: 1 test passes.
  - Size: 15 min. `requires: 3.21`

### Phase 3c: CLI implementation and tests

Starts after Phase 3b completes (Task 3.22). Shares test_maintenance.py with 3a/3b; serialization rule applies.

- [ ] **3.23** Implement CLI `_main()` in `maintenance.py` [TDD green-first for structure].
  - Per I-6: argparse for `--decay`, `--project-root`, `--dry-run`. Resolve project-root via `Path(args.project_root).resolve() if args.project_root else Path.cwd().resolve()`. Validate `is_dir()`. Read config via `read_config(str(project_root))`. NFR-3 enabled-check short-circuits BEFORE `MemoryDatabase(db_path)`. Finally close. `if __name__ == "__main__": _main()`.
  - Done: module imports cleanly, `python -m semantic_memory.maintenance` prints usage.
  - Size: 15 min. `requires: 3.22`

- [ ] **3.24** Write AC-29 CLI dry-run override test [TDD red → green].
  - Subprocess invocation: `python -m semantic_memory.maintenance --decay --dry-run --project-root <tmp>` with config `memory_decay_dry_run: false`. Assert CLI reports dry-run (summary contains "(dry-run)"), DB unchanged.
  - Done: 1 test passes.
  - Size: 15 min. `requires: 3.23`

- [ ] **3.25** Write NFR-3 process-level zero-overhead test [TDD red → green].
  - Subprocess invocation on fresh dir with isolated HOME. **Isolation contract:** `env={"HOME": str(tmp_path), "PYTHONPATH": "plugins/pd/hooks/lib"}` passed to `subprocess.run`. Config `memory_decay_enabled: false` in `tmp_path / ".claude/pd.local.md"`. Invoke `python -m semantic_memory.maintenance --decay --project-root <tmp>`. Assert `(tmp_path / ".claude/pd/memory/memory.db").exists() == False` — the CLI short-circuit before DB open prevented file creation. Isolating HOME via env override is mandatory so the test does NOT assert on the user's real `~/.claude/pd/memory/memory.db`.
  - Done: 1 test passes.
  - Size: 15 min. `requires: 3.24`

---

## Phase 4: session-start.sh integration

### Phase 4a: Write integration tests FIRST (TDD red)

**Integration pattern:** `test-hooks.sh` is a monolithic runner with ~119 inline `test_*` bash functions called from its own `main()` block. External `test-*.sh` files in the same directory are NOT sourced by test-hooks.sh. Tasks 4.1 + 4.2 therefore add INLINE test functions directly to `test-hooks.sh`, matching the precedent established by existing tests like `test_session_start_json`.

- [ ] **4.1** Add inline `test_memory_decay_session_start` function to `plugins/pd/hooks/tests/test-hooks.sh` for AC-21 [TDD red].
  - Add a new bash function following the existing `test_session_start_json`-style pattern. Contents:
    - `tmp_home=$(mktemp -d)` + `trap 'rm -rf "$tmp_home"' RETURN` for cleanup.
    - Create `$tmp_home/.claude/pd.local.md` with `memory_decay_enabled: true` and the 4 threshold fields.
    - Seed memory.db: `HOME="$tmp_home" PYTHONPATH="$PLUGIN_ROOT/hooks/lib" "$PLUGIN_ROOT/.venv/bin/python" -c 'from semantic_memory.database import MemoryDatabase; db = MemoryDatabase(str(Path.home() / ".claude/pd/memory/memory.db")); ... seed 2 stale high entries ...'`.
    - Invoke: `HOME="$tmp_home" bash "$PLUGIN_ROOT/hooks/session-start.sh" < /dev/null`.
    - Assert: `jq -e '.hookSpecificOutput.additionalContext | contains("Decay: demoted high->medium")' <<< "$output"`.
    - Increment `TESTS_RUN` + `TESTS_PASSED` on success; call `log_fail` on failure per existing conventions.
  - Add call to `test_memory_decay_session_start` inside `test-hooks.sh`'s `main()` block alongside the existing test calls.
  - Done: 1 new inline test function + 1 call site added; test currently fails because run_memory_decay not yet implemented.
  - Size: 20 min. `requires: 3.23`

- [ ] **4.2** Add inline `test_memory_decay_missing_module` function for AC-22 [TDD red].
  - Similar structure to Task 4.1 but simulates missing module.
  - **Cleanup contract (critical):** install `trap 'mv "$PLUGIN_ROOT/hooks/lib/semantic_memory/maintenance.py.bak" "$PLUGIN_ROOT/hooks/lib/semantic_memory/maintenance.py" 2>/dev/null || true; rm -rf "$tmp_home"' RETURN` BEFORE the rename so restoration happens even on assertion failure.
  - Rename `maintenance.py → maintenance.py.bak`.
  - Invoke session-start.sh with isolated HOME.
  - Assert: exit 0, JSON well-formed, `additionalContext` does NOT contain "Decay:" substring.
  - Add call to `test_memory_decay_missing_module` in `main()`.
  - Done: 1 new inline test function + 1 call site; maintenance.py.bak rename restored on all exit paths.
  - Size: 15 min. `requires: 4.1`

### Phase 6: Existing-test audit + remediation (interleaves between Phase 4a and Phase 4b)

- [ ] **6.1** Narrow-grep for tests that ASSERT ON session-start output ordering or section presence.
  - Action: `grep -rn 'additionalContext\|full_context\|recon_summary\|doctor_summary\|memory_context' plugins/pd/hooks/tests/ > agent_sandbox/082-impacted-tests.txt`. Manually review each match — keep only those that do ORDERING assertions (not mere references). The Phase 0 Task 0.3 grep was overly broad; this narrower grep establishes the true impacted set.
  - Done: `082-impacted-tests.txt` contains 0-N filtered matches. Expected count: 0-5 (most hook tests reference these vars via grep-free path).
  - Size: 10 min. `requires: 0.3, 4.2`

- [ ] **6.2** For each impacted test identified in Task 6.1, apply remediation.
  - **Size-split gate (bounded inline):** If Task 6.1 identified 0 hits → Task 6.2 is a 2-min no-op (document `"Phase 6 audit found 0 impacted tests"` in baselines file and move on). If Task 6.1 identified 1-5 hits → apply remediation inline within this single task (15-75 min total; capped at 5 tests because the Phase 0 audit's expected range is 0-5 per R-6 estimate). If the count unexpectedly exceeds 10, capture the full list in `082-impacted-tests.txt` and emit a stderr warning `"Phase 6 remediation list exceeds expected range (N > 10)"` for operator review — but continue remediating sequentially within this task (do NOT halt; bounded inline remediation is the authoritative path).
  - Remediation pattern per test: (a) if test asserts exact section ordering in additionalContext → update to be robust to new decay section (test existence, not order, OR add decay section to expected); (b) if test writes config for session-start → no change needed (default `memory_decay_enabled: false` means decay silently no-ops).
  - Done: all impacted tests updated (0 edits if grep returned no ordering-assertions); OR sub-tasks 6.2a/b/c... spawned if count ≥4.
  - Size: 2-45 min depending on hit count (see size-split gate above).
  - `requires: 6.1`

- [ ] **6.3** Run hook-tests before Phase 4b to confirm no regression from Phase 6 edits.
  - Action: `bash plugins/pd/hooks/tests/test-hooks.sh` → count PRE-EXISTING passing tests ≥ `test_hooks_before_082`. **Expected state at this point:** Tasks 4.1 + 4.2 have already added 2 inline test functions (`test_memory_decay_session_start`, `test_memory_decay_missing_module`) that are currently RED (they will fail until Phase 4b wires `run_memory_decay`). So `TESTS_RUN == test_hooks_before_082 + 2`, `TESTS_FAILED == 2` (the new AC-21/22), `TESTS_PASSED == test_hooks_before_082` (or higher if Phase 6 did not need to remediate). **Do NOT debug these 2 failures** — they go green in Task 4.6 after Phase 4b lands.
  - Done: baseline re-verified; the only failures are the 2 new AC-21/22 tests; no pre-existing test regressed.
  - Size: 5 min. `requires: 6.2`

### Phase 4b: Land the session-start wiring (tests go green)

- [ ] **4.3** Add `run_memory_decay()` bash function to `session-start.sh` per I-8.
  - Insert the function BEFORE the `main()` function block (anchored textually: immediately before the `# Main` comment line at ~655; do NOT rely on exact line numbers). Copy the PLUGIN_ROOT resolution pattern VERBATIM from `run_doctor_autofix` — `$PLUGIN_ROOT` is set at script-top (line 7: `PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"`) so it IS available to the new function. Use platform-aware `gtimeout 10 / timeout 10` pattern, `$PLUGIN_ROOT/.venv/bin/python` with fallback to `python3`, `PYTHONPATH="${SCRIPT_DIR}/lib"`, stderr-suppressed `2>/dev/null || true`. Include timeout-budget cross-ref comment per I-8.
  - **Verification sub-step:** `grep -n 'PLUGIN_ROOT=' plugins/pd/hooks/session-start.sh` must show line 7 export BEFORE the new function.
  - Done: function added; `bash -n session-start.sh` passes syntax check; PLUGIN_ROOT grep confirms export.
  - Size: 15 min. `requires: 6.3`

- [ ] **4.4** Reorder `session-start.sh` main() to call `run_memory_decay` FIRST.
  - Use textual anchor (NOT line numbers — they may shift): find the line `memory_context=$(build_memory_context)` and insert `local decay_summary=""` + `decay_summary=$(run_memory_decay)` IMMEDIATELY BEFORE it. Keep `run_reconciliation` and `run_doctor_autofix` calls unchanged in their positions (they run after `build_memory_context` in the final order).
  - Done: `bash -n` passes; final invocation order is `decay → memory_context → recon → doctor`.
  - Size: 10 min. `requires: 4.3`

- [ ] **4.5** Add display-prepend block for `decay_summary` per I-8 authoritative anchor.
  - Use textual anchor: insert the new `if [[ -n "$decay_summary" ]]; then ... fi` block IMMEDIATELY AFTER the existing `if [[ -n "$doctor_summary" ]]; then ... fi` block and IMMEDIATELY BEFORE the existing `if [[ -n "$cron_schedule_context" ]]; then ... fi` block. Use the exact pattern matching the other summary prepends.
  - Done: block present in the right position relative to neighboring blocks.
  - Size: 10 min. `requires: 4.4`

- [ ] **4.6** Run full `test-hooks.sh` and confirm AC-21 + AC-22 go green.
  - Action: `bash plugins/pd/hooks/tests/test-hooks.sh` → pass count is exactly `test_hooks_before_082 + 2` (Tasks 4.1 + 4.2 added 2 inline test functions + call sites, so TESTS_RUN increments by 2).
  - Done: Phase 4a tests go green; no existing tests regressed.
  - Size: 5 min. `requires: 4.5`

---

## Phase 5: Config templates + docs sync [PARALLEL: phase-5 with phase-3-or-phase-4]

- [ ] **5.1** Append 5 fields to `plugins/pd/templates/config.local.md`.
  - Fields with exact comments per spec FR-3: `memory_decay_enabled: false`, `memory_decay_high_threshold_days: 30`, `memory_decay_medium_threshold_days: 60`, `memory_decay_grace_period_days: 14`, `memory_decay_dry_run: false`.
  - Done: 5 new lines + comments added.
  - Size: 10 min. `requires: 3.7` (spec FR-3 validated)

- [ ] **5.2** Append same 5 fields to `.claude/pd.local.md`.
  - Same fields, same values (all defaults — no debug-collection flip since spec says opt-in).
  - Done: 5 new lines in repo config.
  - Size: 5 min. `[PARALLEL: phase-5]` `requires: 5.1`

- [ ] **5.3** Append 5 bullet lines to `README_FOR_DEV.md` memory config table.
  - Insert after `memory_refresh_limit` row (from 081). Format: `- \`memory_decay_enabled\` — ... (default: false)` etc.
  - Done: 5 new lines in the table.
  - Size: 10 min. `[PARALLEL: phase-5]` `requires: 5.1`

- [ ] **5.4** Run AC-25 + AC-26 verification greps.
  - `grep -c "^memory_decay_" plugins/pd/templates/config.local.md` → 5.
  - `grep -c "^memory_decay_" .claude/pd.local.md` → 5.
  - `grep -c "memory_decay_" README_FOR_DEV.md` → ≥5.
  - Done: all 3 counts match.
  - Size: 5 min. `requires: 5.2, 5.3`

---

## Phase 7: Final verification

- [ ] **7.1** Run full semantic_memory test suite.
  - `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v`. Must pass; count ≥ `memory_tests_before_082` + ~30.
  - Done: all green.
  - Size: 5 min. `requires: 2.7, 3.25, 4.6, 5.4` (explicit dep on 2.7 ensures concurrent-writer tests pass; others are transitively guaranteed).

- [ ] **7.2** Run hook-tests.
  - `bash plugins/pd/hooks/tests/test-hooks.sh`. Must report ≥ `test_hooks_before_082` passing.
  - Done: all green.
  - Size: 5 min. `requires: 7.1`

- [ ] **7.3** Run validate.sh + AC-27 verification.
  - `./validate.sh`. 0 errors; warning count ≤ `validate_warnings_before_082`.
  - **AC-27 check:** verify no new MCP tools were introduced. `grep -rn "@mcp.tool\|@mcp_tool\|def .*tool.*:\|FastMCP" plugins/pd/mcp/` — count must match pre-082 baseline. Alternatively, git diff against main: `git diff main -- plugins/pd/mcp/ | grep -E '^[+].*def (complete_phase|get_phase|...)'` returns 0 new tool definitions. Additive scope per NFR-1 is confined to maintenance.py + database.py + session-start.sh; MCP surface is unchanged.
  - Done: clean; AC-27 confirmed.
  - Size: 10 min. `requires: 7.2`

- [ ] **7.4** Capture `EXPLAIN QUERY PLAN` evidence per R-6.
  - Open memory.db with 10k seeded rows, run `EXPLAIN QUERY PLAN <I-2 SELECT>`, record plan output + actual `elapsed_ms` from AC-24 test in `agent_sandbox/082-eqp.txt`. **Distinct from 082-baselines.txt** — this file is intentionally NOT deleted in Task 7.6; the retrospective command (in /pd:finish-feature) reads it and incorporates into retro.md "Performance" section. After retrospective runs, operator may manually delete `082-eqp.txt`.
  - Done: `agent_sandbox/082-eqp.txt` exists with EQP output + elapsed_ms + hardware context.
  - Size: 10 min. `requires: 7.3`

- [ ] **7.5** Delete `agent_sandbox/082-baselines.txt` (temp file, Phase 7 cleanup).
  - `rm agent_sandbox/082-baselines.txt` and `rm agent_sandbox/082-impacted-tests.txt` (created by Task 6.1). Leave `082-eqp.txt` alone — retrospective needs it.
  - Done: two temp files removed; 082-eqp.txt preserved.
  - Size: 2 min. `requires: 7.4`

---

## Summary

**Task count:** ~45 tasks across 7 phases.
**Estimated total:** 5-15 min per task → ~6-11 hours of focused implementation.
**Parallel groups:** Phase 0 tasks; Phase 5 tasks (docs edits).
**Critical sequencing:** Phase 4a (tests) → Phase 6 (remediate existing) → Phase 4b (land wiring).
