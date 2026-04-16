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
