# Backlog Archive

Closed sections moved from backlog.md by /pd:cleanup-backlog.

## From Feature 082 QA (2026-04-18)

- **#00075** No timeout cap when gtimeout/timeout absent in session-start.sh (pre-existing pattern shared by build_memory_context, run_reconciliation, run_doctor_autofix). Medium risk on minimal macOS without coreutils. (fixed in feature:089 — Python subprocess fallback with timeout=10)
- **#00076** Equal decay thresholds + rapid sequential calls = double demotion across ticks. Spec-compliant but may surprise API callers. Consider semantic-coupling warning for `med == high` (currently only warns when `med < high`). (fixed in feature:091-082-qa-residual-cleanup — `<=` predicate + updated warning text)
- **#00077** AC-22 test covers file-missing only; not SyntaxError/ImportError in maintenance.py. Shell guard (`|| true + 2>/dev/null`) handles all uniformly. Low priority. (fixed in feature:091-082-qa-residual-cleanup — AC-22b/c blocks in test-hooks.sh via temp-PYTHONPATH subshell harness)
- **#00078** `_select_candidates` accesses `db._conn` directly for read query. Add public `MemoryDatabase.scan_decay_candidates()` method if the encapsulation norm is elevated. (fixed in feature:091-082-qa-residual-cleanup — scan_decay_candidates public method + caller swap)
- **#00079** `updated_at IS NULL` guard in `_execute_chunk` SQL is dead code — schema enforces NOT NULL on `updated_at`. Defensive; harmless. Remove if cleanliness preferred. (fixed in feature:091-082-qa-residual-cleanup — dead branch removed from database.py _execute_chunk)
## From Feature 095 First-Principles Advisor (2026-04-29)

- **#00277** [MED/architecture] Relocate `_ISO8601_Z_PATTERN` from `database.py:23-26` to `_config_utils.py` near `_iso_utc`. Co-locating the validator with its producer would: (1) make source-level pins trivially checkable as `assert _PATTERN.flags & re.ASCII` without requiring `inspect.getsource()` on call-site method bodies; (2) centralize the two call sites onto a single canonical import; (3) make module-level invariants testable without implementation coupling to `database.py` internals; (4) break the recursive test-hardening pattern observed across 091/092/093/095 where each hardening iteration generates new test-coverage debt because the validator lives in a non-obvious place. Filed by feature:095 first-principles advisor as the architectural debt root-cause. (filed by feature:095 — relocate pattern to config-utils) (promoted → feature:096-iso8601-pattern-relocation)
## From Feature 095 Pre-Release QA Findings (2026-04-29)

First production exercise of feature 094's Step 5b adversarial QA gate produced 8 MEDs (3 from test-deepener after AC-5b HIGH→MED remap + 5 native MEDs) and 3 LOWs. Auto-filed per FR-7a. Gate verdict: PASS (HIGH count = 0).

**MED (1, consolidated from 8) — surfaced by feature:095 pre-release QA:**

