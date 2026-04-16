# Tasks: Orchestrator Mid-Session Memory Refresh

**Feature:** 081-mid-session-memory-refresh-hoo
**Plan:** plan.md
**Created:** 2026-04-16

## Phase 0: Baselines

### Task 0.1: Capture validate.sh warning baseline
**File:** `agent_sandbox/081-baselines.txt` (new temp file, deleted in Task 7.4)
**Change:** Run `./validate.sh 2>&1 | grep -oE "Warnings: [0-9]+"` — record count. Write to file as `validate_warnings_before_081=N`.
**Done:** File exists with the line.
**Depends on:** none

### Task 0.2: Capture test count baselines
**File:** `agent_sandbox/081-baselines.txt` (append)
**Change:** Run three pytest commands in collect-only mode using the project's venv + PYTHONPATH (matching Phase 7's pattern):
- `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py --collect-only -q 2>&1 | tail -1` → `memory_tests_before_081=N`
- `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py --collect-only -q 2>&1 | tail -1` → `workflow_state_tests_before_081=M`
- `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_ranking.py --collect-only -q 2>&1 | tail -1` → `ranking_tests_before_081=K`
**Done:** File contains three count lines.
**Depends on:** Task 0.1

### Task 0.3: Existing-test audit — capture enclosing test function names
**File:** `agent_sandbox/081-baselines.txt` (append as `# audit: test_name_1, test_name_2, ...` line)
**Change:** Find tests that may assert on exact `complete_phase` response shape. Simple grep for matching lines doesn't give function context, so use a two-step approach:
1. `grep -B 20 'complete_phase\|last_completed_phase' plugins/pd/mcp/test_workflow_state_server.py | grep -E '^\s*def test_' | sort -u` — captures the test functions in whose bodies the pattern appears (within 20 lines before).
2. Extract just the function names (strip `def test_` prefix and `(self, ...):` suffix).
3. Append as a single line: `# audit: test_name_1, test_name_2, ...`. If empty, append `# audit: <none>`.

Fallback if step 1 is noisy: use pytest-collection + manual inspection. Record method either way.
**Done:** File has a single `# audit:` line with comma-separated test names (or `<none>`).
**Depends on:** Task 0.2

## Phase 1: refresh.py shared module

### Task 1.1: test_refresh.py scaffold + autouse reset fixture
**File:** `plugins/pd/hooks/lib/semantic_memory/test_refresh.py` (NEW)
**Change:** Create test file with pytest imports + `from semantic_memory import refresh`. Add `@pytest.fixture(autouse=True) def reset_refresh_state(monkeypatch)` that resets `_slow_refresh_warned=False`, `_refresh_error_warned=False`, `_refresh_warned_fields=set()` via `monkeypatch.setattr(refresh, ...)`. Include module docstring explaining `monkeypatch.setitem` pattern for config.
**Done:** File exists; fixture defined; empty test placeholder (`def test_scaffold_imports(): pass`) passes.
**Depends on:** none

### Task 1.2: `build_refresh_query` tests [TDD: red]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_refresh.py`
**Change:** Add `TestBuildRefreshQuery` class with 4 tests:
- `test_normal_slug_and_next_phase` — AC-4a: `"feature:081-mid-session-memory-refresh-hoo", "specify"` → `"mid-session-memory-refresh-hoo design"`.
- `test_finish_terminal` — AC-4b: `("...", "finish")` → `"mid-session-memory-refresh-hoo"` (no trailing space).
- `test_three_digit_id` — AC-4c: `"feature:100-foo-bar", "design"` → `"foo-bar create-plan"`.
- `test_regex_mismatch_returns_none` — AC-4d: `"feature:weird-id", "specify"` → `None`.
**Done:** Tests fail with AttributeError (function not defined).
**Depends on:** Task 1.1

### Task 1.3: `build_refresh_query` implementation [green]
**File:** `plugins/pd/hooks/lib/semantic_memory/refresh.py` (NEW)
**Change:** Create module with top-of-file imports (`re`, `pathlib.Path`, `datetime`, `json`, `sys`, `time`). Define `_FEATURE_SLUG_RE = re.compile(r"^feature:\d+-(.+)$")`. Define `_NEXT_PHASE` dict per design I-2. Define `build_refresh_query(feature_type_id, completed_phase)` returning `None` on regex mismatch, `f"{slug} {_NEXT_PHASE.get(completed_phase, '')}".strip()` otherwise.
**Done:** Task 1.2 tests green.
**Depends on:** Task 1.2

