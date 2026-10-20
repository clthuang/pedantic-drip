# Plan: Feature 092 — 091 QA Residual Hotfix

## Status
- Created: 2026-04-20
- Phase: create-plan
- Upstream: spec.md + design.md

## Baseline

`PRE_092_SHA` captured at branch creation. Also record baseline line count: `PRE_092_TEST_HOOKS_LOC=$(wc -l < plugins/pd/hooks/tests/test-hooks.sh)` — AC-9 compares post-092 line count against this baseline.

## Implementation Order

Per design.md Stream decomposition:

| # | Plan Item | Stream | FR(s) | Depends on | Parallelizable |
|---|-----------|--------|-------|------------|----------------|
| PI-1 | FR-1 clamp + docstring | A | FR-1 | none | Yes with PI-2, PI-3, PI-6 |
| PI-2 | FR-5 regex validation + log-and-skip + module-level pattern | A | FR-5 | none | Yes with PI-1, PI-3, PI-6 |
| PI-3 | FR-8 batch_demote empty-now_iso raise (after empty-ids short-circuit) | A | FR-8 | none | Yes with PI-1, PI-2, PI-6 |
| PI-4 | New pytests (AC-1, AC-7, AC-10) | D | FR-1/5/8 tests | PI-1, PI-2, PI-3 | Sequential after PI-1/2/3 land |
| PI-5 | FR-6 spec.md clamp values (feature 091) | C | FR-6 | none | Yes with PI-1..4, PI-6 |
| PI-6 | FR-2/3/4 inline edits to existing AC-22b/c | B | FR-2, FR-3, FR-4 | none | Yes with PI-1..5 |
| PI-7+8 | FR-7 helper extraction (absorbs PI-6 inline edits) + FR-9 PASS echo marker embedded at extraction time | B | FR-7, FR-9 | PI-6 | Atomic co-landing (single commit + single helper body) |
| QG | Quality gates: pytest + test-hooks.sh + validate.sh | all | NFR-2/3 | all PIs | Sequential |
| V1 | AC verification (grep + test execution) | all | all ACs | all PIs | Sequential |

**Note (per phase-reviewer suggestion):** FR-2/3/4 are atomic edits made inline to the existing AC-22b/c blocks first; FR-7 then extracts the shared helper incorporating those changes; FR-9 is the echo-marker addition INSIDE the helper. Do not create separate tasks for FR-9 post-FR-7 — they co-land.

## Dependency Graph

```
PI-1 (FR-1) ──┐
PI-2 (FR-5) ──┼──▶ PI-4 (AC-1/7/10 pytests)
PI-3 (FR-8) ──┘
PI-5 (FR-6 docs) ─────────── independent
PI-6 (FR-2/3/4 inline) ──▶ PI-7 (FR-7 helper) ──▶ PI-8 (FR-9 marker)
                                                        │
                                All ────────────────────┼──▶ QG ──▶ V1
                                                        ▼
                                         Post-merge: AC-12 adversarial QA
```

## TDD Ordering

All code changes follow RED→GREEN:

| PI | RED | GREEN |
|----|-----|-------|
| PI-1 (FR-1) | AC-1 pytest (scan_decay_candidates(scan_limit=-1) returns []) — FAILS before clamp | Clamp added; AC-1 passes |
| PI-2 (FR-5) | AC-7 pytest (malformed cutoff → empty + stderr warning) — FAILS before validation | Regex + log-and-skip; AC-7 passes |
| PI-3 (FR-8) | AC-10 pytest (ids+empty_now_iso → ValueError; empty_ids → 0) — FAILS before validation | Validation added; AC-10 passes |
| PI-6 | Existing AC-22b/c tests continue to pass | Inline edits for FR-2/3/4 preserve behavior |
| PI-7 | AC-9 (helper exists; line-count reduced) — PI-6's inline tests still pass post-extraction | Helper replaces duplicated scaffold |
| PI-8 | AC-11 grep `AC-22b PASS: shell guard` = 1 — FAILS before marker | Echo marker added inside helper; AC-11 passes |

