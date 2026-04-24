# Retrospective — Feature 093 (092 QA Residual Hotfix)

## Status
- Completed: 2026-04-24
- Branch: `feature/093-092-qa-residual-hotfix`
- Target release: v4.16.2

## Scope delivered (3 findings → 1 unified fix)

All three 092 post-release QA findings closed via one regex change + symmetric call-site application:

| FR | Item | Shipped |
|----|------|---------|
| FR-1 | #00219 HIGH: `\d` accepts Unicode digits | Pattern `[0-9]{...}...Z` + `re.ASCII` |
| FR-2 | #00220 MED: `$` anchor allows trailing `\n` | `.match()` → `.fullmatch()` |
| FR-3 | #00221 MED: `not now_iso` catches empty only | Symmetric `_ISO8601_Z_PATTERN.fullmatch(now_iso)` in `batch_demote` |
| FR-4 | (advisor: format-drift pin) | Parametrized test across 5 datetime boundaries |
| FR-5 | (acceptance testing) | 3 new parametrized test methods + TD-3 regression guard |
| FR-6 | (#00226 from 092 LOW co-landed) | `{!r:.80}` bounded repr in both error paths |

## AORTA analysis

### A — Accomplishments
1. **Single root cause surfaced and fixed once.** 3 findings (1 HIGH + 2 MED) reduced to "FR-5/FR-8 asymmetric shallow validation" and closed with one pattern edit + one symmetric call-site addition.
2. **Format-drift pin installed** (FR-4): parametrized test across year 0001, year 9999, microsecond=999999, leap year, canonical. Future `_iso_utc` refactor that breaks the pattern will fail loudly.
3. **Direct-orchestrator first-pass implement** — third consecutive feature (091, 092, 093) to pass implement review on first try. Pattern holds: tight upstream → zero implement iterations.
4. **Symmetry invariant enforced** via single `_ISO8601_Z_PATTERN` constant used by BOTH read (log-and-skip) and write (raise) call sites. AC-5 grep pins this: exactly 1 `re.compile` line.

### O — Observations
1. **Existing tests using `+00:00`-suffix `NOW_ISO` broke under the hardened pattern** — updated in the same commit. Three `TestBatchDemote*` classes had their class-level `NOW_ISO = "2026-04-16T12:00:00+00:00"` which would fail `fullmatch()`. Caught in first pytest run; fixed by flipping to `Z` suffix.
2. **`datetime` import missing at module level** — FR-4 parametrize decorator evaluated `datetime(...)` at class-definition time, but `datetime` was only imported inline in the function body. Caught in first pytest run; fixed by hoisting import to top of file.
3. **Advisor consensus produced better decisions than any single advisor** — pre-mortem flagged the format-drift risk; antifragility flagged the tight-coupling risk the fix introduces. Together: both demanded the parametrized test as a non-negotiable gate. Neither alone would have caught the full picture.
4. **Spec-reviewer caught a weak AC-5 shadow-pattern check** — my original regex searched for the literal string `YYYY` or `ISO` in comments. Spec-reviewer pointed out a second pattern without those tokens would bypass the check. Fixed in spec iteration but not a blocker.

### R — Root causes (for the 092 residuals this fixed)
1. **FR-5/FR-8 asymmetry in 092 design.** 092 correctly identified read-vs-write semantics (TD-3) but over-applied it: read path got format validation, write path got emptiness check. The correct interpretation: *asymmetry in behavior* (log-and-skip vs raise), not *asymmetry in validation depth*.
2. **Python 3 `\d` Unicode semantics (#00219)** is a stdlib footgun documented but easy to miss. Even with explicit spec review, "looks like digits" passes casual inspection. The fix (`[0-9]`) is a well-known defensive idiom in regex-heavy Python codebases; the miss is one of awareness, not design skill.
3. **`$` vs `\Z` vs `fullmatch()` (#00220)** is similar — Python's `$` has a well-documented asymmetry with POSIX/PCRE. `fullmatch()` (Python 3.4+) exists precisely to avoid this footgun. The 092 spec used `.match()` out of habit.

### T — Tasks (action items)
1. **[MED]** File new backlog entry: canonical validation helper `validate_iso8601_z(x) -> bool` in `_config_utils.py` (co-located with `_iso_utc`). Currently `_ISO8601_Z_PATTERN` lives in `database.py` per Open Q #1 decision — but if other modules ever need the same validation, move to `_config_utils.py` to eliminate the import-direction coupling problem.
2. **[LOW]** Consider a hookify rule that flags `re.compile(r'.*\\d.*')` in `plugins/pd/hooks/lib/`: any `\d` in an ISO-format regex should trigger a review prompt. Turns the specific 092 miss into a proactive gate.

### A — Actions
- 3 backlog items (#00219, #00220, #00221) closed with `feature:093` markers.
- 1 LOW item (#00226 bounded repr) co-landed in same commit.
- Knowledge bank: reinforce "fail-loud format-drift pins for any format-parsing regex" pattern.

## Metrics
- **Reviewer dispatches:** ~4 across all phases (tightest surgical ever — PRD 2 iter, spec 1 iter, implement 0 iter)
- **LOC:** +60 prod/test net (pattern edits + new parametrized tests)
- **New pytests:** 18 parametrized assertions (280/280 passes, was 262/262)
- **Quality gates:** all green first try

## What went well
- Root-cause unification framing upfront saved 3× the reviewer cycles. One fix, not three.
- Parametrize-as-primary test strategy produces dense coverage (18 assertions across 4 test methods).
- Advisor consensus on `[0-9]` + `re.ASCII` + `fullmatch` (belt AND suspenders) — nobody proposed a minimal fix because each advisor independently saw the others' blind spots.

## What could improve
- `datetime` import issue cost one pytest cycle — should have caught in spec review by reading parametrize decorator semantics more carefully.
- Existing `NOW_ISO = "+00:00"` in 3 test classes should have been flagged in spec pre-checks (grep for `+00:00` in test files).

## References
- PRD: `docs/brainstorms/20260424-111837-092-qa-residual-hotfix.prd.md`
- Feature: `docs/features/093-092-qa-residual-hotfix/`
- Source: backlog #00219 (HIGH) + #00220 (MED) + #00221 (MED) from 092 post-release adversarial QA