### Task 1.4: `_resolve_int_config` tests [TDD: red]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_refresh.py`
**Change:** Add `TestResolveIntConfig` class with tests per AC-5 + bool/dedup:
- `test_int_passthrough`
- `test_string_parse_int`
- `test_bool_rejected` (`True` → default + warning)
- `test_float_rejected` (`5.7` → default + warning; int helper must NOT accept floats)
- `test_invalid_string_rejected` (`"bad"` → default + warning)
- `test_clamp_above_max` (`100` with clamp=(1,20) → 20; no warning — silent clamp)
- `test_clamp_below_min` (`0` with clamp=(1,20) → 1; no warning)
- `test_warning_deduped_across_calls` (call twice with bool; assert exactly one stderr warning via capsys)
**Done:** Tests fail.
**Depends on:** Task 1.1

### Task 1.5: `_resolve_int_config` + module globals [green]
**File:** `plugins/pd/hooks/lib/semantic_memory/refresh.py`
**Change:**
1. Add module-level globals: `_refresh_warned_fields: set[str] = set()`, `_slow_refresh_warned: bool = False`, `_refresh_error_warned: bool = False`.
2. Add module-level constants: `REFRESH_OVERSAMPLE_FACTOR: int = 3`, `INFLUENCE_DEBUG_LOG_PATH = Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"`.
3. Define `_resolve_int_config(config, key, default, *, clamp=None, warned)`:
   - `isinstance(raw, bool)` rejection FIRST (bool is int subclass).
   - Then `isinstance(raw, int)` branch (NOT int/float — reject floats like 5.7 since this is an int helper).
   - Then string parse via `int(raw)` (NOT `float(raw)` — must exactly match int form).
   - Invalid → `_warn_and_default`.
   - Apply clamp silently (no warning for intentional clamping).
4. Define private `_warn_and_default(key, raw, default, warned)` mirroring 080's pattern.
**Done:** Task 1.4 tests green.
**Depends on:** Task 1.4

### Task 1.6: `_emit_refresh_diagnostic` tests [TDD: red]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_refresh.py`
**Change:** Add `TestEmitRefreshDiagnostic` class:
- `test_emits_one_line_when_debug_enabled` — monkeypatch `refresh.INFLUENCE_DEBUG_LOG_PATH = tmp_path / "log.jsonl"`. Call with full kwargs. Assert file exists with 1 line matching regex `"event":\s*"memory_refresh"` and contains `"elapsed_ms":` field.
- `test_missing_parent_dir_created` — path with missing subdir → file created.
- `test_write_failure_warns_once_then_silent` — path is a directory → first call emits one stderr warning, second call silent, both return None; assert total warning count == 1 via capsys.
**Done:** Tests fail.
**Depends on:** Task 1.5

### Task 1.7: `_emit_refresh_diagnostic` implementation [green]
**File:** `plugins/pd/hooks/lib/semantic_memory/refresh.py`
**Change:** Define `_emit_refresh_diagnostic(*, feature_type_id, completed_phase, query, entry_count, elapsed_ms)`:
- `Path.parent.mkdir(parents=True, exist_ok=True)`
- Build JSON line with `strftime("%Y-%m-%dT%H:%M:%SZ")` + event=memory_refresh + all passed fields
- Append to `INFLUENCE_DEBUG_LOG_PATH`
- Catch `(OSError, IOError)` broadly; use `global _refresh_error_warned` flag; first failure emits stderr warning, subsequent silent.
**Done:** Task 1.6 tests green.
**Depends on:** Task 1.6

### Task 1.8: `_serialize_entries` tests [TDD: red]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_refresh.py`
**Change:** Add `TestSerializeEntries` class:
- `test_exact_three_keys` — AC-6: given an entry dict with many keys (name, category, description, confidence, influence_count, ...), serialized entry has exactly `{"name", "category", "description"}`.
- `test_description_truncated_240_chars` — 500-char description → 240 chars (assert `len(e["description"]) == 240`).
- `test_byte_cap_drops_from_end` — AC-11: 10 entries each with 500-char description → serialized JSON ≤ 2000 bytes; final list may be <10 entries (assert result count); asserts per-entry description ≤ 240 chars.
- `test_empty_input_returns_empty_list` — `[]` → `[]`.
**Done:** Tests fail.
**Depends on:** Task 1.1

