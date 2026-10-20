# Tasks: Influence Tuning + Diagnostics

**Feature:** 080-influence-wiring
**Plan:** plan.md
**Created:** 2026-04-16

## Phase 0: Baselines (prerequisite)

### Task 0.1: Capture validate.sh warning baseline
**File:** `agent_sandbox/080-baselines.txt` (new temp file, deleted in Phase 5 Task 5.7)
**Change:** Before any edits, run `./validate.sh 2>&1 | grep -oE "Warnings: [0-9]+"` and record the count. Write to `agent_sandbox/080-baselines.txt` as `validate_warnings_before_080=N`. Task 3.2 appends `ranking_tests_before_080=M` to the same file.
**Done:** File exists with the validate_warnings_before_080 line.
**Depends on:** none

## Phase 1: Shared helpers + test fixture

### Task 1.1: `_resolve_float_config` tests [TDD: red]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add `TestResolveFloatConfig` class with 5 tests: (a) float passthrough returns as-is, (b) int returns float, (c) string `"0.42"` parses, (d) `True` (bool) rejected → default + warning, (e) string `"bad"` rejected → default + warning. Assert on module-level `_warned_fields` membership for dedup.
**Done:** Tests written; fail with AttributeError (`_resolve_float_config` not defined yet) — red phase.
**Depends on:** none

### Task 1.2: `_resolve_float_config` + module globals [TDD: green]
**File:** `plugins/pd/mcp/memory_server.py`
**Change:**
1. Add `from pathlib import Path` to the import block (after `from contextlib import asynccontextmanager`). Current imports do NOT include Path. **Note:** `sys` is already imported at line 10 — do NOT add it again (Task 1.5 adds sys to a different file, ranking.py).
2. After line 401 (`_project_root`), add block: `_warned_fields: set[str] = set()`, `_influence_debug_write_failed: bool = False`, `INFLUENCE_DEBUG_LOG_PATH = Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"`.
3. Define `_resolve_float_config(key, default)` and private `_warn_and_default(key, raw, default)` per design I-3 (with explicit bool rejection).
**Done:** Task 1.1 tests green; `python -c "from plugins.pd.mcp import memory_server"` (or equivalent import path) loads without ImportError.
**Depends on:** Task 1.1

### Task 1.3: autouse reset fixture (memory_server tests)
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add `@pytest.fixture(autouse=True) def reset_memory_server_state(monkeypatch)` that uses `monkeypatch.setattr(memory_server, "_warned_fields", set())`, `monkeypatch.setattr(memory_server, "_influence_debug_write_failed", False)`, `monkeypatch.setattr(memory_server, "_config", {})` before each test. Document in module docstring: "Tests set specific config values via `monkeypatch.setitem(memory_server._config, key, value)` (NOT direct assignment) so teardown auto-restores."
**Done:** Fixture runs before every test in the file; AC-10 tests see clean state regardless of ordering.
**Depends on:** Task 1.2

### Task 1.4: `_resolve_weight` tests [TDD: red]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_ranking.py`
**Change:** Add `TestResolveWeight` class with 4 tests: (a) float passthrough; (b) bool rejected → default + warning; (c) value 2.5 → clamped to 1.0 silently (no warning); (d) invalid string → default + warning.
**Done:** Tests written; fail.
**Depends on:** none

### Task 1.5: `_resolve_weight` + module globals [TDD: green]
**File:** `plugins/pd/hooks/lib/semantic_memory/ranking.py`
**Change:**
1. Add `import sys` to the import block (current imports: math, datetime only). Required for `sys.stderr.write` in the warning helper.
2. Module-level: `_ranker_warned_fields: set[str] = set()`.
3. Define `_resolve_weight(config, key, default, *, warned)` + private `_ranker_warn_and_default(key, raw, default, warned)` per design I-5 (explicit bool rejection, clamp to [0.0, 1.0] silently).
**Done:** Task 1.4 tests green; `python -c "from semantic_memory import ranking"` loads without ImportError.
**Depends on:** Task 1.4

### Task 1.6: autouse reset fixture (ranking tests)
**File:** `plugins/pd/hooks/lib/semantic_memory/test_ranking.py`
**Change:** Add autouse fixture resetting `_ranker_warned_fields` via monkeypatch.
**Done:** Fixture present; test isolation verified by running `pytest -p no:randomly` and `pytest -p randomly` both green.
**Depends on:** Task 1.5

## Phase 2: memory_server.py wiring

### Task 2.1: AC-1 test (threshold config-driven) [TDD: red]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add test that seeds `monkeypatch.setitem(memory_server._config, "memory_influence_threshold", 0.80)`. Call helper WITHOUT passing a threshold argument (relies on signature default) using synthetic injected entries with known similarity 0.75. Assert `matched == []` (because config=0.80 should reject 0.75). Then set config to 0.55; assert `matched` contains the entry.

