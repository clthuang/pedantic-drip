# Retrospective — Feature 091 (082 QA Residual Cleanup)

## Status
- Completed: 2026-04-20
- Branch: `feature/091-082-qa-residual-cleanup`
- Scope delivered: 23 backlog markers + 4 code fixes + 1 investigation finding + 4 new test classes + 2 shell test blocks

## Scope snapshot (what shipped)

| FR | Delivered | Evidence |
|----|-----------|----------|
| FR-1 backlog hygiene | 22 closure + 1 partial marker | `docs/backlog.md` verified via V1 loop |
| FR-2 `<=` warning predicate | predicate + warning text flipped; 2 new tests; test_ac31 capsys drain | `maintenance.py:424` |
| FR-3 AC-22b/c blocks | 2 new `test-hooks.sh` functions using temp-PYTHONPATH subshell harness | `test-hooks.sh:2960-3083` |
| FR-4 `scan_decay_candidates` method | new public method + 4 tests; caller swap preserves `grace_cutoff` | `database.py:953`, `maintenance.py:259-266` |
| FR-5 dead SQL branch | `updated_at IS NULL OR` removed | `database.py:1028` |
| FR-6 isoformat drift | `TestSelectCandidates` uses `_iso()` with AC-9c canonical pin | `test_maintenance.py:400-416` |
| PA-1 (post-merge) | `#00192` filed for isoformat lint opportunity | `docs/backlog.md` |
| PA-2 (post-merge) | `#00076`–`#00079` closed with `feature:091` markers | `docs/backlog.md` |

## Iteration counts (AORTA: Actual-vs-target)

| Phase | Reviewers | Target | Actual | Notes |
|-------|-----------|--------|--------|-------|
| specify | spec-reviewer | ≤ 2 | 4 (3 fail + 1 pass) | Discovered production shell-guard stderr suppression mid-review; rewrote AC-4 approach |
| specify | phase-reviewer | ≤ 2 | 2 (1 fail + 1 pass) | AC-3 regex + AC-9 line-range brittle to drift |
| design | design-reviewer | ≤ 2 | 2 (1 fail + 1 pass) | Blocker caught: `scan_limit` clamp cited as 500k vs actual 10M |
| design | phase-reviewer | ≤ 2 | 2 (1 fail + 1 pass) | Tautology in AC-22b/c harness (|| true swallows assertion) |
| create-plan | plan-reviewer | ≤ 2 | 3 (2 fail + 1 pass) | AC-1c regex bug: `[59]` char class not `[5-9]` range |
| create-plan | task-reviewer | ≤ 2 | 2 (1 fail + 1 pass) | Depends-on mismatch between index and task bodies |
| create-plan | phase-reviewer | ≤ 2 | 3 (2 fail + 1 pass) | V1 `declare -A` bash 4+ incompatibility with macOS bash 3.2 |
| implement | 4-reviewer + final | ≤ 2 | 2 (1 pass with 2 suggestions + 1 final-val pass) | Direct-orchestrator first-pass approval |

**Grand total:** ~20 reviewer dispatches across 4 phases. 3–4 recurring classes of blocker: regex precision (AC-1c, AC-9), portability (bash 3.2, sed BSD/GNU), existing-code-state verification (scan_limit bound, grace_cutoff preservation).

## AORTA analysis

### A — Accomplishments

1. **23 stale backlog items closed with durable markers** — the backlog now reflects real state (22 fixed in 088/089, 1 partial in 088) rather than appearing-open-despite-fixed.
2. **Silent fragility eliminated** — `TestSelectCandidates` no longer uses `.isoformat()` with SQLite lexical comparison, removing the coincidental-pass test path.
3. **Encapsulation violation closed** — `maintenance.py:259` `db._conn.execute` bypass replaced with `MemoryDatabase.scan_decay_candidates()` public method (knowledge-bank HIGH anti-pattern "Direct `db._conn` Access in Reconciliation Code").
4. **AC-22 coverage extended to SyntaxError + ImportError** using temp-PYTHONPATH subshell harness that never mutates the production file (AC-4d invariant).
5. **Structural exit gate honored** — Stage 5 adversarial review produced zero new HIGH findings; all Round 1 issues were MED/LOW.

### O — Observations (surprises / non-obvious)

1. **Production stderr suppression discovered only during spec review** — `session-start.sh:719,735` uses `2>/dev/null || true` as production guard, making stderr-based assertions for AC-22 impossible. Redirected AC-4 to exit-status-only contract. Should have been captured in the design phase or earlier.
2. **`scan_limit` clamp was `(1000, 10_000_000)` not `(1000, 500_000)`** — the spec/design initially cited the wrong bound. Caught in design review iteration 1; not catastrophic because TD-1's "prefer generator" conclusion strengthens under the corrected bound (1.5 GB worst case), but a 20x factual miss in the initial artifacts.
3. **23 items were already fixed, not just 22** — initial PRD undercounted `#00116` as a partial by one. Reconciliation table in spec FR-1 surfaced the correct count.
4. **`awk '/PATTERN/,/PATTERN2/'` range bug is extremely easy to trip** — when the start pattern also matches the end pattern (as happens with Python class lines), the range collapses to one line. Replaced with flag-based form across spec+tasks+V1.
5. **Direct-orchestrator implementation passed first reviewer round with zero issues** — validates the knowledge-bank pattern "rigorous-upstream-enables-direct-orchestrator-implement". Invested heavy iterations upstream (spec + design + plan reviews, ~15 iterations total before implement); collected dividend with 0-issue implement review.

