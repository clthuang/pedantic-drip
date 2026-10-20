---
last-invoked: 2026-04-16
feature: 080-influence-wiring
---

# Plan: Influence Tuning + Diagnostics

## Implementation Order

```
Phase 1: Shared helpers + test fixture (_resolve_float_config, _resolve_weight, autouse reset)
    ↓
Phase 2: memory_server.py wiring (threshold resolution + diagnostics in wrapper)
    ↓
Phase 3: ranking.py wiring (_influence_weight attribute + _prominence coefficient)    [PARALLEL with Phase 2 after Phase 1]
    ↓
Phase 4: Config templates + in-repo config + README_FOR_DEV.md sync
    ↓
Phase 5: 14-caller migration (mechanical) + verification gates
```

Phase 2 and Phase 3 can run in parallel after Phase 1 lands the shared helper pattern — they touch different files (mcp/memory_server.py vs hooks/lib/semantic_memory/ranking.py) and have no shared state at runtime.

## Phase 1: Helpers + Test Fixture (C-4)

**Why:** `_resolve_float_config` and `_resolve_weight` are depended on by both C-1 (threshold) and C-2 (weight). The autouse test fixture is depended on by every AC-10 test. TDD: red tests first, green helper implementations next.
**Why this order:** Zero external dependencies; both Phase 2 and Phase 3 consume these helpers.
**Complexity:** Low

### Task-level breakdown (see tasks.md):
- Task 1.1: `_resolve_float_config` tests in `plugins/pd/mcp/test_memory_server.py` (TDD red — 5 cases: float passthrough, int passthrough, string parse, bool rejection, invalid string)
- Task 1.2: `_resolve_float_config` implementation in memory_server.py (green) + module-level `_warned_fields`, `_influence_debug_write_failed`, `INFLUENCE_DEBUG_LOG_PATH` declarations grouped after `_project_root`
- Task 1.3: autouse reset fixture added to test_memory_server.py resetting `_warned_fields`, `_influence_debug_write_failed`, `_config` via monkeypatch.setattr
- Task 1.4: `_resolve_weight` tests in `plugins/pd/hooks/lib/semantic_memory/test_ranking.py` (TDD red — 4 cases: float/int/bool/clamp)
- Task 1.5: `_resolve_weight` implementation in ranking.py (green) + module-level `_ranker_warned_fields`
- Task 1.6: autouse reset fixture in test_ranking.py resetting `_ranker_warned_fields`

**Done when:** Tests for both helpers green; `_warned_fields` dedup works across repeated calls; bool rejection verified.

## Phase 2: memory_server.py wiring (C-1 + C-3)

**Why:** Expose threshold from config + emit diagnostics from wrapper. Depends on Phase 1 helper.
**Why this order:** Runs parallel to Phase 3 after Phase 1.
**Complexity:** Medium (touches both helper signature and MCP wrapper)

### Task-level breakdown:
- Task 2.1: Tests for AC-1 (threshold config-driven, TDD red). Test `_process_record_influence_by_content` directly with `_config["memory_influence_threshold"]` at 0.80 vs 0.55, synthetic similarity 0.75.
- Task 2.2: Change helper signature `threshold: float = 0.70` → `threshold: float | None = None`; add resolution block at top of helper; keep clamp (green).
- Task 2.3: Change wrapper signature `threshold: float = 0.70` → `threshold: float | None = None` (no behavior change in wrapper yet).
- Task 2.4: Tests for AC-4/AC-5 (diagnostics emit/silent, TDD red). Monkeypatch `INFLUENCE_DEBUG_LOG_PATH` to tmp_path. Assert file contents.
- Task 2.5: `_emit_influence_diagnostic` helper in memory_server.py (I-4) — strftime Z-format, IOError guard with `_influence_debug_write_failed`.
- Task 2.6: Integrate diagnostic emission into wrapper per I-2b — json.loads parse, re-resolve threshold, clamp-parity, call _emit_influence_diagnostic. Gate on `_config.get("memory_influence_debug", False)`.
- Task 2.7: Tests for AC-10 (a, c, d, e) — non-float threshold warning, missing log dir, write failure, bool rejection.
- Task 2.8: Test for AC-6 (lowered default takes effect when threshold=None).

**Done when:** AC-1, AC-4, AC-5, AC-6, AC-10(a,c,d,e) tests all green. `record_influence_by_content` MCP tool signature changed; external behavior unchanged when callers pass explicit threshold.

## Phase 3: ranking.py wiring (C-2)

**Why:** Extract hardcoded `0.05 * influence` coefficient to config-driven `self._influence_weight`.
**Why this order:** Parallel with Phase 2 after Phase 1.
**Complexity:** Low