### Task 1.9: `_serialize_entries` implementation [green]
**File:** `plugins/pd/hooks/lib/semantic_memory/refresh.py`
**Change:** Define `_serialize_entries(entries: list[dict]) -> list[dict]`:
1. Build list of `{"name": e["name"], "category": e["category"], "description": e["description"][:240]}`.
2. Serialize with `json.dumps(entries, separators=(',', ':'))`.
3. Check UTF-8 byte length via `.encode('utf-8')`.
4. If >2000 bytes: iteratively drop from end until ≤2000 bytes.
5. Return remaining list.
**Done:** Task 1.8 tests green.
**Depends on:** Task 1.8

### Task 1.10a: `hybrid_retrieve` tests [TDD: red]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_refresh.py`
**Change:** Add `TestHybridRetrieve` class with `test_ranking_order_deterministic_with_seeded_provider` covering AC-13: seeded `_FixedSimilarityProvider` (confirmed to exist at `plugins/pd/mcp/test_memory_server.py:1692` — do NOT redefine a second copy) + in-memory MemoryDatabase with K entries; assert returned list has expected ordering by query-similarity.

**Preferred import approach:** Add a fixture to `plugins/pd/mcp/conftest.py` (create if absent) that exports `_FixedSimilarityProvider` for cross-test-file use. Then `from conftest import ...` works regardless of invocation cwd.

**Fallback (if conftest path is awkward):** Use an absolute-path sys.path insert via `Path(__file__).resolve().parents[4] / 'plugins' / 'pd' / 'mcp'` (NOT the relative `"plugins/pd/mcp"` form which fails when pytest runs from a subdirectory).
**Done:** Test fails with AttributeError (hybrid_retrieve not defined).
**Depends on:** Task 1.5

### Task 1.10b: `hybrid_retrieve` implementation [green]
**File:** `plugins/pd/hooks/lib/semantic_memory/refresh.py`
**Change:** Define `hybrid_retrieve(db, provider, config, query, limit) -> list[dict]`:
- `pipeline = RetrievalPipeline(db, provider, config)`
- `result = pipeline.retrieve(query, project=None)`
- `all_entries = db.get_all_entries()`
- `entries_by_id = {e["id"]: e for e in all_entries}`
- `ranker = RankingEngine(config)`
- `return ranker.rank(result, entries_by_id, limit)`
**Done:** Task 1.10a test green.
**Depends on:** Task 1.10a

## Phase 2: memory_server.py refactor

### Task 2.0: Verify refresh.py importable from memory_server.py's PYTHONPATH
**File:** (verification only)
**Change:** Run `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c "from semantic_memory.refresh import hybrid_retrieve; print('ok')"` — must print `ok`. This validates the exact namespace `memory_server.py` uses for its semantic_memory imports; importing memory_server itself would trigger MCP lifespan side effects and is not a reliable probe.
**Done:** Probe prints `ok`.
**Depends on:** Task 1.10b

### Task 2.1: Characterize pre-refactor behavior — write AC-13 parity test FIRST
**File:** `plugins/pd/hooks/lib/semantic_memory/test_refresh.py`
**Change:** Extend `TestHybridRetrieve` with `test_ac13_parity_hybrid_retrieve_is_deterministic` — call `hybrid_retrieve(db, provider, config, Q, N)` TWICE with identical inputs; assert both returned lists equal each other (structural parity: anyone calling this function gets the same result). This test is characterization before the memory_server refactor lands — if Task 2.2 regresses hybrid_retrieve's behavior, this test catches it. Do NOT call `_process_search_memory` from this test (would require full MCP server context; unnecessary since parity is function-level, not caller-level).
**Done:** Test green against current hybrid_retrieve.
**Depends on:** Task 2.0

### Task 2.2: Refactor `_process_search_memory` to call hybrid_retrieve
**File:** `plugins/pd/mcp/memory_server.py`
**Change:** Replace the RetrievalPipeline + RankingEngine construction block inside `_process_search_memory` (around line 311-340) with a single call: `ranked = hybrid_retrieve(db, provider, _config, context_query, limit)`. Import `hybrid_retrieve` at the top of memory_server.py. Preserve all surrounding logic (category filter, response shape, etc.) unchanged.
**Done:** Smoke test passes: `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v -k search_memory` runs green (existing search_memory tests still pass with the refactored body).
**Depends on:** Task 2.1

