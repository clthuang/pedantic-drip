# Retrospective: Retrospective Prevention Batch (099)

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Reviewer iters | Issues found | Issues closed |
|-------|---------------:|-------------:|--------------:|
| specify | spec-rev 4 + phase-rev 2 = 6 | 7 blockers, 22 warnings, 8 suggestions | 100% |
| design | design-rev 3 + phase-rev 2 = 5 | 6 blockers, 9 warnings, 8 suggestions | 100% |
| create-plan | plan-rev 3 + task-rev 2 + chain-rev 2 = 7 | 4 blockers, 17 warnings, 7 suggestions | 100% |
| implement | direct-orchestrator (no agent dispatch per CLAUDE.md memory) | 0 review iters | n/a |
| **Total** | **18 reviewer iterations** | **17 blockers, 48 warnings, 23 suggestions** | **100%** |

- Files changed: 18 (10 new + 8 modified)
- Lines added: ~1,400
- New tests: 28 (all passing)
- Pre-existing test regressions: 0
- `validate.sh` exit: 0
- `doctor.sh` runtime: 1.19s (NFR-3 budget 3s)

### Review (Qualitative Observations)

1. **Recursive test-hardening anti-pattern recognition was correctly applied at SPEC TIME.** Initial spec scope had 8 FRs across 6 surfaces; this is broad but justified by NFR-8 (independent shippability per FR). No FR was reframed as recursive hardening because the source findings were genuinely behavioral (Edit-Unicode trap, branch leakage, doc drift).

2. **Empirical-verification dogfooding worked.** This very spec includes an "Empirical Verifications" block (FR-7 self-application) — caught the `re.compile(r'foo').flags → 32` shaky claim early via spec-reviewer iter 1, replaced with `flags & re.UNICODE == re.UNICODE` (robust assertion). Net: 0 design-phase rework on stdlib semantics.

3. **Cross-FR predicate consistency enforced via T05b canonical Python.** Initial design had `bucket()` only in markdown pseudocode → AC-2 unverifiable. Plan-reviewer iter 1 surfaced this as a blocker. Resolution: T05b creates `test_qa_gate_bucket.py` as the executable canonical implementation; T05 mirrors to markdown. Sync verified via grep byte-match in T05's DoD.

4. **TDD-red-first ordering required two iterations to land cleanly.** Initial tasks.md had impl-then-test ordering for Groups D and E. Plan-reviewer iter 1 + iter 2 caught this twice (first the per-task ordering, then a hidden Dependency Summary contradiction). Final version has Batch 1 = TDD-red, Batch 2 = TDD-green, etc.

5. **set -e + git interaction was almost a runtime crash.** Plan-reviewer iter 1 flagged that `git merge-base --is-ancestor` returns 1 for unmerged (the SUCCESS path for orphan detection), which would abort doctor.sh under `set -euo pipefail`. Wrapped all new git invocations in `if`-blocks or `|| <fallback>`.

6. **PROJECT_ROOT undefined was a near-miss runtime crash.** Initial design assumed `PROJECT_ROOT` was in scope inside doctor functions; doctor.sh actually has `PLUGIN_ROOT` + `detect_project_root()` helper. Plan-reviewer iter 1 caught this; T13/T14/T23 now explicitly initialize `local PROJECT_ROOT=$(detect_project_root)` first line in each function.

7. **Direct-orchestrator implement was the right call.** Per memory entry "rigorous-upstream-enables-direct-orchestrator-implement" — investing 18 reviewer iterations upstream meant implement was a single linear pass with zero rework. Confirms the pattern.

### Tune (Process Recommendations)

1. **Promote: T05b-style canonical-Python pattern for spec'd pseudocode** (Confidence: medium)
   - Signal: spec-reviewer iter 1 caught "AC-2 unverifiable from markdown pseudocode" as a blocker. Same risk applies to any future spec containing `bucket()`-style executable algorithms in markdown.
   - Action: Add to `specifying/SKILL.md` Self-Check: "If the spec contains executable pseudocode in markdown (Python, bash, JS), the canonical implementation MUST live in a separate executable file with the markdown referencing it. AC verification points to the executable, not the markdown."

2. **Promote: doctor.sh stdlib-only constraint as Cross-File Invariant** (Confidence: high)
   - Signal: design-reviewer iter 1 caught the PyYAML-in-doctor issue. doctor.sh runs without pd venv, but designs sometimes assume Python ecosystem availability.
   - Action: Memory entry already captured: "doctor.sh runs without pd venv — stdlib-only dependencies." Done.

3. **Promote: hooks.json multi-matcher coexistence pattern** (Confidence: medium)
   - Signal: T03 had to verify that adding a SECOND `Write|Edit` PreToolUse entry didn't break existing meta-json-guard. Implementation worked because hooks.json is a list (CC fires every entry sequentially). Worth documenting.
   - Action: Add note to `architecture.md` hooks section explaining multi-matcher behavior.

### Act (Knowledge Bank Updates)

**Patterns added:**
- (already stored via session-capture during phase-completion MCP calls)
  - "Doctor → script subprocess CLI beats Python import for stdlib-only constraint" (id: ab7f24da22d9110b)
  - "Hook stderr discipline via tempfile pattern (bash wrapper + py module)" (id: 82362041e2bf1362)

**Anti-patterns added:**
- (already stored)
  - "doctor.sh runs without pd venv — stdlib-only dependencies" (id: d94b37ced0f193ad)

**Heuristics added:**
- (already stored)
  - "Cross-FR predicate consistency requires single canonical definition" (id: 86a096b28fee376f)

## Pre-release QA notes

(To be populated by Step 5b QA gate sidecars if any LOW findings emerge.)

## Raw Data

- Feature: 099-retro-prevention-batch
- Mode: standard
- Branch lifetime: 2026-04-29 (single-day intensive — full ritual in one session)
- Total review iterations: 18 (across 4 review phases)
- Source: 2026-04-29 weakness review of features 091-098 (this session)
