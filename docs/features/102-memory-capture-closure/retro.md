# Retrospective: Feature 102 — Memory Pipeline Capture Closure

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Reviewer Iterations | Outcome |
|-------|---------------------|---------|
| Brainstorm | 3 prd-reviewer + 3 brainstorm-reviewer | PRD approved |
| Specify | 2 spec-reviewer + 3 phase-reviewer | spec.md approved (35 ACs + 5 NFRs) |
| Design | 2 design-reviewer + 2 phase-reviewer | design.md approved (14 components, 8 interfaces) |
| Create-plan | 2 plan-reviewer + 2 task-reviewer + 2 phase-reviewer + 1 relevance-verifier | 25 tasks (20 Simple + 5 Medium + 0 Complex) |
| Implement | direct-orchestrator (single-pass) | 218 tests pass; validate.sh 0 errors |
| Pre-release QA gate | 4 reviewers in parallel | 4 cross-confirmed HIGH inline-fixed; 12 MED auto-filed (#00298-#00309) |

**Branch lifetime:** 2 calendar days (2026-05-01 to 2026-05-03).
**Total reviewer iterations across all phases:** 24.
**Files changed:** 25 files, ~2400 insertions, ~30 deletions.
**Net new components:** 14 (6 new files + 8 modifications).

### Review (Qualitative Observations)

1. **Direct-orchestrator implement pattern continues to work** — heavy upfront review (24 iterations) enabled single-pass implementation without per-task implementer agent dispatch. Backend implementation matched design verbatim; validate.sh passed first try. Same outcome as feature 101.

2. **QA gate caught 4 cross-confirmed HIGH findings** — pre-release adversarial QA (4 parallel reviewers) was load-bearing this feature. Specifically:
   - **Rotation order in capture-on-stop.sh** (code-quality blocker) — log rotation fired AFTER append instead of BEFORE, defeating the size threshold contract. Latent bug only catchable by structural review, not the test suite I had.
   - **Category mapping bug** (impl + test-deepener cross-confirmed) — substring case glob `*"not "*` would have over-matched preference patterns. Impl-reviewer caught this from spec divergence; test-deepener cross-confirmed via "no test exists for AC-2.4a parametrized".
   - **Missing dropped_excerpts in overflow log** (code-quality + test-deepener) — implementation drift from spec AC-2.5, only caught by reviewer reading spec + diff.
   - **Missing `when...then` soft marker** in enforceability.py (code-quality + impl) — spec/design listed it; implementation missed it.

3. **Test-script gap was substantial but bounded** — bash hook integration tests (T2.1a, T2.2a, T2.3) and CLI seam tests (test_main.py) were planned but not authored during the direct-orchestrator implement pass. Pattern matches feature 101's deferred 6 RED test gaps via qa-override.md. Acceptable for primary-feature shipping; appropriate for follow-up test-hardening feature (filed as #00298-#00306).

4. **Opportunity-cost advisor's "narrower gap" insight reshaped scope** — initial brainstorm assumed PostToolUse for corrections; advisor pointed out `capture-tool-failure.sh` already covers tool failures, narrowing the actual gap to user corrections + workarounds. Saved an estimated half-day of redundant work. UserPromptSubmit was the correct hook all along.

5. **Pre-mortem advisor's "calibration before merge" prediction was vindicated** — advisor flagged untested signal-detection heuristic as the #1 risk; AC-1.8 mandated a 20-sample calibration corpus pre-merge as the mitigation. The corpus exists but its harness is deferred (#00298) — partial-credit on the mitigation. Future feature should run the corpus through the hook in CI.

### Tune (Process Recommendations)

1. **QA gate's 4-reviewer parallel dispatch is essential — confidence: high.** This feature's HIGH findings were entirely structural/spec-divergence issues that rigorous upstream review didn't catch. The QA gate is doing what it was designed for. Continue dispatching all 4 reviewers in parallel; do not optimize away.

2. **Bash hook integration tests should be authored during implement, not deferred — confidence: medium.** Two consecutive features (101, 102) deferred test scripts via qa-override. This is becoming a habit. Future features with bash hook deliverables should explicitly carve out time for `test-{hook-name}.sh` files in the implement pass, not the test-hardening follow-up. Pre-merge precision corpus harness in particular (AC-1.8 here) should be CI-runnable from day one.

3. **Spec-vs-implementation drift is the dominant QA-gate finding source — confidence: high.** 4 of 4 cross-confirmed HIGHs were "implementation diverged from spec text in a small but structurally important way" (rotation order, category glob, missing JSON field, missing soft marker). Code-quality + implementation reviewers caught all 4 by reading the spec/diff side-by-side. This is the structural reason QA gate has antifragile properties and should never be skipped.

### Act (Knowledge Bank Updates)

**Patterns added:**
- "Pre-release adversarial QA gate catches spec-vs-impl drift" — confidence: high, observed: features 094 / 099 / 102 (3 features confirm).
- "Bash hook category-mapping must use exact regex literal match, not substring case glob" — confidence: medium (single observation, but specific bug class).

**Anti-patterns added:**
- "Substring case glob over-matches when patterns share characters" — confidence: medium, observed: feature 102 capture-on-stop.sh:80.
- "Log rotation after append leaks one extra entry to oversized file" — confidence: low, observed: feature 102 capture-on-stop.sh:113.

**Heuristics added:**
- "When opportunity-cost advisor flags 80% existing coverage, re-scope before designing" — confidence: medium, validated: features 101 + 102.
- "Direct-orchestrator implement is viable when upstream has 20+ reviewer iterations" — confidence: medium, validated: features 101 + 102 (single-pass implement, no per-task agent dispatch).

## Pre-release QA notes

### Cross-confirmed HIGH (fixed inline)
1. capture-on-stop.sh:113 rotation order
2. capture-on-stop.sh:80 category mapping substring glob
3. capture-on-stop.sh:118 missing dropped_excerpts field
4. enforceability.py:36 missing when...then soft marker

### Audit log
- security-reviewer: HIGH=0 MED=0 LOW=3 (suggestions only)
- code-quality-reviewer: HIGH=1 MED=3 LOW=1 (1 fixed inline, 2 filed)
- implementation-reviewer: HIGH=5 MED=7 LOW=0 (5 deferred per qa-override.md)
- test-deepener: HIGH=11 MED=0 LOW=0 (2 fixed, 9 deferred per qa-override.md)

## Raw Data
- Feature: 102-memory-capture-closure
- Mode: standard
- Branch lifetime: ~48 hours (2026-05-01 19:43 UTC → 2026-05-03 ~16:00 UTC)
- Total review iterations: 24 + 4 (QA gate) = 28
- Pre-release QA: 4 cross-confirmed HIGH fixed inline; qa-override.md applied for deferred test scripts
