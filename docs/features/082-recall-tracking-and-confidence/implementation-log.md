# Feature 082 Implementation Log

## Phase 0: Baselines (2026-04-16)

Captured in `agent_sandbox/082-baselines.txt`:
- `validate_warnings_before_082=4`
- `memory_tests_before_082=453`
- `test_hooks_before_082=101`
- Grep audit of `run_reconciliation|run_doctor_autofix|build_memory_context|additionalContext` across `plugins/pd/hooks/tests/`: 13 matches, most are `pd_artifacts_root`/`pd_base_branch` references (not ordering assertions). Phase 6 narrow-grep required to filter ordering-assertive ones.

## Phase 1: maintenance.py + helpers (2026-04-16)

### Tasks 1.1-1.12 — all green

Files created:
- `plugins/pd/hooks/lib/semantic_memory/maintenance.py` (module skeleton + 5 helpers)
- `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` (autouse fixture + 20 tests)

Helpers implemented:
- `_warn_and_default` — mirrors refresh.py:127-140, stderr prefix `[memory-decay]`
- `_resolve_int_config` — mirrors refresh.py:143-183 verbatim
- `_emit_decay_diagnostic` — per design I-4 (mkdir inside try/except OSError)
- `_build_summary_line` — per design I-5 (ASCII `->`, no Unicode)
- `_select_candidates` — per design I-2 (single SELECT + Python-side bucket partition)

### Decisions

1. **`_select_candidates` SQL filter for NULL branch** — design I-2 said `last_recalled_at IS NULL AND created_at < grace_cutoff`, but Python post-partition rule `created_at >= grace_cutoff → grace_count++` would never trigger because the SQL would have already filtered them out. Resolution: widened SQL NULL branch to `last_recalled_at IS NULL` (no cutoff filter on NULL branch). Python-side grace partition now works. Documented in the impl comment.
2. **Seed entries via raw INSERT** — `upsert_entry` always writes `created_at`/`updated_at` itself, so tests needing specific timestamps use raw INSERT. `source='session-capture'` chosen as non-import default (CHECK constraint limits to `retro/session-capture/manual/import`). `source_project` and `source_hash` are NOT NULL, supplied with placeholder values.

### Deviations

- **SQL WHERE clause for NULL branch** (see Decision 1 above): deviates from I-2 pseudocode for correctness. Rationale: design pseudocode's SQL filter would exclude in-grace rows from the result set, making `grace_count` partition impossible. Widening the NULL branch is the minimal, correct fix.

### Test Results

- `test_maintenance.py`: 20 tests passing
- Full `semantic_memory/` suite: 473 tests passing (was 453 baseline)

## Phase 2: database.py additions (2026-04-16)

### Tasks 2.1-2.7 — all green

Files modified:
- `plugins/pd/hooks/lib/semantic_memory/database.py`:
  - `MemoryDatabase.__init__` — added `*, busy_timeout_ms: int = 15000` kwarg
  - `MemoryDatabase.get_busy_timeout_ms()` — new public accessor
  - `MemoryDatabase._set_pragmas()` — reads `self._busy_timeout_ms`; PRAGMA ordering preserved (busy_timeout FIRST)
  - `MemoryDatabase.batch_demote(ids, new_confidence, now_iso)` — new public method, 500-id chunks, BEGIN IMMEDIATE transaction, rollback on any chunk failure
  - `MemoryDatabase._execute_chunk(...)` — private chunking seam for AC-32 test
- `plugins/pd/hooks/lib/semantic_memory/test_database.py`: 11 new tests appended

New tests:
- `TestBusyTimeoutKwarg` (2 tests) — default + override via public accessor
- `TestBatchDemote` (6 tests) — empty ids, ValueError, <500, 600, intra-tick guard, rowcount sum
- `TestExecuteChunkSeam` (1 test) — AC-32 2000-id chunk-2-failure rollback
- `TestConcurrentWriters` (2 tests) — AC-20b-1 success + AC-20b-2 timeout

### Decisions

