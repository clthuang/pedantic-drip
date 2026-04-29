# PRD: Test-Hardening Sweep for `_ISO8601_Z_PATTERN` Mutation-Resistance Gaps

*Source: Backlog #00246*

## Status
- Created: 2026-04-29
- Last updated: 2026-04-29
- Status: Draft
- Problem Type: Product/Feature
- Archetype: fixing-something-broken

## Problem Statement

Feature 093 shipped `_ISO8601_Z_PATTERN = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', re.ASCII)` with belt-and-suspenders defense (`[0-9]` literal AND `re.ASCII` flag). The 18 parametrized behavior tests added in feature 093 all pass under FOUR distinct mutation classes:

1. Swap `[0-9]` → `\d` (`re.ASCII + \d` is behaviorally equivalent to `[0-9] + re.ASCII`)
2. Drop `re.ASCII` flag (`[0-9]` is ASCII-only by spec, behavior unchanged)
3. Swap to `\d` AND drop `re.ASCII` (re-introduces #00219 Unicode-digit bypass — this IS caught by behavior tests via `test_pattern_rejects_unicode_digits`)
4. Single-call-site `.fullmatch()` → `.match()` revert at `batch_demote` only (caught at `scan_decay_candidates` by trailing-WS tests, NOT at `batch_demote` due to missing trailing-space + CRLF parametrize cases)

Mutation classes (1) and (2) each silently weaken defense-in-depth without any behavior test catching them. Mutation class (4) silently weakens one of the two call sites. 7 HIGH source-level mutation-resistance gaps unpinned (#00246-#00252).

### Evidence
- **plugins/pd/hooks/lib/semantic_memory/database.py:23-26** — current `_ISO8601_Z_PATTERN` source — Evidence: file:line
- **docs/backlog.md #00246-#00252** — 7 HIGH gaps from feature 093 post-release adversarial QA — Evidence: file
- **plugins/pd/mcp/test_workflow_state_server.py:1851-1857** — existing `inspect.getsource()` source-pin precedent (asserts literal token presence in handler bodies) — Evidence: file:line
- **plugins/pd/hooks/lib/entity_registry/test_backfill.py:2073-2084** — module-scope `inspect.getsource()` exclusion-grep precedent — Evidence: file:line
- **plugins/pd/hooks/lib/semantic_memory/test_database.py:2025-2122** — current parametrized tests for ISO8601 pattern (`TestScanDecayCandidates`, `TestBatchDemote`) — Evidence: file:line

## Goals
1. Close all 7 HIGH source-level mutation-resistance gaps via new tests.
2. Prefer **stable public attribute assertions** (`pattern.pattern`, `pattern.flags & re.ASCII`) over `inspect.getsource()` text-grep where the same signal is available — first-principles + antifragility advisors converged on this.
3. Use `inspect.getsource()` ONLY where call-site call-form is the actual contract (e.g., AC-50 `.fullmatch()` source pin must be at call site, not at the pattern definition).
4. Keep test-only scope: zero production code changes in `database.py`.

## Success Criteria
- [ ] 7 new test methods (or extensions of existing parametrize lists) added to `plugins/pd/hooks/lib/semantic_memory/test_database.py`
- [ ] New test class `TestIso8601PatternSourcePins` for source-level pins (mirroring existing class-naming convention)
- [ ] Pin tests use `_ISO8601_Z_PATTERN.pattern` / `_ISO8601_Z_PATTERN.flags & re.ASCII` for #00246 (literal) + #00247 (flag) + #00248 (direct Unicode rejection) — NOT `inspect.getsource()` for these (per antifragility recommendation: stable public attrs since Python 3.7)
- [ ] Pin tests use `inspect.getsource(MemoryDatabase.scan_decay_candidates)` + `inspect.getsource(MemoryDatabase.batch_demote)` for #00250 (call-site `.fullmatch()` source-pin) — required because the contract is "call site uses `.fullmatch()` not `.match()`"
- [ ] Pattern-identity test for #00249 (assert both call-site sources reference the literal token `_ISO8601_Z_PATTERN.fullmatch(`, NOT a local `re.compile(`)
- [ ] Cross-call-site rejection parity for #00251 — extend existing `test_batch_demote_rejects_invalid_now_iso` parametrize with trailing-space + trailing-CRLF cases
- [ ] Mixed ASCII+Unicode partial-injection #00252 — 4 parametrized cases (Unicode digit at day / hour / minute / second positions) at BOTH call sites
- [ ] Existing pytest baseline (280/280 PASS at feature 093 close) becomes 295-305/295-305 PASS — no regressions; 15-25 net new parametrized assertions per NFR-1
- [ ] Per-section `ids=[...]` argument added to new parametrize blocks (per feature 094 retro suggestion #00243)
- [ ] Wall-clock implementation: <30 min in direct-orchestrator pattern
- [ ] **First production exercise of feature 094's pre-release QA gate** — `/pd:finish-feature` Step 5b dispatches 4 reviewers in parallel pre-merge; closes AC-9/11/13/19 deferred verification from feature 094 retro
- [ ] **Pre-merge empirical verification of feature 094 gate test-file scope** — during T6 dogfood, inspect the diff passed to reviewers and confirm `tests/` files appear; document in retro.md "Manual Verification" section. Closes Open Question 1 with empirical evidence rather than spec-citation alone

## User Stories

### Story 1: Future maintainer refactors the regex
**As a** future contributor (or me, 6 months from now)  
**I want** any refactor that swaps `[0-9]` → `\d` OR drops `re.ASCII` to fail at least one test loudly  
**So that** the silent-defense-weakening failure mode flagged in feature 093 retro is structurally impossible

**Acceptance:** mutate `database.py:24` to `r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z'` (keep flag), run pytest → at least `test_pattern_source_uses_explicit_digit_class` fails. Mutate to drop `re.ASCII` (keep `[0-9]`), run → `test_pattern_compiled_with_re_ascii_flag` fails.

### Story 2: Future call-site refactor reverts to `.match()`
**As a** maintainer  
**I want** any single-site revert from `.fullmatch()` to `.match()` to fail a test  
**So that** the asymmetric trailing-newline bypass (#00220) cannot regress at one call site silently

**Acceptance:** mutate `database.py:1068` (batch_demote) to `_ISO8601_Z_PATTERN.match(now_iso)` → at least `test_call_sites_use_fullmatch_not_match` fails. Same for line 1001.

## Use Cases

### UC-1: Direct pattern-object pin
**Actors:** test runner | **Preconditions:** `_ISO8601_Z_PATTERN` importable from `semantic_memory.database`  
**Flow:** import constant → assert `'[0-9]' in pattern.pattern` AND `'\\d' not in pattern.pattern` → assert `bool(pattern.flags & re.ASCII)` is True → assert `pattern.fullmatch('２０２６-04-20T00:00:00Z') is None`  
**Postconditions:** mutation classes 1 + 2 + (1+2) all caught

### UC-2: Call-site source pin
**Actors:** test runner | **Preconditions:** `MemoryDatabase` class accessible  
**Flow:** `inspect.getsource(MemoryDatabase.scan_decay_candidates)` → assert `'_ISO8601_Z_PATTERN.fullmatch(' in src AND '_ISO8601_Z_PATTERN.match(' not in src AND 're.compile(' not in src` → repeat for `batch_demote`  
**Postconditions:** mutation class 4 caught at both call sites

### UC-3: Cross-call-site rejection parity
**Actors:** test runner | **Preconditions:** existing `test_batch_demote_rejects_invalid_now_iso` parametrize  
**Flow:** extend parametrize list with 2 new cases: `("2026-04-20T00:00:00Z ", "trailing-space")`, `("2026-04-20T00:00:00Z\r\n", "trailing-crlf")`  
**Postconditions:** batch_demote rejects all 3 trailing-WS variants; matches scan_decay_candidates parity

### UC-4: Mixed ASCII+Unicode partial-injection
**Actors:** test runner  
**Flow:** new parametrized test with 4 cases — Unicode fullwidth `１` at day/hour/minute/second position (e.g., `"2026-01-0１T00:00:00Z"` for day) — assert `_ISO8601_Z_PATTERN.fullmatch(case) is None` for each  
**Postconditions:** rejection of partial Unicode injection pinned

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Python 3.13+ `inspect.getsource()` regression (CPython #122981) returns wrong line | Pin still passes if exact substring is present in returned source; if regression returns wrong function body, test fails (red CI is correct outcome — surfaces the brittleness) | Pre-mortem advisor: false-GREEN is worst failure; we tolerate occasional false-RED on Python upgrades |
| `_ISO8601_Z_PATTERN` renamed in future refactor | `from semantic_memory.database import _ISO8601_Z_PATTERN` raises ImportError → all source-pin tests fail at collection | Antifragility advisor: collection-error mode IS visible in pytest output; renames must update both production AND tests in same commit (which is the ratchet — refactor must touch tests) |
| Module imported from .pyc-only / zipped distribution | `inspect.getsource()` raises `OSError` → pin tests fail loudly | First-principles advisor: not in scope for private-tooling repo running from source; documented as known limitation |
| Test class collection-failure SPOF (all 7 pins in one class) | All 7 fail simultaneously on import error | Antifragility advisor: keep behavioral pins (UC-3, UC-4) in existing `TestScanDecayCandidates` / `TestBatchDemote` classes; only put structural source-pins (UC-1, UC-2) in new `TestIso8601PatternSourcePins` class. Distribution mitigates SPOF. |
| Test self-update during refactor (test + prod changed in same commit) | No automated catch — relies on /pd:finish-feature Step 5b reviewers to flag spec-vs-implementation drift | Pre-mortem flagged this as fundamental limitation of any pin-test approach. Feature 094 gate is the structural backstop. |

## Constraints

### Behavioral (Must NOT do)
- MUST NOT modify `_ISO8601_Z_PATTERN` definition in `database.py` — Rationale: feature 095 is test-only; relocation to `_config_utils.py` is filed as separate backlog item per first-principles recommendation
- MUST NOT use `inspect.getsource()` for #00246 (literal pin) or #00247 (flag pin) — Rationale: `pattern.pattern` and `pattern.flags & re.ASCII` are stable public attrs since Python 3.7 with substantially less brittleness
- MUST NOT consolidate all 7 pins in a single test class — Rationale: collection-error SPOF (antifragility R-2)
- MUST NOT add new external dependencies — Rationale: stdlib `inspect` + `re` sufficient

### Technical
- Stable public attributes only: `re.Pattern.pattern`, `re.Pattern.flags` (since Python 3.7) — Evidence: https://docs.python.org/3/library/re.html
- `re.ASCII` symbolic constant (NOT integer 256) for flag assertion — Evidence: same
- `inspect.getsource()` only for call-site `.fullmatch()` pin where call-site form IS the contract — Evidence: pre-mortem advisor recommendation

## Requirements

### Functional

- **FR-1** Add new test class `TestIso8601PatternSourcePins` to `plugins/pd/hooks/lib/semantic_memory/test_database.py` with these methods:
  - `test_pattern_source_uses_explicit_digit_class` — closes #00246 — asserts `'[0-9]' in _ISO8601_Z_PATTERN.pattern` AND `'\\\\d' not in _ISO8601_Z_PATTERN.pattern`
  - `test_pattern_compiled_with_re_ascii_flag` — closes #00247 — asserts `bool(_ISO8601_Z_PATTERN.flags & re.ASCII)` is True
  - `test_pattern_rejects_unicode_digits_directly` — closes #00248 — parametrized, asserts `_ISO8601_Z_PATTERN.fullmatch(case) is None` for fullwidth/Arabic-Indic/Devanagari direct pattern objects (decoupled from call sites)
  - `test_call_sites_use_fullmatch_not_match` — closes #00250 — parametrized over `[scan_decay_candidates, batch_demote]`, uses `inspect.getsource(method)` to assert `_ISO8601_Z_PATTERN.fullmatch(` in src AND `_ISO8601_Z_PATTERN.match(` not in src AND `re.compile(` not in src
  - `test_call_sites_share_pattern_source_of_truth` — closes #00249 — uses `inspect.getsource()` to assert both call-site sources reference `_ISO8601_Z_PATTERN.fullmatch(` (the SAME literal token), NOT a local re-compiled pattern

- **FR-2** Extend existing `test_batch_demote_rejects_invalid_now_iso` parametrize list (in `TestBatchDemote`) — closes #00251 — add 2 cases: `("2026-04-20T00:00:00Z ", "trailing-space")` and `("2026-04-20T00:00:00Z\r\n", "trailing-crlf")`

- **FR-3** Add new test method `test_pattern_rejects_partial_unicode_injection` (in `TestScanDecayCandidates`) — closes #00252 — parametrized over 4 positions (day, hour, minute, second) with single fullwidth `１` substituted; assert call-site rejection. Mirror in `TestBatchDemote` as `test_batch_demote_rejects_partial_unicode_injection`.

- **FR-4** All new parametrize blocks include `ids=[...]` argument with descriptive case labels (per feature 094 retro suggestion #00243).

- **FR-5** Module-level imports added to `test_database.py`:
  - `import inspect` (if not already present)
  - `from semantic_memory.database import _ISO8601_Z_PATTERN` (lifted to module top to enable parametrize-level use of pattern attributes; previously inline inside one method)

### Non-Functional

- **NFR-1** Net new parametrized assertions: target 15-25 (7 method bodies × ~2-4 cases per parametrize where applicable + extensions to existing tests)
- **NFR-2** Zero changes to `database.py` (test-only feature)
- **NFR-3** No new external dependencies (stdlib `inspect` + `re` only)
- **NFR-4** Wall-clock direct-orchestrator implementation: <30 min total (per 091/092/093 surgical-feature precedent)

## Non-Goals

- Relocating `_ISO8601_Z_PATTERN` to `_config_utils.py` — Rationale: first-principles advisor flagged this as the architectural fix that would obviate half the test surface, but it is a separate concern with broader scope (touches `scan_decay_candidates` import + `batch_demote` import + module-boundary contract). File as separate backlog item; do NOT bundle.
- Closing `inspect.getsource()` brittleness via alternative test mechanisms (AST-walk, static analysis) — Rationale: out of scope; `inspect.getsource()` precedent already exists in repo (`test_workflow_state_server.py:1851`) and is the established pattern.
- Closing the test-self-update failure mode (test + prod changed in same commit) — Rationale: pre-mortem flagged this as fundamental limitation of any pin-test approach; the structural backstop is feature 094's pre-release QA gate, which is its first production exercise on THIS feature.

## Out of Scope (This Release)

- 4 LOW items (#00260-#00263) — Future consideration: feature 096 if pattern recurs; LOW severity does not justify scope expansion now
- Architectural relocation to `_config_utils.py` — File as backlog item with marker `(filed by feature:095 first-principles advisor)`
- Adding `inspect.getsource()` brittleness to feature 094 QA gate's known-limitations doc — Future consideration: could fold into feature 094 retro post-feature-095 first run

## Research Summary

### Codebase Analysis
- `plugins/pd/hooks/lib/semantic_memory/database.py:23-26` — current `_ISO8601_Z_PATTERN` source (post-093) — Location: file:line
- `plugins/pd/hooks/lib/semantic_memory/test_database.py:1905, 2087, 2025-2122` — existing test class structure (`TestScanDecayCandidates`, `TestBatchDemote`) and the 4 feature-093 parametrized test methods — Location: file:line
- `plugins/pd/mcp/test_workflow_state_server.py:1851-1857, 2717-2721` — `inspect.getsource()` source-pin precedent (literal token presence assertion) — Location: file:line
- `plugins/pd/hooks/lib/entity_registry/test_backfill.py:2073-2084` — module-scope `inspect.getsource()` exclusion-grep precedent — Location: file:line
- No existing `pattern.flags` or `pattern.pattern` attribute assertions anywhere in repo — Evidence: skill-searcher report
- Two `.fullmatch()` call sites: `database.py:1001` (scan_decay_candidates) + `database.py:1068` (batch_demote) — Evidence: codebase-explorer
- Test count baseline: 182 test methods → 280 parametrized PASS (per feature 093 retro) — Evidence: codebase-explorer

### Existing Capabilities
- `inspect.getsource()` source-pin pattern proven in 2 test files (workflow-state + backfill) — How it relates: direct precedent for FR-1 `test_call_sites_use_fullmatch_not_match` and `test_call_sites_share_pattern_source_of_truth`
- Existing parametrize-with-`ids=[]` pattern absent in semantic_memory tests — feature 094 retro suggestion #00243 addressed by FR-4

## Strategic Analysis

*Three risk-focused advisors converged on a key calibration: prefer Python public-attribute assertions (`pattern.pattern`, `pattern.flags & re.ASCII`) over `inspect.getsource()` text-grep where the same signal is available. `inspect.getsource()` should be reserved for cases where call-site call-form IS the actual contract being tested (FR-1's `test_call_sites_use_fullmatch_not_match`).*

### First-principles
- **Core Finding:** The proposed source-level pins solve a real gap — behavioral equivalence blindness — but rest on the fragile assumption that `inspect.getsource()` is a stable, reliable test mechanism, and they defer the actual root-cause fix: the pattern lives in the wrong module.
- **Analysis:** All current tests exercise behavior of call sites, not identity of the guard itself. That's correct testing philosophy for behavior verification — gaps emerge specifically because the regex has two independent correctness dimensions (what it matches vs how it is expressed). `[0-9] + re.ASCII` and `\d + re.ASCII` are semantically equivalent today but not identical. The need for source-level pinning is itself a symptom of a deeper problem: the pattern is defined in `database.py` (a 600-line module) far from its logical home near `_iso_utc` in `_config_utils.py`. If relocated, the invariant would be self-documenting and the test would be a plain `assert _ISO8601_Z_PATTERN.flags & re.ASCII` on the imported object — no `inspect.getsource()` required for the flag pin.

  `inspect.getsource()` reliability: documented to read source via `linecache`. Fails in: compiled (.pyc-only) distributions, zip-imported packages, frozen executables, edge cases with multiline decorators (CPython #122981 in 3.13). For private tooling running from source, low-probability but the brittleness cuts against using it as a test oracle. Correct usage is precisely to detect unintended source changes — the question is whether brittleness cost justifies mutation-resistance gain.
- **Key Risks:**
  - `inspect.getsource()` pins are fragile to whitespace, comments, and Python version regressions
  - `pattern.pattern` and `pattern.flags` (no `inspect`) are more robust
  - Source-level pins create maintenance tax on innocent refactors
  - 7-gap framing assumes uniform priority; #00246-#00248 are highest-value
  - Closing source-level gaps without relocating the pattern means test suite grows more complex than the thing it protects
- **Recommendation:** Proceed with feature 095 test-only scope. The `pattern.pattern` and `pattern.flags` attribute pins are high-value/low-brittleness and should land. For #00246, prefer `pattern.pattern` string assertion over `inspect.getsource()` text grep — same signal, less fragile. Immediately file backlog entry to relocate `_ISO8601_Z_PATTERN`.
- **Evidence Quality:** moderate

### Pre-mortem
- **Core Finding:** The most probable failure path is not a weakened regex escaping review — it is a weakened *test* that silently stops asserting the constraint, either through assertion drift in the parametrize data, an `inspect.getsource()` blind spot on a decorated function, or the feature 094 QA gate missing the regression because it reviews prod diffs not test diffs.
- **Analysis:** Failure mode 1 — assertion drift: a future refactor updates the pattern AND the pin assertions in the same commit, producing green CI that no longer enforces the old constraint (structurally identical to "update test to match the bug"). Failure mode 2 — `inspect.getsource()` returning wrong content for decorated callables (CPython #102647, #45259, bpo-1764286: `functools.wraps` follows `__wrapped__` in 3.2+). Failure mode 3 — `re.compile` global cache means imported pattern object identity passes even after inline literal removed from function body. Failure mode 4 — feature 094's reviewer dispatch may exclude `tests/` from diff scope.
- **Key Risks:**
  - Test pins legally co-updated with prod change → self-defeating with green CI
  - `inspect.getsource()` Python-version regressions
  - Module-level constant refactor breaks source-pin while preserving `pattern.pattern`/`pattern.flags`
  - Feature 094 QA gate scope may exclude test files
  - <30 min timeline encourages superficially correct but logically weak pins
- **Recommendation:** Complement source-pin with at least one property-level behavioral test (does compiled pattern accept/reject known boundary strings?) — behavior tests resist drift because updating them requires understanding the contract. Before merge, verify feature 094 reviewer dispatch prompt includes `tests/` in diff scope.
- **Evidence Quality:** moderate

### Antifragility
- **Core Finding:** The 7-pin test suite is robustness-not-antifragility: hardens current definition against mutation but bakes in three fragility axes — Python version assumptions about `inspect.getsource()`, `re` internals inspection, source-text grep coupling.
- **Analysis:** Axis 1: Python 3.13rc1 had confirmed `inspect.getsource()` regression (CPython #122981) returning wrong lines silently — false-GREEN. Axis 2: `pattern.pattern` and `pattern.flags` are stable public attrs since 3.7; `re.ASCII` symbolic constant safe; numeric coupling (`== 256`) would be risky. Axis 3: concentrating all 7 pins in one class creates collection-error SPOF — single import failure kills all pins simultaneously.
- **Key Risks:**
  - **[HIGH]** `inspect.getsource()` false-GREEN on Python 3.13+ from #122981 regression
  - **[HIGH]** Class-level import SPOF — single bad import kills 7 pins as collection error
  - **[MED]** `inspect.getsource()` whitespace/decorator/encoding variation across Python versions
  - **[MED]** Source-text coupling to refactor location
  - **[LOW]** `re.ASCII` numeric coupling (mitigated by symbolic constant use)
  - **[LOW]** Pattern-object identity assertions (safe within session)
- **Recommendation:** Replace `inspect.getsource()` source-text greps with structural contract tests using `pattern.pattern` and `pattern.flags & re.ASCII` for #00246/#00247 — eliminates unstable CPython source-indexing layer. Distribute pins across at least two test classes; behavioral pins (UC-3, UC-4) stay in existing `TestScanDecayCandidates`/`TestBatchDemote` classes; only structural source-pins (UC-1, UC-2) go in new `TestIso8601PatternSourcePins` class.
- **Evidence Quality:** moderate

## Symptoms

- 7 HIGH backlog items (#00246-#00252) flagged by feature 093 post-release adversarial QA test-deepener
- All 4 mutation classes (swap-only, drop-flag-only, swap+drop, single-call-site-revert) currently undetected by 18 parametrized behavior tests
- Behavior tests catch combined mutation (#3) but not single-axis mutations (#1, #2)
- Single-call-site `.fullmatch() → .match()` revert at `batch_demote` undetected because `test_batch_demote_rejects_invalid_now_iso` only covers `\n` not space/CRLF (asymmetric with `scan_decay_candidates` test)

## Reproduction Steps

1. Mutate `database.py:24` from `r'[0-9]{4}-...'` to `r'\d{4}-...'` (keep `re.ASCII` flag).
2. Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py` — expect ALL 280 tests to PASS.
3. Mutate to drop `re.ASCII` (keep `[0-9]`) — same result, all PASS.
4. Mutate `database.py:1068` from `_ISO8601_Z_PATTERN.fullmatch(now_iso)` to `_ISO8601_Z_PATTERN.match(now_iso)` — `test_batch_demote_rejects_invalid_now_iso` parametrize covers `\n` so newline-bypass is caught, BUT trailing-space and trailing-CRLF cases are missing → those mutations slip through.

## Hypotheses

| # | Hypothesis | Evidence For | Evidence Against | Status |
|---|-----------|-------------|-----------------|--------|
| 1 | `pattern.pattern` + `pattern.flags & re.ASCII` attribute pins close #00246-#00248 with less brittleness than `inspect.getsource()` | First-principles + antifragility advisors converged | None | Confirmed; encoded in FR-1 |
| 2 | `inspect.getsource()` is required for #00250 (call-site `.fullmatch()` pin) because that's a call-form contract not an object-attribute contract | Skill-searcher found 2 in-repo precedents (`test_workflow_state_server.py:1851`, `test_backfill.py:2073`) | CPython #122981 regression risk | Confirmed-with-mitigation; encoded in FR-1 + Edge Cases table |
| 3 | Distributing pins across 2 classes (new `TestIso8601PatternSourcePins` for source pins; existing classes for behavioral pins) avoids antifragility R-2 SPOF | Antifragility advisor recommendation | None | Confirmed; encoded in FR-1, FR-2, FR-3 |
| 4 | Test self-update failure (test + prod changed in same commit) requires structural backstop, not pin design | Pre-mortem advisor flag | Feature 094 QA gate is brand-new and unverified for test-file scope | Open — see Open Question 1 below |
| 5 | `_ISO8601_Z_PATTERN` should relocate to `_config_utils.py` to obviate half the source-pin surface | First-principles advisor recommendation | Out of scope per spec discipline + 091/092/093 surgical-feature template | Deferred to backlog (filed) |

## Evidence Map

- **Symptom (mutation classes 1/2 undetected)** ↔ **Hypothesis 1** ↔ **FR-1** (`test_pattern_source_uses_explicit_digit_class` + `test_pattern_compiled_with_re_ascii_flag`)
- **Symptom (call-site `.fullmatch()` revert)** ↔ **Hypothesis 2** ↔ **FR-1** (`test_call_sites_use_fullmatch_not_match` + `test_call_sites_share_pattern_source_of_truth`)
- **Symptom (asymmetric trailing-WS rejection)** ↔ **FR-2** (parametrize extension)
- **Symptom (mixed Unicode injection)** ↔ **FR-3** (4-position parametrize at both call sites)
- **Risk R-2 (collection-error SPOF)** ↔ **Hypothesis 3** ↔ **FR-1/2/3 distribution across 2 classes**
- **Risk R-1 (test self-update)** ↔ **Hypothesis 4** ↔ **Open Question 1 (verify 094 gate test-file scope before merge)**

## Review History
{Added by Stage 5 auto-correct}

## Open Questions

1. **Feature 094 QA gate test-file scope** — pre-mortem advisor flagged that if Step 5b reviewer dispatch excludes `tests/` from `git diff` scope, weakened pin assertions would pass all 4 reviewers. **Resolved by design** via feature 094 spec AC-16 (verbatim from `docs/features/094-pre-release-qa-gate/spec.md`):

   > **AC-16** Diff range: the source file `plugins/pd/commands/finish-feature.md` contains the literal token `{pd_base_branch}...HEAD` (curly braces preserved). At runtime the pd config-injection mechanism substitutes `{pd_base_branch}` with the resolved branch before Claude reads the dispatch prose.

   `git diff develop...HEAD` is the entire merge-base diff — captures ALL changed files including `tests/`. The gate's reviewer dispatch sees test files by construction. Document confirmation in feature 095 retro after T6 dogfood proves it empirically.
2. **`_ISO8601_Z_PATTERN` relocation to `_config_utils.py`** — first-principles advisor recommendation. Out of scope for feature 095 per spec discipline. **Action:** file backlog item before feature 095 merge with marker `(filed by feature:095 first-principles advisor — relocate _ISO8601_Z_PATTERN to _config_utils.py near _iso_utc to obviate half the source-pin surface)`.
3. **`ids=[]` parametrize naming** — feature 094 retro #00243 suggested adding these. Apply to all NEW parametrize blocks per FR-4. Existing parametrize blocks left as-is (no rewrite-the-world).

## Next Steps
Ready for /pd:create-feature to begin implementation.