### R — Root causes (for the 3 recurring blocker classes)

1. **Regex precision** — authors write natural-language regex under time pressure (e.g., `0007[59]` as shorthand for "00075 or 00079"); reviewers catch the class-vs-range error only when running the check. **Mitigation idea:** add a hook that runs every AC's grep invocation against the test fixture before spec-review iteration 1.
2. **Portability** — bash 3.2 (macOS system default), BSD vs GNU sed, declare -A absence — test-hooks.sh runs under `/usr/bin/bash`. **Mitigation idea:** document "no bash 4+ features in test-hooks.sh" as a hard constraint in `dev-guide/` or hook-development docs.
3. **Existing-code-state verification gap** — the `scan_limit` clamp miscount and the missed `grace_cutoff` signature preservation both trace to insufficient codebase reading during spec/design. **Mitigation idea:** design-phase codebase-explorer dispatch should include a mandatory signature-capture step for any function/method referenced in the design.

### T — Tasks (action items)

1. **[MED]** Add file `docs/dev_guides/test-hooks-portability.md` documenting bash 3.2 / BSD sed / no `declare -A` constraints. → Out of scope for this feature; file as backlog.
2. **[LOW]** Consider `/pd:finish-feature` retro step scanning for `(fixed in feature:N)` mentions in retro.md and auto-applying markers to `docs/backlog.md`. Would eliminate the stale-backlog class of findings entirely. → Out of scope; file as backlog.
3. **[LOW]** `_config_utils.py` SPOF mitigation (PRD Open Q #2) — antifragility advisor flagged both maintenance and refresh depend on a single module with no fallback. → Out of scope; file as backlog.

### A — Actions

- Knowledge bank updates (see below)
- 4 open 082 backlog items closed with feature:091 markers (PA-2 complete)
- 1 new finding `#00192` filed for isoformat lint opportunity (PA-1 complete)

## Knowledge bank contributions

| Type | Name | Description | Confidence |
|------|------|-------------|------------|
| pattern | "Temp-PYTHONPATH subshell harness for production file fault injection" | When testing production behavior under injected faults (SyntaxError, ImportError), copy the entire Python package to `mktemp -d`, inject the fault there, invoke via `PYTHONPATH=$PKG_TMPDIR`. Subshell-scoped `trap ... EXIT` handles cleanup without disturbing parent script traps. AC-4d invariant (`git status --porcelain` on production file) prevents accidental mutation. | low (single use) |
| pattern | "Ground-truth count reconciliation in scope-bundling features" | When a feature bundles N items from a list, reconcile the count in a Scope section with explicit per-item table — prevents 22-vs-23-vs-24 count mismatches that waste review iterations. | low |
| anti-pattern | "awk range with start/end regex that both match on start line" | `awk '/^class Foo/,/^class [A-Z]/'` collapses to one line when the start pattern also matches the end pattern. Use flag-based form: `awk '/^class Foo:/{flag=1; next} /^class [A-Z]/{flag=0} flag'`. | medium (recurring in 088 and 091) |
| anti-pattern | "Regex char class confused with range" | `0007[59]` is a 2-character class (matches only "5" or "9"), not a range. Use `0007[5-9]`. Recurring in multiple features' AC greps. | low |
| heuristic | "Shell test files constrained to bash 3.2 on macOS" | `test-hooks.sh` runs under `/usr/bin/bash` (3.2 on macOS). No associative arrays, no `mapfile`, no `${var^^}` case conversion. Use portable while-read patterns with process substitution. | medium |
| heuristic | "Existing-code-state verification gate at design phase" | When design references a function/method signature, the designer MUST read the actual signature and pin it verbatim; review checks against real file. Otherwise 20x factual misses (like `scan_limit` clamp) escape to implementation. | low |

## Metrics

- **LOC change:** +187 production (15 new method body + delegation + 1-line predicate + SQL edit -1) + +171 tests + +126 shell test functions + -5 isoformat + 23 markdown lines. Under NFR-1 budget (≤ +250 prod, ≤ +200 tests).
- **Commits on branch:** 12 (T1 single-marker chore, T2–T7b code, quality gates, 2 suggestion-fix commits)
- **Reviewer dispatches:** ~20 total across all phases
- **Wall time (approximate):** ~2 hours of autonomous execution

## What went well

- Spec-level verbatim SQL pinning (TD-2) eliminated the entire class of "semantic SQL divergence" concerns in implement review — zero issues raised about the new method's SQL correctness.
- The temp-PYTHONPATH subshell harness is reusable for any future fault-injection test; significantly better than the legacy rename-and-trap pattern in AC-22.
- Direct-orchestrator implementation (first-pass approval) validated the upstream-investment-pays-off pattern.

## What could improve

- Spec-review iterations 1 and 2 could have combined the "fix regex + fix stderr + fix SQL pin" into a single iteration if a pre-review codebase verification script had caught the assumptions upfront.
- Some reviewer feedback cycles felt repetitive (e.g., "mapping count mismatch" surfaced in plan-review after being fixed in spec-review) — reviewers should read the latest state, not cached prior iterations.

## References

- PRD: `docs/brainstorms/20260420-145644-082-qa-residual-hotfix.prd.md`
- Spec/Design/Plan/Tasks: `docs/features/091-082-qa-residual-cleanup/*.md`
- Review history: `docs/features/091-082-qa-residual-cleanup/.review-history.md`
- Implementation log: `docs/features/091-082-qa-residual-cleanup/implementation-log.md`