## AC Coverage Matrix

All 11 functional ACs + structural AC-12 mapped:

| AC | Plan Item(s) | Verification |
|----|--------------|--------------|
| AC-1 (#00193 clamp + pytest) | PI-1, PI-4 | grep + pytest |
| AC-2 (#00193 docstring correction) | PI-1 | grep for new docstring text |
| AC-3 (#00194 trap pattern + absence-grep) | PI-6, PI-7 | two greps: `≥1` new pattern + `=0` old pattern |
| AC-4 (#00194 mktemp triple guard) | PI-6, PI-7 | three conjunctive greps |
| AC-5 (#00195 AC-4d git -C + manual fire-test) | PI-6, PI-7+8 | grep (automated) + manual fire-test (run once during PI-7+8 landing; record result in implementation-log.md per TD-7) |
| AC-6 (#00196 cp -R -P) | PI-6, PI-7 | `grep cp -R -P ≥1` + `grep 'cp -R "' = 0` |
| AC-7 (#00197 regex + iso_utc pin) | PI-2, PI-4 | grep + pytest |
| AC-8 (#00198 spec clamp values) | PI-5 | grep |
| AC-9 (#00199 helper + LOC reduction) | PI-7 | grep `_run_maintenance_fault_test ≥3` + `wc -l` comparison |
| AC-10 (#00200 batch_demote guards) | PI-3, PI-4 | 2 pytests |
| AC-11 (#00201 PASS markers) | PI-8 | grep test-hooks.sh output |
| AC-12 (structural post-merge QA) | post-merge | 4-reviewer adversarial dispatch |

## Technical Decisions (from design)

TD-1 clamp-not-raise (FR-1), TD-2 log-and-skip (FR-5), TD-3 raise-but-preserve-empty-ids (FR-8; asymmetry grounded in read-vs-write semantics), TD-4 `set +e` NOT `set -e` NOR `set -u` in FR-7 helper, TD-5 single-quoted trap body, TD-6 helper parametrization, TD-7 manual AC-5 fire-test.

## Quality Gates

Before `complete_phase`:

1. **Q1 pytest:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_maintenance.py plugins/pd/hooks/lib/semantic_memory/test_database.py -v` → 0 failed
2. **Q2 test-hooks.sh:** `bash plugins/pd/hooks/tests/test-hooks.sh` → 0 failures; `AC-22b PASS:` + `AC-22c PASS:` lines present
3. **Q3 validate.sh:** `./validate.sh` exit 0
4. **Q4 pd:doctor:** Invoke `/pd:doctor` skill (or check entity registry consistency + orphaned worktrees manually if skill unavailable). Pass = no critical failures; warnings acceptable.

After merge:

5. **Q5 (post-merge, structural exit gate per NFR-5 / AC-12):** Dispatch 4 parallel adversarial reviewers in one message: `pd:security-reviewer` (opus), `pd:code-quality-reviewer` (sonnet), `pd:test-deepener` Phase A (opus), `pd:implementation-reviewer` (opus). Each reviews the merged 092 diff. Pass criterion: ≤ 3 MED findings TOTAL across all 4 reviewers AND zero HIGH findings. Decider: feature author. If a new HIGH surfaces → file new backlog entry; do NOT expand feature scope retroactively.

## Risk Mitigations (from design)

R-1..R-7 carried forward. Plan-level mitigations:
- R-2 (helper SPOF): two different test function call sites fail both loudly on helper bugs
- R-4 (structural exit gate): post-merge 4-reviewer dispatch mandatory; not skippable
- R-7 (`set +e` setup-failure surfacing): explicit `|| { echo FAIL; exit 1; }` on every setup step

## Out of Scope

- Pre-release adversarial QA gate (PRD Open Q #1) — separate backlog entry
- 15 LOW findings #00202-#00216

## Next Steps

1. Task breakdown (tasks.md) — atomic Simple/Medium tasks with binary DoDs
2. Combined reviewer loop (plan + task + phase)
3. Relevance gate
4. `/pd:implement` → direct-orchestrator execution