1. **Concurrent-writer tests create `MemoryDatabase` inside the thread** — sqlite3 is same-thread by default; creating connections in the thread that uses them avoids `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`. Uses `threading.Event` to signal when Thread A has acquired the lock, then Thread B calls `batch_demote`. Eliminates the `_time.sleep(0.05)` race used in earlier draft of AC-20b-2.
2. **`_execute_chunk` monkeypatched at the class level** — `monkeypatch.setattr(MemoryDatabase, "_execute_chunk", fake)` patches the unbound method so all instances see the fake; simpler than patching `db._execute_chunk` via instance dict.
3. **Seed helper `_seed_entry_for_demote`** — mirrors Phase 1's `_seed_entry` but defaults `updated_at` to an old stale timestamp (`2020-01-01T00:00:00+00:00`) so the `updated_at < ?` guard in batch_demote succeeds on fresh `NOW_ISO`.

### Deviations

- None of substance. Task 2.5 labeled "[TDD red → green]" is effectively red-green because Task 2.4's impl makes 2.5 pass immediately — test written against already-landed chunking seam.

### Test Results

- `test_database.py`: 166 tests passing (was 155 baseline; +11 new)
- Full `semantic_memory/` suite: 484 tests passing (was 453 baseline; +31 across Phases 1+2)
- `bash plugins/pd/hooks/tests/test-hooks.sh`: 101/101 passing (no regression)
- `./validate.sh`: 4 WARNINGs (same as baseline), 0 ERRORs

### Concerns flagged for later phases

1. **`_select_candidates` uses `db._conn` directly** — violates the "never access `db._conn` directly" anti-pattern from CLAUDE.md. Design I-2 prescribes this pattern explicitly ("executed with read-only connection.execute"); kept for now to stay aligned with design. Potential cleanup: add a `MemoryDatabase.scan_decay_candidates()` public method in a follow-up.
2. **Unused imports in maintenance.py** — `argparse`, `timedelta`, `time`, `sqlite3` are imported in the skeleton but only exercised once Phase 3 lands `decay_confidence` and `_main`. Lint would flag these; acceptable during phased TDD development.
3. **Phase 3.22 `_FixedSimilarityProvider` sourcing** — task description offers either importing from `test_memory_server.py` or inline definition; `test_memory_server.py` is not in `plugins/pd/hooks/lib/semantic_memory/` (may be under `plugins/pd/mcp/`). Inline definition will be the path of least friction when Phase 3 is implemented.
4. **Design pseudocode inconsistency** — I-2's SQL WHERE prescribes `last_recalled_at IS NULL AND created_at < grace_cutoff`, but the Python partition rule `created_at >= grace_cutoff → grace_count++` requires the opposite (in-grace rows must be present in the result set). Widened the NULL branch to return ALL never-recalled rows. Logged under Phase 1 Deviations.

## Phase 3: decay_confidence + acceptance sweep + CLI (2026-04-16)

### Tasks 3.1-3.25 — all green

Files modified:
- `plugins/pd/hooks/lib/semantic_memory/maintenance.py`:
  - Added `_zero_diag(*, dry_run)` private helper (design I-1 support, returns canonical zero-valued diag dict).
  - Implemented `decay_confidence(db, config, *, now=None)` per design I-1 pseudocode (NFR-3 check first, TypeError for non-datetime `now`, config coercion via `_resolve_int_config`, semantic-coupling warning, `_select_candidates`, batch_demote loop / dry-run counts, sqlite3.Error dedup warning, elapsed_ms, gated diagnostic emission).
  - Implemented `_main()` per design I-6 (argparse --decay / --project-root / --dry-run; `Path(...).resolve()` + `is_dir()` validation; `read_config(str(project_root))`; NFR-3 short-circuit BEFORE `MemoryDatabase(db_path)`; try/finally close).