### Task 2.3: Verify existing memory_server tests pass unchanged + parity still holds
**File:** (verification only)
**Change:** Run:
1. `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v` — assert count ≥ `memory_tests_before_081` and all pass (existing integration-level parity).
2. `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_refresh.py::TestHybridRetrieve -v` — AC-13 parity test from Task 2.1 still green after refactor.
**Done:** Both test runs green.
**Depends on:** Task 2.2

## Phase 3: refresh_memory_digest public entry

### Task 3.1: `refresh_memory_digest` tests [TDD: red]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_refresh.py`
**Change:** Add `TestRefreshMemoryDigest` class:
- `test_ac1_field_shape` — provider + DB + ≥3 medium/high entries matching query → dict with keys `{"query", "count", "entries"}`; each entry has 3 keys.
- `test_ac3_provider_none_returns_none` — provider=None → returns None (NOT empty dict, NOT fallback to BM25).
- `test_ac7_confidence_filter` — DB has 3 entries (low, medium, high), all matching query; limit=10 → response count=2 (only medium + high).
- `test_ac11_byte_cap_end_to_end` — 10 entries each with 500-char description → count ≤ 10 entries with description ≤240 chars and total JSON ≤2000 bytes.
**Done:** Tests fail.
**Depends on:** Task 1.3, 1.5, 1.9, 1.10

### Task 3.2: `refresh_memory_digest` implementation [green]
**File:** `plugins/pd/hooks/lib/semantic_memory/refresh.py`

**Authoritative signature (supersedes design I-1, which predates this task-level decision):**
```python
def refresh_memory_digest(
    db: MemoryDatabase,
    provider: EmbeddingProvider | None,
    query: str,
    limit: int,
    *,
    config: dict,
    feature_type_id: str | None = None,
    completed_phase: str | None = None,
) -> dict | None:
```
The two extra keyword-only params are needed for FR-6 diagnostic emission (both forwarded to `_emit_refresh_diagnostic`). Caller in Task 4.5 passes them through. Design I-1 docstring does not include them — the implementer MUST use this signature.

**Change:** Define `refresh_memory_digest` with the signature above, per design C-1 pseudocode:
1. Start `time.perf_counter()` clock.
2. If provider is None → return None (AC-3 deterministic).
3. `ranked = hybrid_retrieve(db, provider, config, query, limit * REFRESH_OVERSAMPLE_FACTOR)`.
4. Catch any exception → `global _refresh_error_warned`; first failure emits stderr warning; return None.
5. `filtered = [e for e in ranked if e["confidence"] in ("medium", "high")]`.
6. `truncated = filtered[:limit]`.
7. `entries = _serialize_entries(truncated)`.
8. If `not entries`: return None.
9. `elapsed_ms = int((time.perf_counter() - clock_start) * 1000)`.
10. If `elapsed_ms > 500`: `global _slow_refresh_warned`; first-time (flag False), emit this EXACT line (per spec FR-7, asserted verbatim in Task 3.3 regex): `print(f"[workflow-state] memory_refresh took {elapsed_ms}ms (>500ms budget)", file=sys.stderr)`. Then set flag to True. Subsequent calls while flag is True: silent.
11. If `config.get("memory_influence_debug", False)`: call `_emit_refresh_diagnostic(...)` with feature_type_id passed through (see note below), query, entry_count, elapsed_ms.
12. Return `{"query": query, "count": len(entries), "entries": entries}`.

**Done:** Task 3.1 tests pass + AC-1/3/7/11 covered. Additionally: `grep -A2 'def refresh_memory_digest' plugins/pd/hooks/lib/semantic_memory/refresh.py` shows the exact 8-parameter signature defined above.
**Depends on:** Task 3.1

### Task 3.3: AC-10 latency observability test
**File:** `plugins/pd/hooks/lib/semantic_memory/test_refresh.py`
**Change:** Add to `TestRefreshMemoryDigest`:
- `test_ac10_slow_retrieval_warns_once_field_still_present` — monkeypatch `refresh.hybrid_retrieve` with a fake that sleeps 600ms via `time.sleep`. Call `refresh_memory_digest` twice. Assert (a) both calls return a dict (field still present), (b) stderr contains exactly one line matching exact regex `r'\[workflow-state\] memory_refresh took \d+ms \(>500ms budget\)'` (per spec FR-7 mandated prefix + wording), (c) second call emits no additional matching line (cumulative capsys count == 1).