- **#00278** [MED/testability] (promoted → feature:097-iso8601-test-pin-v2) **Test-pin refinement bundle (8 sub-items, consolidated from #00278-#00285)** — feature 095's `TestIso8601PatternSourcePins` source-pins all use substring/presence checks that miss several mutation classes. A single follow-up "test-pin v2" sweep should address all 8 together. Sub-items:
  - **(a)** `test_pattern_source_uses_explicit_digit_class` substring asserts miss character-class EXPANSION (`[0-9０-９]` keeps `[0-9]` substring AND keeps `\d` absent). Fix: replace with exact-string equality on `_ISO8601_Z_PATTERN.pattern`.
  - **(b)** `test_pattern_compiled_with_re_ascii_flag` asserts presence not exclusivity — `re.ASCII | re.IGNORECASE` mutation keeps `flags & re.ASCII` truthy while making lowercase `z` match. Fix: pin exact bitmask OR add behavioral lowercase-z negative case.
  - **(c)** `test_call_sites_use_fullmatch_not_match` is closed-set over 2 methods — future call sites slip past. Fix: open-set discovery via `inspect.getmembers(MemoryDatabase, predicate=inspect.isfunction)`.
  - **(d)** Same test's negative asserts brittle to comments/docstrings — a warning comment containing `_ISO8601_Z_PATTERN.match(` would false-fail. Fix: AST-walk via `ast.parse()` for `ast.Call` nodes instead of substring search.
  - **(e)** Same test's negatives only exclude `.match(` and `re.compile(` — `.search(`/`.findall(`/`.finditer(` mutations slip past. `.search()` dangerous: `Z junk` would match. Fix: extend negative-assertion list OR invert via AST-walk.
  - **(f)** Pre-fullmatch input mutation untested: `_ISO8601_Z_PATTERN.fullmatch(now_iso.rstrip())` passes both source pin AND behavioral trailing-WS tests. Fix: pass `'  ...Z  '` (leading + trailing) and assert rejection; OR AST-pin fullmatch's argument as bare Name.
  - **(g)** `TestIso8601PatternSourcePins` module-level import creates collection-error blast radius across all 214 tests on rename. Fix: `pytest.importorskip` probe + isolation test using `getattr(...)`.
  - **(h)** `test_pattern_rejects_unicode_digits_directly` covers only 3 Unicode scripts (fullwidth, Arabic-Indic, Devanagari) at year position — Bengali, Tibetan, Khmer, Myanmar slip past. Fix: property-based test enumerating ALL Unicode `Nd` category chars.

  Surfaced by feature:095 test-deepener (3 HIGH→MED via AC-5b narrowed remap with no cross-confirm; 5 native MED).

  **Post-096 audit (2026-04-29):** the original brief's claim that sub-items (a, c, e, g) would be "trivially obviated" by feature 096's relocation was over-stated. After auditing each sub-item against the post-096 state of `test_database.py:2265-2309`, **none** of the eight concerns is actually eliminated by relocation alone — the test methods continue to use substring/closed-set assertions on `_ISO8601_Z_PATTERN.pattern` regardless of which module hosts the symbol. What feature 096 *did* enable is a new defensive test (`assert database._ISO8601_Z_PATTERN is _config_utils._ISO8601_Z_PATTERN` for single-source-of-truth pinning) which is additive, not obviating. Recommended next steps:
  - **Lower priority** for sub-items (a, c, e, g): the architectural fix (096) reduces the *frequency* at which this debt manifests (no more recursive hardening pressure on this specific symbol), but the test-pin weaknesses themselves remain.
  - **Defer all 8 sub-items** unless a concrete mutation slips through — feature 096's hash-equality + co-location pattern reduces the realistic blast radius of escape mutations to "very low".
  - **If pursued**, scope as a single "test-pin v2 sweep" feature targeting all 8 sub-items together (they share a common test class and remediation style).

**LOW (3) — surfaced by feature:095 pre-release QA:**

- ~~**#00286**~~ [LOW/testability] **CLOSED 2026-04-29** — FR-2 trailing-whitespace extension extended to `\t`, `\v`, `\f`, `\r` alone, and NEL (U+0085). `test_pattern_rejects_trailing_whitespace` parametrize +5 cases; `TestBatchDemote._INVALID_NOW_ISO_CASES` +5 cases. pytest 214→224 (+10).
- ~~**#00287**~~ [LOW/testability] **CLOSED 2026-04-29** — `assert r'\D' not in _ISO8601_Z_PATTERN.pattern` added to `test_pattern_source_uses_explicit_digit_class`.
- ~~**#00288**~~ [LOW/quality] **CLOSED 2026-04-29** — `specifying` skill Self-Check now requires explicit enumeration of all stdlib imports referenced in test bodies (not just the most prominent one). Closes the traceability gap for future specs.
## From Feature 097 Pre-Release QA Findings (2026-04-29)

**MED (4) — surfaced by feature:097 pre-release QA gate (THIRD production exercise):**

