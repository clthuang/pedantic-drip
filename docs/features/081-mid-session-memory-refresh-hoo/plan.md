---
last-invoked: 2026-04-16
feature: 081-mid-session-memory-refresh-hoo
---

# Plan: Orchestrator Mid-Session Memory Refresh

## Implementation Order

```
Phase 0: Baselines (warning count, test count, impacted-test audit)
    ↓
Phase 1: refresh.py shared module (helpers + module globals + fixture)
    ↓
Phase 2: memory_server.py refactor (parity test first, THEN refactor)
    ↓
Phase 3: refresh_memory_digest public entry (ties helpers together)
    ↓
Phase 4a: imports + globals + lifespan (Tasks 4.1-4.3; lifespan failures emit stderr per Task 4.7)
    ↓
Phase 4b: write integration tests (Task 4.4 — TDD red for AC-1/2/5)
    ↓
Phase 6: audit + remediate existing tests (Tasks 6.1-6.2) — MUST complete before gate lands
    ↓
Phase 4c: gate insertion (Task 4.5) + verify tests go green (Task 4.6) + stderr signals (Task 4.7)
    ↓
Phase 5: Config templates + docs sync                                 [PARALLEL with Phase 4 after Phase 3]
    ↓
Phase 6 (continued): Task 6.3 AC-9 regression verification (full test_workflow_state_server.py run)
    ↓
Phase 7: Final verification (full test suite, validate.sh, test-hooks.sh)
```

**Critical sequencing:** Phase 6 remediation (Task 6.2) interleaves between Task 4.4 (red tests) and Task 4.5 (gate insertion). Without this ordering, enabling the gate with `memory_refresh_enabled: true` default would break existing tests that assert exact-dict equality on `complete_phase` responses (R-6 risk mitigation).

**Parallelism:** Phase 5 (docs/config edits) can still run parallel with Phase 4b onward — field names are spec-fixed; docs don't depend on wiring. Phase 6 depends on Task 4.4 (tests exist so the shape is observable) not on Phase 4c.

## Phase 0: Baselines (Design Phase Gate 1 + 7)

**Why:** Capture pre-change state so Phase 7 can verify no regression. Also enumerates the specific tests needing audit per R-6.
**Why this order:** Zero external dependencies; must run before any edit.
**Complexity:** Low

### Task-level breakdown:
- Task 0.1: Capture `validate.sh` warning count → `agent_sandbox/081-baselines.txt` as `validate_warnings_before_081=N`.
- Task 0.2: Capture existing test counts → same file: `memory_tests_before_081=N`, `workflow_state_tests_before_081=M`, `ranking_tests_before_081=K`.
- Task 0.3: Existing-test audit grep → `grep -n 'complete_phase\|last_completed_phase' plugins/pd/mcp/test_workflow_state_server.py` (result appended to baselines file as comment). Phase 6 tasks read this list.

**Done when:** `agent_sandbox/081-baselines.txt` exists with all four values + audit grep output.

## Phase 1: refresh.py shared module (C-1)

**Why:** All helpers for 081 live here. Must land before Phases 2/3/4 which import from it. TDD per helper: red test → green impl.
**Why this order:** Dependency root. Every downstream phase imports from `refresh.py`.
**Complexity:** Medium (7 helpers + fixture + constants; each individually trivial).

### Task-level breakdown:
- Task 1.1: `test_refresh.py` scaffold + autouse reset fixture (TDD enabler). Fixture resets `_slow_refresh_warned`, `_refresh_error_warned`, `_refresh_warned_fields` via `monkeypatch.setattr`.
- Task 1.2: `build_refresh_query` tests [TDD: red] — AC-4a/b/c/d.
- Task 1.3: `build_refresh_query` implementation [green] — `_FEATURE_SLUG_RE`, `_NEXT_PHASE` dict per design I-2.
- Task 1.4: `_resolve_int_config` tests [TDD: red] — AC-5 variants (clamp, bool reject, invalid string, dedup).
- Task 1.5: `_resolve_int_config` implementation + module globals [green] — `_refresh_warned_fields: set[str]`, `REFRESH_OVERSAMPLE_FACTOR = 3` constant, `INFLUENCE_DEBUG_LOG_PATH` duplicate.
- Task 1.6: `_emit_refresh_diagnostic` tests [TDD: red] — AC-8 (log line format, monkeypatch `refresh.INFLUENCE_DEBUG_LOG_PATH`).
- Task 1.7: `_emit_refresh_diagnostic` + `_slow_refresh_warned` + `_refresh_error_warned` module globals + implementation [green].
- Task 1.8: `_serialize_entries` tests [TDD: red] — AC-6 (exact 3-key shape), AC-11 (byte cap + drop-from-end).
- Task 1.9: `_serialize_entries` implementation [green] — 240-char truncation + UTF-8 byte cap with compact JSON separators.
- Task 1.10: `hybrid_retrieve` implementation + unit test — lifted signature from design TD-1 (`db, provider, config, query, limit`). Test uses seeded `_FixedSimilarityProvider` + in-memory `MemoryDatabase`.

