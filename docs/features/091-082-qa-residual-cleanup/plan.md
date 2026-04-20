# Plan: Feature 091 — 082 QA Residual Cleanup

## Status
- Created: 2026-04-20
- Phase: create-plan (started)
- Upstream: `docs/features/091-082-qa-residual-cleanup/spec.md`, `docs/features/091-082-qa-residual-cleanup/design.md`

## Baseline

All file:line references cited below reference the state of `feature/091-082-qa-residual-cleanup` at branch creation (HEAD: `0e9369a` at plan creation time). Captured as PRE_091_SHA for AC verification:

```bash
PRE_091_SHA=$(git rev-parse HEAD)  # Run once at start of implementation; pin in task outputs
```

## Implementation Order

Ordered from lowest risk / docs-only to higher-risk / code changes. Stream letters match design.md:

| # | Plan Item | Stream | FR | Depends on | Parallelizable |
|---|-----------|--------|----|----|----------------|
| PI-1 | Backlog hygiene — 23 closure markers | D | FR-1 | none | Runs first, serial — reviewer-bandwidth isolation |
| PI-2 | `_execute_chunk` dead SQL branch | B | FR-5 | PI-1 | With PI-3, PI-4, PI-6, PI-7 |
| PI-3 | Equal-threshold warning predicate | A | FR-2 | PI-1 | With PI-2, PI-4, PI-6, PI-7 |
| PI-4 | `MemoryDatabase.scan_decay_candidates` method | B | FR-4 | PI-1 | With PI-2, PI-3, PI-6, PI-7 |
| PI-5 | `_select_candidates` caller swap | B | FR-4 | PI-4 AND PI-6 | Sequential after PI-4 + PI-6 |
| PI-6 | `TestSelectCandidates` isoformat → _iso swap | C | FR-6 | PI-1 | With PI-2, PI-3, PI-4, PI-7 |
| PI-7 | `test-hooks.sh` AC-22b/c blocks | C | FR-3 | PI-1 | With PI-2, PI-3, PI-4, PI-6 |

**Critical dependencies:**
1. PI-5 (caller swap) requires PI-4 (new method on disk) AND PI-6 (TestSelectCandidates in post-isoformat-swap state) — the latter so any AC-7d regression signal is attributable to the caller swap, not to isoformat drift.
2. All code-change PIs depend on PI-1 landing first (docs-only commit frees reviewer bandwidth; enforces single-purpose commits per TD-6).

## Dependency Graph

```
                ┌─ PI-1 (docs)  ─┐
                ├─ PI-2 (SQL)   ─┤
                ├─ PI-3 (pred)  ─┤
                ├─ PI-4 (method)─┼─ PI-5 (caller) ─┐
                ├─ PI-6 (iso)   ─┤                 │
                └─ PI-7 (hook)  ─┘                 │
                                                   │
                              [all complete] ──────┴──▶ validate + tests + commit
```

## Parallel Group Structure

- **Group Alpha-docs (serial, first):** PI-1 — docs-only, lands first so reviewer can focus subsequent bandwidth on code commits.
- **Group Alpha-code (parallel, up to 5, after PI-1):** PI-2, PI-3, PI-4, PI-6, PI-7 — independent code/test changes.
- **Group Beta (sequential after PI-4 + PI-6):** PI-5 — requires PI-4 (method on disk) AND PI-6 (TestSelectCandidates post-isoformat-swap baseline for attributable regression).
- **Final validation (after all):** full test suite + validate.sh + pd:doctor + AC verification.

Given max_concurrent_agents=5, Group Alpha-code dispatches 5 in parallel after PI-1 completes; Group Beta follows. Single implementer dispatch is also viable given scope (~250 LOC production + 200 LOC tests).

## TDD Ordering (per plan item)

All code changes follow RED → GREEN → REFACTOR per `pd:implementing-with-tdd`:

| Plan Item | Test First | Then Code |
|-----------|-----------|-----------|
| PI-1 | AC-1 per-ID loop script (verify 23 markers + 4 open IDs present) | Apply markers per FR-1 mapping table |
| PI-2 | Regression test confirms `batch_demote` still works (existing tests) | Edit SQL; re-run regression |
| PI-3 | New tests `test_equal_threshold_emits_warning` + `test_strictly_less_threshold_still_emits_warning` (both FAIL before change, PASS after) | Flip `<` → `<=`; update warning text |
| PI-4 | New tests `test_scan_decay_candidates_respects_scan_limit` + `test_scan_decay_candidates_includes_null_last_recalled_at` + `test_scan_decay_candidates_returns_iterator` (FAIL — method doesn't exist) | Add method; tests PASS |
| PI-5 | Existing `TestSelectCandidates` regression tests PASS before and after (no new test needed; the regression is the pin) | Swap `db._conn.execute` → `yield from db.scan_decay_candidates(...)` |
| PI-6 | Before edit: `TestSelectCandidates.test_partitions_six_entries_across_all_buckets` PASSES (isoformat). After edit: same test PASSES (Z-suffix) — behavior unchanged | Swap isoformat → _iso; add AC-9c canonical format assertion |
| PI-7 | AC-22b and AC-22c new blocks — with test-hooks.sh existing structure as template | Add the two new test blocks per design I-5 |

## Technical Decision References

All TDs from design.md are load-bearing during implementation. Key references:

- **TD-1 (generator semantics):** `yield from db.scan_decay_candidates(...)` in PI-5.
- **TD-2 (SQL verbatim):** PI-4 must reproduce 5-line SQL byte-for-byte per I-1.
- **TD-3 (scan_limit validation):** no validation added in PI-4; callers responsible.
- **TD-4 (`<=` semantics):** PI-3 emits warning on `med == high` case.
- **TD-5 (temp-PYTHONPATH subshell):** PI-7 harness in subshells only; production file never mutated.
- **TD-6 (git strategy):** PI-1 as single `chore(091): add closure markers...` commit. Each other PI in its own commit.

## Acceptance Criteria Coverage

All 11 spec ACs map to plan items:

| AC | Plan Item(s) | Verification |
|----|--------------|--------------|
| AC-1 (exact markers) | PI-1 | Shell loop over 23-row FR-1 mapping table |
| AC-1b (validate.sh) | PI-1 | `./validate.sh` post-edit |
| AC-1c (per-ID presence) | PI-1 | Shell loop over 27 IDs |
| AC-2 (`<=` predicate) | PI-3 | `grep -cE "if med_days <= high_days"` = 1 |
| AC-2b (no `<`) | PI-3 | `grep -cE "if med_days < high_days"` = 0 |
| AC-3 / AC-3b (warning tests) | PI-3 | pytest |
| AC-4a / AC-4b / AC-4c / AC-4d | PI-7 | bash test-hooks.sh |
| AC-5 / AC-5b (method + SQL pin) | PI-4 | grep + Python normalize |
| AC-6 (no `_conn`) | PI-5 | `grep -c "db._conn" maintenance.py` = 0 |
| AC-7 / AC-7b / AC-7c / AC-7d | PI-4 + PI-5 | pytest |
| AC-8 (no dead branch) | PI-2 | `grep -c "updated_at IS NULL" database.py` = 0 |
| AC-8b (regression) | PI-2 | existing test suite |
| AC-9 / AC-9b / AC-9c | PI-6 | awk+grep + pytest |
| AC-10 / AC-PA-1 / AC-PA-2 | Post-merge | `/pd:finish-feature` retro step |
| AC-11 (structural exit) | Implement phase Stage 5 | adversarial reviewer output |

## Quality Gates

After all PIs complete, before `complete_phase`:

1. **Full test suite:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_maintenance.py plugins/pd/hooks/lib/semantic_memory/test_database.py -v`
2. **Shell tests:** `bash plugins/pd/hooks/tests/test-hooks.sh`
3. **Validation:** `./validate.sh`
4. **Diagnostics:** `pd:doctor` health check

All 4 gates must pass. If any fails, return to the relevant PI and fix before declaring complete.

## Risk Summary (from design.md)

All 6 risks from design carry forward. Plan-level mitigations:

- **R-1 (FR-2 perturbs existing `<` tests):** AC-3b parallel test pins `<` case. Full test suite run in Quality Gates.
- **R-2 (FR-4 signature cascades):** PI-5 preserves `_select_candidates` signature (grace_cutoff kept).
- **R-3 (FR-6 latent bugs):** PI-6 TDD confirms before/after behavior unchanged.
- **R-4 (structural exit gate AC-11):** All PIs produce test pins covering mutation cases.
- **R-5 (sed portability):** RESOLVED in design — PI-7 uses echo+cat prepend.
- **R-6 (Iterator import):** PI-4 adds `from collections.abc import Iterator`.

## Out of Scope

Same as spec and design. Not revisited.

## Next Steps

1. Task breakdown (tasks.md) — each PI decomposed into atomic Simple/Medium tasks with binary DoDs.
2. Combined reviewer loop (plan-reviewer, task-reviewer, phase-reviewer) max 5 iterations.
3. Relevance gate pre-implementation.
4. `/pd:implement` dispatch.