All four below were closed 2026-04-29 with the same architectural rationale that justified the HIGH overrides in `docs/features/097-iso8601-test-pin-v2/qa-override.md`: continuing to expand source-pin coverage (cross-consumer discovery, all-isspace whitespace, FOR-EACH Unicode-Nd, fixture isolation) is the recursive test-hardening anti-pattern (#00277 closed by feature 096). Behavioral coverage in TestScanDecayCandidates and TestBatchDemote already catches real production regressions at call sites. The honest fix when source-pin tests reach their natural limit is to STOP — not to file deeper source-pinning at lower severity. Per qa-override.md §"Architectural decision": revisit only if a real production regression slips through.

- ~~**#00290**~~ [MED/testability] **CLOSED 2026-04-29 (architectural — same rationale as HIGH overrides)** — Cross-consumer identity-pin gap. FR-7's check covers `database._ISO8601_Z_PATTERN is _config_utils._ISO8601_Z_PATTERN`; the architectural single-source-of-truth in `_config_utils.py` makes additional `pkgutil.iter_modules` discovery a recursive harden. If `maintenance`/`refresh`/`memory_server` ever re-shadow the symbol, behavioral tests at those call sites catch the regression independently.
- ~~**#00291**~~ [MED/testability] **CLOSED 2026-04-29 (architectural — same rationale as HIGH overrides)** — Leading-WS coverage extension. The regex `[0-9]{4}-...Z` under `re.fullmatch` rejects ANY leading non-digit by virtue of position-0 character class. ASCII-space coverage is a representative spot-check; extending to `\t`/`\n`/`\r`/`\v`/`\f`/U+00A0 tests `re.fullmatch` semantics, not the validator. Recursive harden of stdlib contract.
- ~~**#00292**~~ [MED/testability] **CLOSED 2026-04-29 (no-op cleanup not worth churn)** — `_pattern_probe` cosmetic fixture. Spec explicitly acknowledged this trade-off. The fixture's documentation value (signaling "this test class depends on `_ISO8601_Z_PATTERN`") exceeds its cosmetic-no-op cost. Deletion would lose self-documentation; full isolation would require routing 21 tests through fixtures for zero behavioral change.
- ~~**#00293**~~ [MED/testability] **CLOSED 2026-04-29 (architectural — same rationale as HIGH overrides)** — Unicode-Nd FOR-EACH-SCRIPT expansion. The validator IS Python's `[0-9]` + `re.ASCII` — a stdlib contract. The 13-script curated sample provides spot-check; extending to all ~75 Nd scripts tests Python's Unicode database, not the validator. Same recursive-hardening anti-pattern as HIGH overrides.

**Override-applied HIGH (2) — accepted as residual risk per qa-override.md:**

- ~~AST-walk misses aliased / getattr / walrus call forms (test_database.py:2354-2362)~~ — **OVERRIDE accepted**: behavioral tests in TestScanDecayCandidates/TestBatchDemote catch real production regressions; this is recursive test-hardening cycle (anti-pattern #00277 closed by 096). Revisit only if production regresses.
- ~~`re.fullmatch(_ISO8601_Z_PATTERN.pattern, s)` flag-bypass form not flagged (test_database.py:2338-2367)~~ — **OVERRIDE accepted**: same architectural rationale.
## From Feature 096 Retro Tune #5 (2026-04-29)

- ~~**#00289**~~ [LOW/docs-hygiene] **CLOSED 2026-04-29 (promoted → feature:098-tier-doc-frontmatter-sweep)** — content-audited and refreshed via 6 parallel audit subagents. 5 BUMP_AND_FIX + 1 DRIFT (api-reference.md). All 6 timestamps bumped to 2026-04-29 with `audit-feature` provenance. Original entry preserved below for reference: Tier-doc frontmatter drift sweep. As of 2026-04-29, six tier-doc files have stale `last-updated` frontmatter values that pre-date their tier's source-monitoring timestamp:
  - `docs/user-guide/overview.md` (last-updated 2026-04-02; source ts 2026-04-18)
  - `docs/user-guide/installation.md` (last-updated 2026-04-15; source ts 2026-04-18)
  - `docs/user-guide/usage.md` (last-updated 2026-04-15; source ts 2026-04-18)
  - `docs/technical/architecture.md` (last-updated 2026-04-15T00; source ts 2026-04-15T09)
  - `docs/technical/workflow-artifacts.md` (last-updated 2026-04-15T00; source ts 2026-04-15T09)
  - `docs/technical/api-reference.md` (last-updated 2026-04-02; source ts 2026-04-15)

  Drift accumulated across features 079-095, NOT feature 096-driven. The honest fix is content-audit-then-bump (verify each doc still reflects current state before updating timestamp), not mechanical timestamp bumping. Estimated effort: ~30 minutes per doc × 6 = 3 hours. Filed as a future feature scope rather than inline cleanup. Surfaced by feature:096 retro Tune #5.