### Task-level breakdown:
- Task 3.1: Tests for AC-2 (weight config-driven, TDD red) in test_ranking.py. Instantiate `RankingEngine` with `config = {"memory_influence_weight": 0.30}`. Call `_prominence` on entry with influence_count=10 vs 0; assert gap ≥0.29.
- Task 3.2: Test for AC-3 (regression — config field absent means byte-identical `_prominence` output). Existing tests should pass unchanged; this is a meta-assertion.
- Task 3.3: Add `self._influence_weight = _resolve_weight(config, "memory_influence_weight", 0.05, warned=_ranker_warned_fields)` to `RankingEngine.__init__` at line ~35 (next to existing _prominence_weight).
- Task 3.4: Replace line 252 last term: `0.05 * influence` → `self._influence_weight * influence`.
- Task 3.5: Test for AC-10(b) — `memory_influence_weight: 2.5` → clamped to 1.0 silently (no warning).

**Done when:** AC-2, AC-3, AC-10(b) green.

## Phase 4: Config templates + docs sync (C-6 + FR-6)

**Why:** Make the 3 new config fields accessible to users and documented in the canonical table.
**Why this order:** Field names are fixed by spec FR-4 — no code dependency. Can run in parallel with Phase 2 and Phase 3 after Phase 1 lands (Phase 1 is not strictly required either, but running after it keeps mental ordering clean). **Downgraded from strict sequential to parallel-eligible.** AC-11 grep in Phase 5 catches any accidental typos.
**Complexity:** Low (pure docs/config edits)

### Task-level breakdown:
- Task 4.1: Append 3 fields to `plugins/pd/templates/config.local.md` with comments per FR-4.
- Task 4.2: Append same 3 fields to `.claude/pd.local.md` (repo config), with `memory_influence_debug: true` for baseline collection.
- Task 4.3: Append 3 bullet entries to `README_FOR_DEV.md` after line 527 (after `memory_promote_min_observations`).
- Task 4.4: Verification grep — AC-11: `grep -c "memory_influence_" README_FOR_DEV.md` returns exactly 3.

**Done when:** All three config fields present in all three files with consistent naming and documented defaults; AC-11 grep passes.

## Phase 5: 14-caller migration + final verification (C-5 + AC-7/AC-7b)

**Why:** Remove `threshold=0.70` from 14 call sites so the new default takes effect in production. Final verification gates.
**Why this order:** Last — depends on Phase 2 signature being stable.
**Complexity:** Low (mechanical)

### Task-level breakdown:
- Task 5.1: Migrate 2 call sites in `plugins/pd/commands/specify.md` per C-5 canonical form (multi-line).
- Task 5.2: Migrate 2 call sites in `plugins/pd/commands/design.md`.
- Task 5.3: Migrate 3 call sites in `plugins/pd/commands/create-plan.md`.
- Task 5.4: Migrate 7 call sites in `plugins/pd/commands/implement.md`.
- Task 5.5: AC-7 grep: `grep -rn "threshold=0.70" plugins/pd/commands/*.md | wc -l` → 0.
- Task 5.6: AC-7b typo-catch grep: `grep -rEn "threshold=0\.[0-9]" plugins/pd/commands/*.md | wc -l` → 0.
- Task 5.7: Full verification — run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ plugins/pd/mcp/test_memory_server.py -v`; run `./validate.sh`. Both must be green.

**Done when:** All 14 call sites migrated; AC-7, AC-7b, AC-11 grep gates pass; full test suite green; validate.sh 0 errors.

## Risks (carried from design.md R-1..R-5)

- **R-1 14-caller miss** — mitigated by AC-7 + AC-7b inverse greps.
- **R-2 config.py blast radius** — mitigated by design TD-3 + FR-5 "point of consumption" explicit.
- **R-3 mkdir race** — mitigated by `exist_ok=True`.
- **R-4 disk full** — mitigated by FR-3 try/except IOError + one-shot flag.
- **R-5 baseline measurement skipped** — operator discipline, retro template flag.

## Dependencies

- Phase 1 blocks Phase 2 and Phase 3.
- Phase 2 and Phase 3 can run in parallel.
- Phase 4 depends on final field names from Phase 2 + Phase 3.
- Phase 5 depends on Phase 2's wrapper signature change (callers pass nothing instead of `threshold=0.70`).

## Total scope estimate

- **~150 LOC** across memory_server.py, ranking.py, test_memory_server.py, test_ranking.py (tests are the majority).
- **14 mechanical edits** in command markdown files.
- **9 lines appended** across templates/config.local.md, .claude/pd.local.md, README_FOR_DEV.md.
- **~12 new test cases** per spec Success Criteria.