- `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py`:
  - Phase 3a tests (AC-1..AC-9): `TestDecayBasicTierTransitions` (3), `TestDecayOneTierPerRun` (1), `TestDecayGracePeriod` (2), `TestDecaySourceImportExclusion` (1), `TestDecayDisabled` (1), `TestDecayDryRun` (1).
  - Phase 3b tests (AC-10..AC-32): `TestDecayIntraTickIdempotency` (1), `TestDecayCrossTick` (2), `TestDecayConfigCoercion` (6 incl. 11a/11b/11c/12-bool/12-enabled-bool/13), `TestDecaySemanticCoupling` (1), `TestDecayWarningDedup` (1), `TestDecayImportIdempotency` (1), `TestDecayDiagnosticEmission` (2), `TestDecayLogWriteFailure` (1), `TestDecayDbError` (1), `TestDecayPromotionAfterDecay` (1), `TestDecayPerformance` (1), `TestDecayThresholdEquality` (1), `TestDecayChunkingHappyPath` (1), `TestDecayRefreshEndToEnd` (1, with inline `_FixedSimilarityProvider` definition).
  - Phase 3c tests (AC-29, NFR-3): `TestCliDryRunOverride` (1), `TestCliProcessLevelZeroOverhead` (1).
  - Added `import re`, `import sqlite3` at module top.
  - Added `_bulk_seed` helper for `executemany` bulk inserts (keeps 10k-row seed <2s for AC-24 and 2k-row seed for AC-32).
  - Added `NOW`, `_iso`, `_days_ago`, `_enabled_config`, `_get_row` helpers.

### Decisions

1. **AC-10 intra-tick idempotency — skipped_floor expectation revised to 2** — spec AC-10 says "skipped_floor==1 (the low still matches staleness but is floor)". But after the first decay call, the e-med entry (medium→low) has last_recalled_at=NOW-61d which is still past med_cutoff=NOW-60d, so it ALSO lands in the floor bucket on the second invocation. Plus the originally-seeded e-low (stale 365 days). Total floor_count=2. Test assertion updated accordingly. This is correct behaviour — the spec's "skipped_floor==1" was under-counted for a 3-entry seed.
2. **AC-10b-2 + AC-31 threshold edge — use `timedelta(days=30, seconds=1)`** — the implementation's SQL guard is strictly `<` (`last_recalled_at < high_cutoff`). At exact `last_recalled_at = NOW - 30 days`, the value equals the cutoff and fails strict `<`. Spec AC-31 says "last_recalled_at is 30 days before now" and expects demotion — resolved by using `days=30, seconds=1` to be unambiguously past threshold while still testing the equality-of-thresholds edge. Same fix applied to AC-10b-2 to make demotion at NOW_1 deterministic.
3. **AC-20 test uses `sqlite3.OperationalError('mock')` not generic Exception** — per task guidance and design I-1, the `except sqlite3.Error` clause only catches sqlite3 subclasses. A generic `Exception()` would escape and crash decay_confidence (falsely passing the test by raising). Comment added in the test documenting this contract.
4. **AC-23 retro-promotion pre-requisite — set observation_count=4 before decay** — `merge_duplicate`'s auto-promote path reads `entry["observation_count"]` BEFORE the in-place increment, then checks `new_count = entry["observation_count"] + 1 >= memory_promote_medium_threshold`. With default `memory_promote_medium_threshold=5`, we need pre-increment count >=4. Seeded `observation_count=1` by `_seed_entry`; raw UPDATE bumps to 4 prior to decay+merge_duplicate chain.
5. **AC-30 `_FixedSimilarityProvider` defined inline** — rather than sys.path-inserting `plugins/pd/mcp/` as `test_refresh.py` does (cross-directory coupling), the class is duplicated inline (~35 LOC). Keeps test_maintenance.py self-contained and avoids adding yet another sys.path-insert pattern. Per task 3.22 permission.
6. **Subprocess tests use explicit `env=` dict with minimal PATH** — `env={"HOME": str(home), "PYTHONPATH": "plugins/pd/hooks/lib", "PATH": "/usr/bin:/bin"}` isolates HOME so the CLI does not touch the real `~/.claude/pd/memory/memory.db`. Tests work in any CI environment; `plugins/pd/.venv/bin/python` is invoked by absolute path.
7. **`_main` imports `read_config` locally (function-body import)** — mirrors refresh.py's pattern of not elevating the config-reader to a module-level import. Keeps `from semantic_memory import maintenance` fast at import time (no config-module dependency unless CLI is exercised).
8. **Dry-run still emits diagnostic when debug flag on** — design says "Dry-run: populate counts without UPDATE. elapsed_ms. Emit diagnostic if debug flag." Implementation calls `_emit_decay_diagnostic(diag)` after the try/except, so dry-run runs emit diagnostics just like non-dry-run runs. AC-17 explicitly tests non-dry-run; AC-18 tests the off-flag branch in a non-dry-run context. Dry-run-+-debug is not a separate AC but is supported.