**Note on prefix:** `refresh.py` emits the warning but the spec-mandated prefix is `[workflow-state]` (the MCP subprocess that hosts this call). Task 3.2 must use this exact prefix in its implementation.
**Done:** Test green.
**Depends on:** Task 3.2

## Phase 4: workflow_state_server.py integration

### Task 4.1: Add imports to workflow_state_server.py
**File:** `plugins/pd/mcp/workflow_state_server.py`
**Change:** Add imports at top:
```python
from semantic_memory.database import MemoryDatabase
from semantic_memory.embedding import EmbeddingProvider, create_provider
from semantic_memory.refresh import (
    refresh_memory_digest, build_refresh_query,
    _resolve_int_config, _refresh_warned_fields,
)
```
Verify no circular import warnings.
**Done:** `workflow_state_server.py` imports cleanly.
**Depends on:** Task 3.2

### Task 4.2: Add three module globals to workflow_state_server.py
**File:** `plugins/pd/mcp/workflow_state_server.py`
**Change:** After existing `_db` module global (~line 73), add:
```python
_config: dict = {}
_provider: EmbeddingProvider | None = None
_memory_db: MemoryDatabase | None = None
```
**Done:** Grep: `grep -c '^_config\|^_provider\|^_memory_db' plugins/pd/mcp/workflow_state_server.py` returns 3.
**Depends on:** Task 4.1