**Red-phase rationale:** Before Task 2.2, the helper signature is `threshold: float = 0.70`, so the default-threshold path uses 0.70 regardless of config. Test fails cleanly because matched will include the entry (0.75 ≥ 0.70) even when config says 0.80 — the config value is ignored. After Task 2.2, default becomes `None` → resolves from config → 0.80 → entry excluded. Test flips to green.

**Test scaffolding:** The helper signature is `_process_record_influence_by_content(db, provider, subagent_output_text, injected_entry_names, agent_role, feature_type_id, threshold)`. Check the existing `test_memory_server.py` for an in-memory `db` fixture (likely present — create one if absent: `@pytest.fixture def mem_db(tmp_path): return MemoryDatabase(str(tmp_path / "test.db"))`). Pass `db=mem_db` + a stub `provider`.

**Deterministic similarity:** To produce a known 0.75 similarity, monkeypatch the internal cosine computation path. Look for the chunk-embedding dot-product call in `_process_record_influence_by_content` (around line ~340 based on the function's existing structure) and either (a) mock the embedding provider's output so chunk embeddings are hand-crafted unit vectors with pre-computed dot products = 0.75, OR (b) monkeypatch `np.dot` / the similarity function itself. Option (a) is more realistic; option (b) is simpler. Pick during implementation; document choice in commit message.
**Done:** Test fails with AssertionError (matched is non-empty when config=0.80) — the RIGHT failure, not a TypeError.
**Depends on:** Task 1.2, Task 1.3

### Task 2.2: Threshold resolution in helper [TDD: green]
**File:** `plugins/pd/mcp/memory_server.py`
**Change:** Change `_process_record_influence_by_content` signature `threshold: float = 0.70` → `threshold: float | None = None`. Add resolution block at top: `if threshold is None: threshold = _resolve_float_config("memory_influence_threshold", 0.55)`. Keep existing `threshold = max(0.01, min(1.0, threshold))` clamp.
**Done:** Task 2.1 tests green.
**Depends on:** Task 2.1

### Task 2.3: Wrapper signature change
**File:** `plugins/pd/mcp/memory_server.py`
**Change:** Change `record_influence_by_content` wrapper signature `threshold: float = 0.70` → `threshold: float | None = None`. Still delegates to helper unchanged (no diagnostic emission yet — that's Task 2.6).
**Done:** Wrapper compiles; existing 14 `threshold=0.70` callers still pass explicit value (migration is Phase 5).
**Depends on:** Task 2.2

### Task 2.4: AC-4/AC-5 tests (diagnostics emit/silent) [TDD: red]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add two tests: (AC-4) monkeypatch `INFLUENCE_DEBUG_LOG_PATH = tmp_path / "log.jsonl"`, set `_config["memory_influence_debug"] = True`, invoke the helper directly (not the async wrapper) with 3 synthetic injected entries. Read log file; assert exactly 1 line matching regex `"event": ?"influence_dispatch"`. (AC-5) same setup but `_config["memory_influence_debug"] = False` (or absent); assert log file doesn't exist OR contains 0 matching lines.

**Async harness guidance:** The MCP wrapper `record_influence_by_content` is `async def` with `@mcp.tool()`. Rather than setting up `pytest-asyncio`, **call the emission path via a synchronous helper.** Option A: test `_emit_influence_diagnostic` in isolation (post-Task-2.5). Option B: since diagnostic emission runs in the wrapper (I-2b), and the wrapper's non-async parts can be unit-tested, extract the diagnostic block into a named sync function `_maybe_emit_diagnostic(result_json, ...)` that the wrapper calls — tests then invoke that sync function directly. Pick Option A if the implementer's first instinct works; Option B if async-harness friction appears.
**Done:** Both tests fail (no diagnostic emitter yet).
**Depends on:** Task 2.3

### Task 2.5: `_emit_influence_diagnostic` helper [TDD: green, partial]
**File:** `plugins/pd/mcp/memory_server.py`
**Change:** Define `_emit_influence_diagnostic(*, agent_role, injected, matched, threshold, feature_type_id)` per design I-4. `Path.mkdir(parents=True, exist_ok=True)`, `strftime("%Y-%m-%dT%H:%M:%SZ")`, append JSON line.
**Except clause:** Catch `(OSError, IOError)` broadly — `IsADirectoryError` and `PermissionError` both subclass `OSError`, so the broad catch covers AC-10(d). Do NOT narrow to `PermissionError` or `FileNotFoundError` alone.
**Flag semantics:** On first exception, `if not _influence_debug_write_failed`: emit stderr warning + set flag to True. Subsequent calls silent. Flag reset per-test via autouse fixture (Task 1.3).
**Done:** Function defined; not yet wired into wrapper.
**Depends on:** Task 2.4

### Task 2.6: Wire diagnostic into wrapper [TDD: green]
**File:** `plugins/pd/mcp/memory_server.py`
**Change:** Per design I-2b, in wrapper after helper returns: `if _config.get("memory_influence_debug", False):` → `json.loads` the result, extract `matched_count = len(result.get("matched", []))`, re-resolve effective threshold (`_resolve_float_config` if None) + clamp for parity, call `_emit_influence_diagnostic(...)`. Wrap with try/except `(json.JSONDecodeError, TypeError)` for malformed result JSON.

**@with_retry semantics note:** The helper `_process_record_influence_by_content` is decorated with `@with_retry("memory")`. If the helper retries on a transient DB lock, it re-enters — threshold resolution runs multiple times, but the diagnostic is emitted from the wrapper (OUTSIDE the retry boundary), so exactly one log line per outer MCP call regardless of retry count. `matched_count` comes from the final successful helper return.
**Done:** Task 2.4 tests green (AC-4 + AC-5).
**Depends on:** Task 2.5

### Task 2.7: AC-10 error-handling tests
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** 4 tests per spec AC-10: (a) non-float threshold → default 0.55 + one stderr warning regex; (c) log dir missing parent → `Path.mkdir` creates it; (d) log path is a directory (write fails) → first call emits one stderr warning, second call silent, response JSON well-formed both times; (e) `memory_influence_threshold: True` (bool) → default 0.55 + one warning.
**Done:** All 4 tests green.
**Depends on:** Task 2.6

### Task 2.8: AC-6 lowered default test
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Seed `_config = {}` (no override). Call helper with `threshold=None`. Use synthetic similarity 0.60. Assert `matched` contains entry (0.60 ≥ 0.55 default). Flip similarity to 0.50; assert empty matched.
**Done:** Test green. Confirms new 0.55 default active.
**Depends on:** Task 2.6

## Phase 3: ranking.py wiring (parallel with Phase 2 after Phase 1)

### Task 3.1: AC-2 test (weight config-driven) [TDD: red]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_ranking.py`
**Change:** Instantiate `RankingEngine(config={"memory_influence_weight": 0.30, ...required base config})`. Call `_prominence(entry_hi_influence, max_obs=10, now=<time>)` with `entry_hi_influence["influence_count"]=10` vs `entry_lo_influence["influence_count"]=0` (both otherwise identical). Assert `prominence_hi - prominence_lo >= 0.29`.
**Done:** Test fails because `_prominence` still uses hardcoded 0.05.
**Depends on:** Task 1.5

### Task 3.2: AC-3 regression baseline capture
**File:** `agent_sandbox/080-baselines.txt` (new temp file, deleted in Phase 5)
**Change:** Before Task 3.3/3.4, run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_ranking.py 2>&1 | tail -1` — capture the "N passed" number. Write to `agent_sandbox/080-baselines.txt` as:
```
ranking_tests_before_080=N
validate_warnings_before_080=M
```
(M comes from Task 0 below — they can share this file.)
**Done:** File exists with both lines; Task 3.4 Done criterion references `ranking_tests_before_080`.
**Depends on:** Task 1.6 (ranking fixture exists)

### Task 3.3: `_influence_weight` in `RankingEngine.__init__` [TDD: green]
**File:** `plugins/pd/hooks/lib/semantic_memory/ranking.py`
**Change:** After existing `_prominence_weight` at line 35, add: `self._influence_weight: float = _resolve_weight(config, "memory_influence_weight", 0.05, warned=_ranker_warned_fields)`.
**Done:** Attribute populated on construction.
**Depends on:** Task 3.1, Task 1.5

### Task 3.4: Replace hardcoded coefficient in `_prominence` [TDD: green]
**File:** `plugins/pd/hooks/lib/semantic_memory/ranking.py`
**Change:** At line 252, replace `0.05 * influence` → `self._influence_weight * influence`.
**Done:** Task 3.1 test green. Task 3.2 baseline tests still pass (AC-3).
**Depends on:** Task 3.3

### Task 3.5: AC-10(b) clamp test
**File:** `plugins/pd/hooks/lib/semantic_memory/test_ranking.py`
**Change:** Instantiate `RankingEngine(config={"memory_influence_weight": 2.5})`. Assert `ranker._influence_weight == 1.0` (clamped). Assert no stderr warning (operator is intentionally tuning).
**Done:** Test green.
**Depends on:** Task 3.3

## Phase 4: Config templates + docs sync

### Task 4.1: Append fields to config template
**File:** `plugins/pd/templates/config.local.md`
**Change:** Append 3 fields with exact comment text per FR-4 (memory_influence_threshold: 0.55, memory_influence_weight: 0.05, memory_influence_debug: false).
**Done:** `grep -c "memory_influence_" plugins/pd/templates/config.local.md` returns 3.
**Depends on:** none (parallel-eligible — field names fixed by spec FR-4; AC-11 grep in Task 5.5 is integration gate)

### Task 4.2: Append fields to in-repo config
**File:** `.claude/pd.local.md`
**Change:** Append same 3 fields, but `memory_influence_debug: true` for baseline collection.
**Done:** `grep -c "memory_influence_" .claude/pd.local.md` returns 3; debug value is `true`.
**Depends on:** none (parallel-eligible — field names fixed by spec FR-4; AC-11 grep in Task 5.5 is integration gate)

### Task 4.3: Append fields to README_FOR_DEV.md
**File:** `README_FOR_DEV.md`
**Change:** After line 527 (`memory_promote_min_observations`), insert 3 bullet entries per FR-6.
**Done:** AC-11: `grep -c "memory_influence_" README_FOR_DEV.md` returns exactly 3.
**Depends on:** none (parallel-eligible — field names fixed by spec FR-4; AC-11 grep in Task 5.5 is integration gate)

## Phase 5: 14-caller migration + final verification

### Task 5.1: Migrate specify.md call sites
**File:** `plugins/pd/commands/specify.md`
**Change:** Remove `threshold=0.70` from the 2 occurrences per C-5 canonical form (multi-line: delete the argument line and move `)` to end of previous argument).

**Indentation note:** specify.md/design.md/create-plan.md use 7-space indentation for call-site args (e.g., `       threshold=0.70)`); implement.md uses 4-space. Preserve each file's existing indentation — do NOT normalize across files.
**Done:** `grep -c "threshold=0.70" plugins/pd/commands/specify.md` returns 0.
**Depends on:** Task 2.3

### Task 5.2: Migrate design.md call sites
**File:** `plugins/pd/commands/design.md`
**Change:** Same as 5.1 for the 2 occurrences.
**Done:** `grep -c "threshold=0.70" plugins/pd/commands/design.md` returns 0.
**Depends on:** Task 2.3

### Task 5.3: Migrate create-plan.md call sites
**File:** `plugins/pd/commands/create-plan.md`
**Change:** Same as 5.1 for the 3 occurrences.
**Done:** `grep -c "threshold=0.70" plugins/pd/commands/create-plan.md` returns 0.
**Depends on:** Task 2.3

### Task 5.4: Migrate implement.md call sites
**File:** `plugins/pd/commands/implement.md`
**Change:** Same as 5.1 for the 7 occurrences. Audit each for single-line vs multi-line form.
**Done:** `grep -c "threshold=0.70" plugins/pd/commands/implement.md` returns 0.
**Depends on:** Task 2.3

### Task 5.5: AC-7 verification grep
**File:** (verification only — no edit)
**Change:** Run `grep -rn "threshold=0.70" plugins/pd/commands/*.md | wc -l`.
**Done:** Returns `0`.
**Depends on:** Task 5.1, 5.2, 5.3, 5.4

### Task 5.6: AC-7b typo-catch grep
**File:** (verification only — no edit)
**Change:** Run `grep -rEn "threshold=0\.[0-9]" plugins/pd/commands/*.md | wc -l`.
**Done:** Returns `0` (catches any residual literal threshold).
**Depends on:** Task 5.5

### Task 5.7: Full test + validate.sh verification
**File:** (verification only; deletes `agent_sandbox/080-baselines.txt` after use)
**Change:** Read baselines from `agent_sandbox/080-baselines.txt` (captured in Task 0.1 + Task 3.2). After all prior tasks complete, run:
   - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ plugins/pd/mcp/test_memory_server.py -v` (full memory + MCP tests)
   - `bash plugins/pd/hooks/tests/test-hooks.sh` (hook integration tests — RankingEngine is consumed by SessionStart injector)
   - `./validate.sh`

After green, delete `agent_sandbox/080-baselines.txt` (temp file, not committed).
**Done:**
- pytest: all green (includes ≥12 new tests for this feature; `ranking_tests_before_080` still pass per AC-3).
- test-hooks.sh: all existing hook tests still pass.
- `./validate.sh`: 0 errors; warning count ≤ `validate_warnings_before_080` (no new warnings introduced).
- Temp baseline file removed.
**Depends on:** all prior tasks