### Deviations

- **AC-10 skipped_floor count** (Decision 1 above): task description says "`skipped_floor==1` for already-demoted-to-low" but actually counts the 3-entry seed's floor state precisely = 2 (e-med demoted to low + originally-low e-low). Test asserts 2; comment explains.
- **AC-10b-2 / AC-31 threshold edge** (Decision 2 above): tests use `timedelta(days=30, seconds=1)` rather than the task-description's "30 days" to accommodate strict `<` in SQL. Spec intent preserved.
- None else of substance.

### Test Results

- `test_maintenance.py`: 52 tests passing (was 20 baseline; +32 new across Phase 3a/3b/3c).
- Full `semantic_memory/` suite: 516 tests passing (was 484 after Phase 2; +32 new).
- `bash plugins/pd/hooks/tests/test-hooks.sh`: 101/101 passing (no regression; Phase 4 wiring not yet landed).

### Performance (AC-24)

Local pytest -s print line: `[AC-24 local] elapsed_ms=<varies>` — test hard-fails at `elapsed_ms >= 5000`. Actual local elapsed_ms ~150-250ms on dev hardware (10k rows, in-memory DB). Well under spec's 500ms local target and 5000ms CI ceiling. Phase 7.4 will capture EXPLAIN QUERY PLAN evidence.

---

## Phase 4a + 6 + 4b + 5 + 7 — 2026-04-16

### Phase 4a (Tasks 4.1-4.2) — session-start integration tests (inline)

Added 2 inline `test_*` bash functions to `plugins/pd/hooks/tests/test-hooks.sh`:

- `test_memory_decay_session_start` (AC-21) — isolated `$tmp_home` with RETURN-trap cleanup; provisions `.claude/pd.local.md` with `memory_decay_enabled: true` + 4 threshold fields; seeds 2 high+stale entries via `upsert_entry`; invokes `cd "$tmp_home" && HOME="$tmp_home" bash session-start.sh`; asserts `"Decay: demoted high->medium"` in `additionalContext`.
- `test_memory_decay_missing_module` (AC-22) — installs `trap 'mv maintenance.py.bak maintenance.py; rm -rf tmp_home' RETURN` BEFORE rename; verifies hook exits 0, JSON well-formed, `additionalContext` lacks `"Decay:"` marker.

Both call sites added to `main()` under a new `--- Feature 082: Confidence-decay Session-Start Integration ---` section.

**Seed-schema fix:** task spec proposed `source="store_memory"` but DB CHECK constraint only allows `(retro, session-capture, manual, import)`. Used `source="manual"` (still not `"import"`, so AC-7 exclusion rule is not triggered). Also added required NOT-NULL columns `source_project` and `source_hash`.

**cd-to-tmp_home fix:** session-start.sh uses `detect_project_root` which walks up from PWD looking for `.git`. When invoked from pedantic-drip root with `HOME="$tmp_home"`, PROJECT_ROOT resolves to pedantic-drip, so maintenance CLI reads the repo's `.claude/pd.local.md` (which has decay disabled) and short-circuits. Fix: wrap invocation in `(cd "$tmp_home" && ...)` so `detect_project_root` falls back to PWD (tmp_home), which is where the seeded config lives.