**Done when:** All `refresh.py` helper tests green; module imports cleanly; `_FEATURE_SLUG_RE.match("feature:081-...")` returns expected match.

## Phase 2: memory_server.py refactor to call hybrid_retrieve (TD-1 revised)

**Why:** Per design TD-1, `_process_search_memory` must call the extracted `hybrid_retrieve` so parity with refresh is structural. Small surgical edit.
**Why this order:** Depends on Phase 1 (hybrid_retrieve exists). Blocks Phase 3 (AC-13 parity test requires this).
**Complexity:** Low (one function body swap + existing search_memory tests must pass unchanged).

### Task-level breakdown:
- Task 2.1: Refactor `_process_search_memory` (memory_server.py lines 311-340 equivalent) to call `hybrid_retrieve(db, provider, _config, query, limit)`. Remove inline RetrievalPipeline + RankingEngine construction.
- Task 2.2: Run existing `plugins/pd/mcp/test_memory_server.py` — must pass unchanged. This is AC-13 at the integration level.
- Task 2.3: Add AC-13 unit test to `test_refresh.py::TestHybridRetrieve` — seeded `_FixedSimilarityProvider`, assert deterministic ordering. Verifies parity at the function level.

**Done when:** Existing memory_server tests green unchanged; test_refresh.py::TestHybridRetrieve covers AC-13.

## Phase 3: refresh_memory_digest public entry (C-1 public surface)

**Why:** Main public function combining hybrid_retrieve + confidence filter + serialize. Depends on all Phase 1 helpers + Phase 2 hybrid_retrieve.
**Why this order:** Last helper in refresh.py; consumed by workflow_state_server in Phase 4.
**Complexity:** Low (pseudocode is already in design C-1).

### Task-level breakdown:
- Task 3.1: `refresh_memory_digest` tests [TDD: red] — AC-1 (shape), AC-3 (provider=None → None deterministically), AC-7 (confidence filter), AC-11 (byte cap end-to-end).
- Task 3.2: `refresh_memory_digest` implementation [green] — per design C-1 pseudocode (provider-None early-return, hybrid_retrieve, filter, truncate, serialize).
- Task 3.3: AC-10 latency test — monkeypatch hybrid_retrieve to sleep 600ms via fake; assert (a) field still present, (b) one stderr warning, (c) second call silent (dedup via `_slow_refresh_warned`).

**Done when:** refresh_memory_digest tests pass including AC-1/3/7/10/11.

## Phase 4: workflow_state_server.py integration (C-2 + C-3)

**Why:** The actual injection point. Depends on Phase 3 (refresh_memory_digest available).
**Why this order:** Parallel with Phase 5 (docs). Precedes Phase 6 (test remediation) because integration tests in Phase 6 exercise this code path.
**Complexity:** Medium (module globals + lifespan + gate + imports + integration tests).

### Task-level breakdown:
- Task 4.1: Add imports to `workflow_state_server.py` top: `MemoryDatabase`, `EmbeddingProvider`, `create_provider`, `refresh_memory_digest`, `build_refresh_query`, `_resolve_int_config`, `_refresh_warned_fields` (imported by reference per design warning).
- Task 4.2: Add three module globals: `_config: dict = {}`, `_provider: EmbeddingProvider | None = None`, `_memory_db: MemoryDatabase | None = None`.
- Task 4.3: Extend lifespan to populate all three. Wrap `create_provider(config)` and `MemoryDatabase(...)` in try/except. Close `_memory_db` on shutdown.
- Task 4.4: Add AC-2 test (disabled flag) — `test_workflow_state_server.py::TestCompletePhaseMemoryRefresh::test_disabled_flag_no_call`. Mock `refresh_memory_digest`; assert call count 0; `memory_refresh` absent from response.
- Task 4.5: Insert integration gate in `_process_complete_phase` per design I-5 (4-part gate: db + _memory_db + last_completed_phase + enabled). Wire call to `refresh_memory_digest`, attach field.
- Task 4.6: Add AC-1 integration test — enabled flag, mocked `refresh_memory_digest` returning fixture digest; assert response contains `memory_refresh` with expected shape.
- Task 4.7: AC-5 test (limit clamping at integration layer) — verifies `_resolve_int_config` wiring in the gate.

**Done when:** Integration tests pass; workflow_state_server imports cleanly; lifespan opens and closes MemoryDatabase without error.

## Phase 5: Config templates + docs sync (C-4)

