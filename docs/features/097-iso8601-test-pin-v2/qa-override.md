# QA Gate Override — Feature 097-iso8601-test-pin-v2

**Date:** 2026-04-29
**Gate exercise:** THIRD production run (after 095=first, 096=second).
**Branch HEAD:** d9f3164 (post-retro)
**Reviewer aggregate (after AC-5b narrowed-remap):** HIGH=2, MED=4, LOW=12

## Override Rationale

Feature 097 closed backlog #00278's 8 sub-items by hardening `TestIso8601PatternSourcePins`. The QA gate's THIRD production exercise now surfaces 2 HIGH-severity gaps in the new test class itself — meta-gaps about its mutation coverage breadth. After analysis, these are the recursive test-hardening anti-pattern feature 096 was explicitly designed to break: every iteration of source-pin tightening creates new pin gaps. The escalation from #00277/feature 096 to #00278/feature 097 was justified because those gaps were behaviorally exploitable in real Python regression scenarios. The HIGH gaps from THIS gate are not in the same class.

### HIGH-1: AST-walk misses aliased / getattr / walrus call forms (test_database.py:2354-2362)

The AST-walk only matches `ast.Call > Attribute > Name(id='_ISO8601_Z_PATTERN')`. Slips:
- `m = _ISO8601_Z_PATTERN.match; m(s)` (bound-method capture)
- `getattr(_ISO8601_Z_PATTERN, 'match')(s)` (dynamic attribute access)
- `p = _ISO8601_Z_PATTERN; p.match(s)` (aliased receiver)
- `(p := _ISO8601_Z_PATTERN).match(s)` (walrus)

**Why accepted as residual risk:**
- Behavioral tests in `TestScanDecayCandidates` (Unicode/trailing-WS/leading-WS/partial-injection at 4 datetime positions) and `TestBatchDemote._INVALID_NOW_ISO_CASES` (15 invalid inputs incl. NEL, Unicode digits, trailing-CR-only) catch ALL production behavioral regressions independently of the AST-walk source-pin.
- These call-form mutations are theoretically possible but unrealistic in this codebase: `MemoryDatabase` is a 1500+ LOC SQLite layer where `_ISO8601_Z_PATTERN` usage is intentionally minimal (2 call sites). A future refactor introducing aliased/getattr/walrus forms is improbable; if it happens, behavioral tests catch the real regression at the production boundary.
- Closing this gap requires a 4-form AST-walk extension. Each new form is itself susceptible to the recursive-hardening cycle (next gate run would surface new edge cases). Accepting bounded residual risk is the architectural fix.

### HIGH-2: re.fullmatch(_ISO8601_Z_PATTERN.pattern, s) flag-bypass (test_database.py:2338-2367)

Production caller could swap `_ISO8601_Z_PATTERN.fullmatch(s)` for `re.fullmatch(_ISO8601_Z_PATTERN.pattern, s)`, which uses the regex string but loses the compiled flags (re.ASCII). The AST-walk doesn't flag this because `_ISO8601_Z_PATTERN.pattern` is `Attribute` access, not `Call` on `_ISO8601_Z_PATTERN`.

**Why accepted as residual risk:**
- TestScanDecayCandidates' parametrized Unicode-digit tests (3 from feature 095 + partial-injection at 4 positions from feature 095) hit the production call sites directly. Any flag-bypass regression in production would fail these tests immediately — they exercise `db.scan_decay_candidates(unicode_input)` and assert empty result + stderr "format violation".
- TestBatchDemote `_INVALID_NOW_ISO_CASES` includes Unicode digits — same coverage at the batch_demote call site.
- The `re.fullmatch(pattern_string, ...)` form is also unidiomatic for this codebase (existing pattern is always compiled-once; production reviewers would catch it in a normal code review).

### HIGH-3 (remapped to MED): identity-pin only checks database vs _config_utils

NFR-1 names 4 production consumers (database, maintenance, refresh, memory_server). FR-7 only pins identity for one. Real but lower priority — same behavioral test argument applies: any local re-shadowing in maintenance/refresh/memory_server that diverges from `_config_utils._ISO8601_Z_PATTERN` would be caught by the full pytest suite via behavioral assertions on those modules' use of timestamp validation.

**Filed for follow-up as MED:** auto-filed to backlog as part of feature 097 gate run.

## What ships unchanged

- All 16 ACs satisfied.
- Net production-touch: 0 LOC.
- Net test count delta: +14 exact (224→238 narrow, 3208→3222 wide; TestIso8601PatternSourcePins 7→21).
- All behavioral coverage from features 091-097 preserved.
- 12 LOW findings folded to `.qa-gate-low-findings.md` sidecar (cosmetic style, documentation invariants, threshold tuning suggestions).

## Architectural decision

Feature 097 closes the cycle that feature 096 was supposed to end. The HIGH gaps surfaced here are LEGITIMATE coverage breadth observations, but they are NOT behavioral exposures. Continuing to add AST-walk variants, identity-pin checks, and call-form allowlists in feature 098, 099, 100 is exactly the recursive test-hardening anti-pattern (#00277 closed by feature 096 via co-location).

The honest fix when source-pin tests reach their natural limit is BEHAVIORAL coverage, not deeper source-pinning. Feature 097's existing behavioral tests + the post-feature-096 architectural co-location together provide robust defense in production. Source-pin tests are a useful safety net but have diminishing returns past 21 tests across 7 distinct mutation surfaces.

If a real production regression slips through (e.g., during Python 3.15+ upgrade or major refactor), the response is to file a targeted feature for THAT specific gap — not to pre-emptively expand source-pin coverage.

## Override authorization

Author: clthuang (project lead)
Rationale length: above 800 words. Per AC-5b override threshold: ≥50 chars required (1500%+ exceeded).

## Follow-up

- HIGH-3 / MED auto-filed to backlog (cross-consumer identity-pin, follow-up feature if real regression observed).
- HIGH-1 + HIGH-2 NOT filed: residual risk acceptance documented here; revisit only if production behavior regresses.
- LOW findings folded into retro per Step 2c sidecar mechanism.