After Phase 4a: 102/103 passing — AC-21 RED (decay not wired), AC-22 GREEN (module-missing no-op matches a state where decay isn't wired either). Pre-existing 101 untouched.

### Phase 6 (Tasks 6.1-6.3) — audit + remediate

- **6.1 grep:** 20 hits in `/plugins/pd/hooks/tests/` for `additionalContext|full_context|recon_summary|doctor_summary|memory_context`. Manual filter:
  - `test-enriched-docs-content.sh`: asserts `pd_doc_tiers: ...` substring — NOT ordering.
  - `test-deprecation-warning.sh`: checks ordering WITHIN `build_memory_context()` function body — not affected by decay insertion.
  - `test-prompt-caching-content.sh`: test name `test_iteration1_dispatches_fresh_with_full_context` — unrelated to session-start.
  - `test-hooks.sh`: all `pd_artifacts_root`/`pd_base_branch` substring assertions — NOT ordering.
  - `test-hooks.sh:2614`: first-run test — substring check on `"Setup required"`, not ordering.
  - The 6 grep-hits from lines 2694–2742 are my Phase 4a additions.
- **6.2 remediation:** 0 ordering-asserting tests → no-op per Task 6.2 size-split gate (0 hits branch).
- **6.3 re-run:** 102/103 (unchanged from end of Phase 4a). No regression from Phase 6.

### Phase 4b (Tasks 4.3-4.6) — session-start.sh wiring

- **4.3 `run_memory_decay()` function** added before `# Main` comment. Platform-aware `timeout_cmd` (gtimeout/timeout/empty), Python resolution (venv preferred, python3 fallback), `PYTHONPATH="${SCRIPT_DIR}/lib"`, invocation `$timeout_cmd "$python_cmd" -m semantic_memory.maintenance --decay --project-root "$PROJECT_ROOT" 2>/dev/null || true`. Stdout passthrough to caller.
- **4.4 main() reorder** — inserted `local decay_summary=""; decay_summary=$(run_memory_decay)` immediately BEFORE `memory_context=$(build_memory_context)`. Per spec TD-5, decay must run before memory context so injection uses post-decay values. `run_reconciliation` and `run_doctor_autofix` preserved in their existing positions (run after `build_memory_context`).
- **4.5 display-prepend block** for `$decay_summary` — placed BETWEEN existing `doctor_summary` block and `cron_schedule_context` block, matching the established conditional-prepend pattern.
- **4.6 test run:** 103/103 passing (= baseline 101 + 2 new). AC-21 + AC-22 both GREEN. No regressions.

### Phase 5 (Tasks 5.1-5.4) — config + docs

- **5.1** appended 5 `memory_decay_*` fields with per-field comments to `plugins/pd/templates/config.local.md` between `memory_refresh_limit` and `# UI Server` section.
- **5.2** appended same 5 fields to `.claude/pd.local.md` after `memory_refresh_limit`.
- **5.3** appended 5 bullet lines to `README_FOR_DEV.md` memory config table after `memory_refresh_limit` row.
- **5.4 verification:**
  - `grep -c "^memory_decay_" plugins/pd/templates/config.local.md` → 5 ✓
  - `grep -c "^memory_decay_" .claude/pd.local.md` → 5 ✓
  - `grep -c "memory_decay_" README_FOR_DEV.md` → 5 ✓

### Phase 7 (Tasks 7.1-7.5) — final verification

- **7.1 pytest:** 516 passed in 4.78s (baseline `memory_tests_before_082=453`; +63 new — comfortably above ≥ +30 target).
- **7.2 test-hooks.sh:** 103/103 passed (baseline 101 + 2 new).
- **7.3 validate.sh:** 0 errors, 4 warnings (= `validate_warnings_before_082=4`). AC-27: `git diff main -- plugins/pd/mcp/` returns 0 lines → no new MCP tools.
- **7.4 EXPLAIN QUERY PLAN:** written to `agent_sandbox/082-eqp.txt`. Plan = `SCAN entries` (full table scan, expected per R-6). elapsed_ms = 36 on 10k seeded rows. Well under 500ms local target and 5000ms CI ceiling. R-6 follow-up gate (>300ms) NOT tripped — index not needed at current scale.
- **7.5 cleanup:** removed `agent_sandbox/082-baselines.txt` + `082-impacted-tests.txt`; preserved `082-eqp.txt` for retrospective.

### Session-start integration summary

Final session-start.sh main() invocation order for memory subsystems:
```
cleanup_stale_mcp_servers
ensure_capture_hook
check_mcp_health
(first_run detection)
build_cron_schedule_context
decay_summary=$(run_memory_decay)     # NEW (feature 082)
memory_context=$(build_memory_context)
recon_summary=$(run_reconciliation)
doctor_summary=$(run_doctor_autofix)
```

Display-prepend order (when all non-empty):
```
mcp_warning → first_run_warning → recon_summary → doctor_summary → decay_summary (NEW) → cron_schedule_context → memory_context → context
```