**Why:** User-visible surface. Field names are fixed by spec FR-5 so no code dependency.
**Why this order:** Parallel-eligible after Phase 3; completed before Phase 7 verification.
**Complexity:** Low (pure text edits).

### Task-level breakdown:
- Task 5.1: Append 2 fields to `plugins/pd/templates/config.local.md` with exact comments per design C-4 / spec FR-5.
- Task 5.2: Append same 2 fields to `.claude/pd.local.md` (repo config). No special debug-collection value — plain defaults (enabled: true, limit: 5).
- Task 5.3: Append 2 bullet lines to `README_FOR_DEV.md` memory config table (after line 530 `memory_influence_debug` from 080).
- Task 5.4: AC-12 verification grep — three greps with expected counts (2, 2, ≥2).

**Done when:** All three files contain the 2 new fields; AC-12 greps pass.

## Phase 6: Existing-test audit + remediation (R-6 mitigation)

**Why:** Per design Phase Gate 1, existing `complete_phase` tests may break from the new `memory_refresh` field. Phase 0 audit enumerated them; this phase updates them.
**Why this order:** Must follow Phase 4 (integration code lands) and precede Phase 7 (final verification).
**Complexity:** Low (mechanical per-test updates).

### Task-level breakdown:
- Task 6.1: Read `agent_sandbox/081-baselines.txt` audit output → list of impacted test names.
- Task 6.2: For each impacted test (expected count: 5-15), apply remediation per design R-6:
  - Option (a) — set `memory_refresh_enabled: false` in the test's config (preferred if test is simple).
  - Option (b) — update exact-dict assertion to ignore `memory_refresh` key (preferred if test needs the full response shape).
  - Pick per-test based on readability.
- Task 6.3: Run audited tests to confirm they pass.
- Task 6.4: AC-9 verification — `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v` reports ≥ `workflow_state_tests_before_081` passing tests.

**Done when:** All previously-passing tests still pass; no test was skipped or deleted.

## Phase 7: Final verification

**Why:** Ship gate. Verifies no regression, warning count ≤ baseline, full suite green.
**Why this order:** Last.
**Complexity:** Low (verification-only).

### Task-level breakdown:
- Task 7.1: Run `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ -v`. Must be all green; counts ≥ all Phase 0 baselines plus new tests.
- Task 7.2: Run `bash plugins/pd/hooks/tests/test-hooks.sh`. Must be 101/101 (or ≥ baseline).
- Task 7.3: Run `./validate.sh`. Must be 0 errors; warning count ≤ `validate_warnings_before_081`.
- Task 7.4: Delete `agent_sandbox/081-baselines.txt` (temp file, not committed).

**Done when:** All three gates green; temp baseline file removed.

## Risks (from design)

- **R-1 Provider lifespan failure** — mitigated by deterministic `provider is None → None` early-return + design-level documentation.
- **R-2 MCP cold-start latency** — first phase-transition may trip FR-7 warning (one-shot). Accepted.
- **R-3 INFLUENCE_DEBUG_LOG_PATH drift** — backlog item if it bites.
- **R-4 Orchestrator confusion by refresh content** — mitigated by `memory_refresh_enabled: false` rollback lever.
- **R-5 Token budget edge cases** — deterministic enforcement via FR-4 byte cap + AC-11 coverage.
- **R-6 Existing complete_phase tests** — addressed by Phase 0 audit + Phase 6 remediation.

## Deliverables Summary

**New files:**
- `plugins/pd/hooks/lib/semantic_memory/refresh.py` — shared helper module.
- `plugins/pd/hooks/lib/semantic_memory/test_refresh.py` — unit tests.
- `agent_sandbox/081-baselines.txt` — temp file, deleted in Task 7.4 on success.

**Edited files:**
- `plugins/pd/mcp/workflow_state_server.py` — imports + 3 module globals + lifespan additions + integration gate in `_process_complete_phase`.
- `plugins/pd/mcp/memory_server.py` — small refactor: `_process_search_memory` body swapped to call `hybrid_retrieve`.
- `plugins/pd/mcp/test_workflow_state_server.py` — new `TestCompletePhaseMemoryRefresh` class + remediation of existing tests per Phase 6 audit.
- `plugins/pd/templates/config.local.md` — 2 new field entries.
- `.claude/pd.local.md` — 2 new field entries.
- `README_FOR_DEV.md` — 2 new memory config table bullets.

**Test delta:**
- New unit tests in `test_refresh.py` covering AC-1, AC-3, AC-4a/b/c/d, AC-5 variants, AC-6, AC-7, AC-8, AC-10, AC-11, AC-13.
- New integration tests in `test_workflow_state_server.py` covering AC-1, AC-2, AC-5 at the MCP response level.
- Remediated existing tests (exact count captured by Phase 0 Task 0.3 audit grep, written to baselines file by Task 6.1).