### Task 4.3: Extend lifespan to populate globals + close on shutdown (includes failure signal)
**File:** `plugins/pd/mcp/workflow_state_server.py`
**Change:** Inside lifespan context manager (around existing `read_config` call), after `config = read_config(project_root)`:
```python
global _config, _provider, _memory_db
_config = config
try:
    _provider = create_provider(config)
except Exception as e:
    # Visible operator signal — silent failure would leave memory_refresh
    # disabled process-wide with no diagnostic.
    print(f"[workflow-state] memory_refresh disabled for this process: provider init failed: {e}", file=sys.stderr)
try:
    _memory_db = MemoryDatabase(str(Path.home() / ".claude" / "pd" / "memory" / "memory.db"))
except Exception as e:
    print(f"[workflow-state] memory_refresh disabled for this process: memory_db init failed: {e}", file=sys.stderr)
```
In shutdown (yield'd-finally block): `if _memory_db: _memory_db.close()`.
**Done:** `grep -c "global _config, _provider, _memory_db" plugins/pd/mcp/workflow_state_server.py` returns 1 (confirms declaration in lifespan); `grep -c "memory_refresh disabled for this process" plugins/pd/mcp/workflow_state_server.py` returns ≥2 (confirms both stderr warnings). Behavioral verification deferred to Task 4.4/4.6.
**Depends on:** Task 4.2

### Task 4.4: Write integration tests FIRST [TDD: red for 3 ACs]
**File:** `plugins/pd/mcp/test_workflow_state_server.py`
**Change:** Add `TestCompletePhaseMemoryRefresh` class with THREE tests (written before gate implementation):
- `test_ac2_disabled_flag_no_refresh` — Set `memory_refresh_enabled: false`; mock `workflow_state_server.refresh_memory_digest` to raise AssertionError if called; call `complete_phase`; assert response does NOT contain `memory_refresh` key; assert mock call count == 0.
- `test_ac1_enabled_returns_digest` — Enable flag; mock `refresh_memory_digest` to return `{"query": "test q", "count": 2, "entries": [{"name": "A", "category": "patterns", "description": "..."}, {"name": "B", "category": "heuristics", "description": "..."}]}`; call `complete_phase`; assert response contains `memory_refresh` field equal to the mocked dict.
- `test_ac5_limit_clamp_above_max` — Set `memory_refresh_limit: 100`; spy on `refresh_memory_digest` call; assert the `limit` arg passed was 20 (clamped); similarly verify `limit: 0 → 1` and `limit: True → 5` (bool rejection).

**Spy argument indexing:** `refresh_memory_digest` signature is `(db, provider, query, limit, *, config, feature_type_id=None, completed_phase=None)`. When the gate calls it positionally, `limit` is positional index 3. Assert via `mock_refresh.call_args.args[3]` to read the clamped value.

**Config mutation:** Use `monkeypatch.setattr(workflow_state_server, "_config", {"memory_refresh_enabled": ..., "memory_refresh_limit": ...})` — NOT `monkeypatch.setitem`. Lifespan re-assigns `_config = config` which invalidates `setitem` on the original dict; `setattr` replaces the module reference and is safe.
**Done:** All 3 tests are collected by pytest. When executed:
- `test_ac1_enabled_returns_digest` and `test_ac5_limit_clamp_above_max` FAIL (gate not present; response missing `memory_refresh` key; mock not called).
- `test_ac2_disabled_flag_no_refresh` trivially PASSES (no gate means no call, which the test asserts). Kept as a regression guard for the disable path post-Task-4.5.
Both states are valid TDD red for the primary ACs (AC-1, AC-5); AC-2 becomes a regression test.
**Depends on:** Task 4.3

### Task 4.5: Insert 4-part integration gate in _process_complete_phase
**File:** `plugins/pd/mcp/workflow_state_server.py`
**Change:** Per design I-5 (after iter 2 fixes), insert before `return json.dumps(result)`:
```python
# Feature 081: memory refresh digest (additive).
if (
    db is not None
    and _memory_db is not None
    and result.get("last_completed_phase")
    and _config.get("memory_refresh_enabled", True)
):
    query = build_refresh_query(feature_type_id, phase)
    if query:
        limit = _resolve_int_config(
            _config, "memory_refresh_limit", 5,
            clamp=(1, 20), warned=_refresh_warned_fields,
        )
        digest = refresh_memory_digest(
            _memory_db, _provider, query, limit,
            config=_config,
            feature_type_id=feature_type_id,
            completed_phase=phase,
        )
        if digest:
            result["memory_refresh"] = digest
```
**Done:** Task 4.4 test passes.
**Depends on:** Task 4.4, **Task 6.2 (existing tests must be remediated FIRST or they will break mid-phase)**

### Task 4.6: Verify Task 4.4's red tests go green after gate lands [TDD: green]
**File:** (verification only)
**Change:** Run `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py::TestCompletePhaseMemoryRefresh -v`. All 3 tests from Task 4.4 (AC-1, AC-2, AC-5) must pass now that Task 4.5's gate is in place.
**Done:** 3 tests green. Red→green cycle complete for Phase 4's TDD pair.
**Depends on:** Task 4.5

### Task 4.7: (REMOVED — merged into Task 4.3)

The stderr failure signals that were previously in this task are now part of Task 4.3's lifespan implementation. See Task 4.3's code snippet for the `memory_refresh disabled for this process: ...` warning pattern. Removing this task eliminates the retroactive-edit collision between 4.3 and 4.7.

## Phase 5: Config templates + docs sync

### Task 5.1: Append fields to config template
**File:** `plugins/pd/templates/config.local.md`
**Change:** After existing `memory_influence_debug` line from 080, append per spec FR-5:
```yaml
# inject memory digest into complete_phase responses so orchestrator sees fresh
# entries at phase boundaries; disable to revert to session-start-only memory
memory_refresh_enabled: true
# max memory entries in per-phase refresh digest; clamped to [1, 20]; each
# entry description capped at 240 chars
memory_refresh_limit: 5
```
**Done:** `grep -c "^memory_refresh_" plugins/pd/templates/config.local.md` returns 2.
**Depends on:** Task 3.2

### Task 5.2: Append fields to in-repo config
**File:** `.claude/pd.local.md`
**Change:** Append same 2 fields as Task 5.1.
**Done:** `grep -c "^memory_refresh_" .claude/pd.local.md` returns 2.
**Depends on:** Task 3.2

### Task 5.3: Append fields to README_FOR_DEV.md
**File:** `README_FOR_DEV.md`
**Change:** Locate the existing `memory_influence_debug` bullet via `grep -n "memory_influence_debug" README_FOR_DEV.md` (line number may have shifted since 080 shipped — use grep, not hardcoded line). After that line, append:
```
- `memory_refresh_enabled` — Inject memory digest into complete_phase MCP response at phase boundaries (default: true)
- `memory_refresh_limit` — Max entries in per-phase refresh digest (default: 5; clamped to [1, 20])
```
**Done:** `grep -c "memory_refresh_" README_FOR_DEV.md` returns ≥2.
**Depends on:** Task 3.2

### Task 5.4: AC-12 verification
**File:** (verification only)
**Change:** Run:
- `grep -c "^memory_refresh_" .claude/pd.local.md` → 2
- `grep -c "^memory_refresh_" plugins/pd/templates/config.local.md` → 2
- `grep -c "memory_refresh_" README_FOR_DEV.md` → ≥2
**Done:** All three greps return expected counts.
**Depends on:** Task 5.1, 5.2, 5.3

## Phase 6: Existing-test audit + remediation

### Task 6.1: Read audit grep and write impacted-test list to baseline file
**File:** `agent_sandbox/081-baselines.txt` (append)
**Change:** Read the `# audit:` lines populated by Task 0.3. Extract the test function names from the grep output. Append as a single line: `# impacted_tests: test_name_1, test_name_2, ...` in `agent_sandbox/081-baselines.txt`. If the list is empty, append `# impacted_tests: <none>`. Task 6.2 reads this as the definitive list (not a mental note).
**Done:** File contains an `# impacted_tests:` line with comma-separated names.
**Depends on:** Task 0.3

### Task 6.2: Remediate each impacted test BEFORE gate goes live (Task 4.5)
**File:** `plugins/pd/mcp/test_workflow_state_server.py`
**Change:** Read the `# impacted_tests:` line from `agent_sandbox/081-baselines.txt`. For each listed test:
- If test uses `response == {exact_dict}`: either (a) change to `assert response_json.keys() >= {expected_keys}` + per-key asserts, OR (b) set `memory_refresh_enabled: false` in the test's config via `monkeypatch.setitem(workflow_state_server._config, "memory_refresh_enabled", False)`.
- Document choice briefly (one-line comment per test if non-obvious).

**Critical sequencing:** This task MUST complete before Task 4.5 (gate insertion). Without remediation first, Task 4.5 enables the `memory_refresh` field and existing exact-dict equality tests fail mid-Phase-4.
**Done:** Each previously-passing test still passes; `pytest plugins/pd/mcp/test_workflow_state_server.py -v` is green as a pre-check for Task 4.5 gate landing.
**Depends on:** Task 6.1, Task 4.4 (tests exist so we know the response shape); **BLOCKS Task 4.5**.

### Task 6.3: AC-9 verification (after Phase 4 integration)
**File:** (verification only)
**Change:** After Phase 4 complete, run `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v`. Confirm pass count ≥ `workflow_state_tests_before_081 + 3_new_081_tests` (3 from Task 4.4).
**Done:** All green.
**Depends on:** Task 4.6 (all Phase 4 complete; Task 4.7 was merged into Task 4.3)

## Phase 7: Final verification

### Task 7.1: Full test suite (memory + MCP + ranking + refresh)
**File:** (verification only)
**Change:** `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ -v 2>&1 | tail -5`. Count passing tests.
**Done:** Pass count ≥ sum of baselines + new 081 tests; 0 failures; no skips beyond pre-existing.
**Depends on:** Task 6.3, Task 5.4

### Task 7.2: Hook integration tests
**File:** (verification only)
**Change:** `bash plugins/pd/hooks/tests/test-hooks.sh`.
**Done:** 101/101 passed (or ≥ baseline; note any skips).
**Depends on:** Task 7.1

### Task 7.3: validate.sh warning count ≤ baseline
**File:** (verification only)
**Change:** `./validate.sh 2>&1 | tail -5`. Extract warning count. Compare against `validate_warnings_before_081`.
**Done:** 0 errors AND warnings ≤ baseline.
**Depends on:** Task 7.1

### Task 7.4: Delete temp baseline file (ONLY on full Phase 7 success)
**File:** `agent_sandbox/081-baselines.txt` (delete)
**Change:** **Guard:** Only run if Tasks 7.1, 7.2, AND 7.3 all passed. On any failure, keep `agent_sandbox/081-baselines.txt` for debugging (do NOT commit it — already in agent_sandbox which is gitignored). Command: `rm agent_sandbox/081-baselines.txt`.
**Done:** On success path: file no longer exists. On failure path: file retained; Task 7.4 is skipped; operator investigates with baseline available.
**Depends on:** Task 7.1, 7.2, 7.3 (all green)
