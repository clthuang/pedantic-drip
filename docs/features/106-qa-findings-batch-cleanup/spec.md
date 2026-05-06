# Spec: QA Findings Batch Cleanup

## Problem

Features 104 and 105 each completed with QA-gate findings auto-filed to backlog under `## From Feature {id} Pre-Release QA Findings (2026-05-06)` sections — 4 MED + 6 LOW items total (#00310-#00319). Items have accumulated as deferred tech-debt across two consecutive features. This batch resolves them (or explicitly closes with rationale) so the backlog returns to a clean state.

## Scope-Decision Resolutions

The create-feature args called out 3 conflicting/coupled fixes. Resolutions:

**Decision 1 — #00310 vs #00315 (capture-on-stop test-injection seam):** The seam (`PD_TEST_WRITER_PYTHONPATH` / `PD_TEST_WRITER_PYTHON` env vars at `capture-on-stop.sh:42-44`) is the mechanism feature 104's tests rely on. Removing it would invalidate the existing test infrastructure (the original PYTHONPATH-only override doesn't survive the subprocess boundary because `capture-on-stop.sh` re-assigns `PYTHONPATH` before invoking the writer). Decision: **Option (b) — keep the seam and amend feature 104's design.md TD-2 to canonicalize it**. This makes #00310 a documentation-only fix. #00315 (defensive `CLAUDE_CODE_DEV_MODE` guard) remains in-scope as a separate small hardening.

**Decision 2 — #00312 vs #00314 (test-session-start consolidation):** The two files cover **different functions** (verified at spec time): `test-session-start.sh` (hyphenated) tests `cleanup_stale_correction_buffers` (1 test, AC-6.1 from feature 104). `test_session_start_cleanup.sh` (underscored) tests `cleanup_stale_mcp_servers` (5 tests: stale-PID, missing-PID-dir, invalid-PID-content, non-orphaned-process, double-fork-orphan). Both functions are defined in the same `session-start.sh` source file. Decision: **merge both files' tests into the single hyphenated `test-session-start.sh`, applying the sed-extract pattern (TD-1 from feature 104) to BOTH function extractions** (the underscored file currently embeds copy-paste of `cleanup_stale_mcp_servers`; new file will sed-extract both). This subsumes #00314 (sed-extract backport applied during consolidation). The underscored file is deleted. Coverage is preserved by counting test functions before vs after.

**Decision 3 — #00319 (agent_sandbox commit-stance):** This is a pure process learning, not a code defect. Decision: **add a one-paragraph note to `docs/dev_guides/component-authoring.md`** (or equivalent existing dev_guide that covers feature artifact conventions) reminding designers to verify `.gitignore` status of any prescribed committed-artifact path. Backlog item closes as "documented".

**Decision 4 — #00317 (validate.sh `|| true` pipeline nuance):** Pre-existing pattern, documented for future audit, fix-optional. Decision: **close as `wontfix` — keep as future-audit candidate**. No code change in this feature.

## Success Criteria

1. All 10 backlog items #00310-#00319 close with one of: (a) implementation in this feature, (b) documented as superseded by another item in this feature, (c) closed as `wontfix` with rationale, (d) closed as documented in dev_guides.
2. All existing hook tests (`bash plugins/pd/hooks/tests/test-hooks.sh`) continue to pass.
3. `validate.sh` continues to pass.
4. The pattern_promotion pytest continues to pass.
5. `bash plugins/pd/hooks/tests/test-session-start.sh` runs the consolidated tests (covering AC-6.1 `cleanup_stale_correction_buffers` from feature 104 AND the 5 `cleanup_stale_mcp_servers` tests previously in `test_session_start_cleanup.sh`). Total test count in consolidated file ≥ 6 (1 + 5).
6. Backlog rows for #00310-#00319 are updated with `(closed: ...)` annotations referencing this feature or specific resolution.

## Functional Requirements

### FR-1: Documentation updates (no code change)

**FR-1a (#00310):** Amend `docs/features/104-batch-b-test-hardening/design.md` TD-2 to canonicalize the test-injection seam. Add a paragraph after the existing TD-2 body documenting the `PD_TEST_WRITER_PYTHONPATH` / `PD_TEST_WRITER_PYTHON` env vars as the canonical mechanism, with rationale (PYTHONPATH-only doesn't survive subprocess boundary because `capture-on-stop.sh` hardcodes its own PYTHONPATH).

**FR-1b (#00319):** Add a one-paragraph note to `docs/dev_guides/component-authoring.md` under a new subsection (heading like "Committed vs gitignored evidence" or "Feature artifact paths"). The paragraph reminds designers to verify `.gitignore` status of any prescribed committed-artifact path. References feature 105's `.qa-gate-evidence.md` resolution as the precedent. Target file is fixed: `docs/dev_guides/component-authoring.md` (no implementer choice). If that file does not exist, create it.

**AC-1.1:** `docs/features/104-batch-b-test-hardening/design.md` contains a paragraph in or immediately after TD-2 referencing both `PD_TEST_WRITER_PYTHONPATH` and `PD_TEST_WRITER_PYTHON`. Verifiable via:
```bash
grep -A 30 "^### TD-2" docs/features/104-batch-b-test-hardening/design.md | grep -q "PD_TEST_WRITER_PYTHONPATH" || { echo "FAIL"; exit 1; }
grep -A 30 "^### TD-2" docs/features/104-batch-b-test-hardening/design.md | grep -q "PD_TEST_WRITER_PYTHON" || { echo "FAIL"; exit 1; }
echo "AC-1.1 PASS"
```

**AC-1.2:** `docs/dev_guides/component-authoring.md` contains a section or paragraph mentioning both `agent_sandbox` AND (`gitignore` OR `gitignored`). Verifiable:
```bash
grep -n "agent_sandbox" docs/dev_guides/component-authoring.md | grep -E "gitignore|gitignored" | head -1
# OR (since the keywords may be on different lines within the same paragraph):
awk '/^##/{section=$0} /agent_sandbox/{found_sb=1; sb_section=section} /gitignore|gitignored/{if(section==sb_section)found_gi=1} END{exit !(found_sb && found_gi)}' docs/dev_guides/component-authoring.md && echo "AC-1.2 PASS" || echo "AC-1.2 FAIL"
```
Required: at least one of the two checks succeeds.

### FR-2: Wire test scripts into runner (#00311)

Add invocations for `test-tag-correction.sh`, `test-capture-on-stop.sh`, and `test-session-start.sh` to `plugins/pd/hooks/tests/test-hooks.sh` so they run in the standard `bash plugins/pd/hooks/tests/test-hooks.sh` invocation. Update `docs/dev_guides/commands-reference.md` to reference the consolidated runner.

**AC-2.1:** Running `bash plugins/pd/hooks/tests/test-hooks.sh` invokes all 3 new test scripts. Verifiable via invocation-anchored grep (matches any non-comment line that ends with the script name, regardless of `bash`/`./`/`${SCRIPT_DIR}/`/`"${SCRIPT_DIR}/` prefix):
```bash
grep -cE "^[[:space:]]*[^#]*test-tag-correction\.sh" plugins/pd/hooks/tests/test-hooks.sh
grep -cE "^[[:space:]]*[^#]*test-capture-on-stop\.sh" plugins/pd/hooks/tests/test-hooks.sh
grep -cE "^[[:space:]]*[^#]*test-session-start\.sh" plugins/pd/hooks/tests/test-hooks.sh
```
Required: each grep ≥1 (one invocation line per script).

**AC-2.2:** `bash plugins/pd/hooks/tests/test-hooks.sh` exits 0 after the wiring change. Verifiable via running the script.

**AC-2.3:** `docs/dev_guides/commands-reference.md` contains a reference to `test-hooks.sh` and the consolidated test set. Verifiable:
```bash
grep -E "test-hooks\.sh" docs/dev_guides/commands-reference.md | head -1
```
Required: ≥1 match.

### FR-3: Consolidate test-session-start files (#00312, subsumes #00314)

Merge `test_session_start_cleanup.sh` (covers `cleanup_stale_mcp_servers`, 5 tests, copy-paste extraction) into `test-session-start.sh` (covers `cleanup_stale_correction_buffers`, 1 test, sed-extract). Apply the sed-extract pattern (TD-1 from feature 104) to BOTH function extractions in the merged file. Delete `test_session_start_cleanup.sh` after merge.

**AC-3.1:** `plugins/pd/hooks/tests/test-session-start.sh` contains test functions covering BOTH `cleanup_stale_correction_buffers` AND `cleanup_stale_mcp_servers`. The underscored `test_session_start_cleanup.sh` no longer exists. Verifiable:
```bash
test -f plugins/pd/hooks/tests/test-session-start.sh || { echo "FAIL: hyphenated file missing"; exit 1; }
test ! -f plugins/pd/hooks/tests/test_session_start_cleanup.sh || { echo "FAIL: underscored file still present"; exit 1; }
grep -q "cleanup_stale_correction_buffers" plugins/pd/hooks/tests/test-session-start.sh || { echo "FAIL: correction-buffers function reference missing"; exit 1; }
grep -q "cleanup_stale_mcp_servers" plugins/pd/hooks/tests/test-session-start.sh || { echo "FAIL: mcp-servers function reference missing"; exit 1; }
echo "AC-3.1 PASS"
```

**AC-3.2:** The consolidated `test-session-start.sh` uses sed-extract for BOTH function extractions (no copy-paste from session-start.sh). Verifiable:
```bash
grep -c "sed -n '/^cleanup_stale_correction_buffers" plugins/pd/hooks/tests/test-session-start.sh  # ≥1
grep -c "sed -n '/^cleanup_stale_mcp_servers" plugins/pd/hooks/tests/test-session-start.sh  # ≥1
```
Required: each grep ≥1 match.

**AC-3.3:** The consolidated file preserves all 6 prior tests (1 from hyphenated + 5 from underscored). Verifiable:
```bash
test_count=$(grep -cE "^[[:space:]]*test_[a-zA-Z_]+\(\)" plugins/pd/hooks/tests/test-session-start.sh)
[[ "$test_count" -ge 6 ]] || { echo "FAIL: only $test_count tests, expected ≥6"; exit 1; }
echo "AC-3.3 PASS ($test_count tests)"
```

**AC-3.4:** Running `bash plugins/pd/hooks/tests/test-session-start.sh` exits 0 with all 6 consolidated tests passing.

### FR-4: Refactor test_category_mapping (#00313)

Refactor the interleaved-teardown test in `plugins/pd/hooks/tests/test-capture-on-stop.sh` (`test_category_mapping`, line 188) into two smaller test functions, one per branch (anti-patterns vs patterns), each with own setup/teardown.

(Note: backlog #00313 mis-attributes the function to `test-tag-correction.sh`. The function actually lives in `test-capture-on-stop.sh:188` — verified at spec time. FR-4 location is authoritative.)

**AC-4.1:** `plugins/pd/hooks/tests/test-capture-on-stop.sh` contains 2 test functions covering category mapping (one per branch), instead of one combined function. Verifiable (regex aligned with design I-4 function names `test_category_mapping_anti_patterns()` and `test_category_mapping_preference()`):
```bash
grep -cE "^test_category_mapping_(anti_patterns|preference)\(\)" plugins/pd/hooks/tests/test-capture-on-stop.sh
```
Required: ≥2 matches.

**AC-4.2:** Running `bash plugins/pd/hooks/tests/test-capture-on-stop.sh` exits 0 with all tests passing (no regression from the refactor).

### FR-5: Defensive env-var guard (#00315)

Add a `[[ "${CLAUDE_CODE_DEV_MODE:-}" == "1" ]]` guard to the test-injection seam in `plugins/pd/hooks/capture-on-stop.sh:42-44` so the env-var override only takes effect when `CLAUDE_CODE_DEV_MODE=1` is set.

**AC-5.1:** `capture-on-stop.sh` checks `CLAUDE_CODE_DEV_MODE` before honoring `PD_TEST_WRITER_PYTHONPATH` / `PD_TEST_WRITER_PYTHON`. Implementer must use one of: (a) inline guard on each env-var line (`[[ "${CLAUDE_CODE_DEV_MODE:-}" == "1" ]] && [[ -n "${PD_TEST_WRITER_PYTHONPATH:-}" ]] && writer_pythonpath="$PD_TEST_WRITER_PYTHONPATH"`), or (b) wrapping `if [[ ... DEV_MODE ... ]]; then` block around both env-var checks. Verifiable: extract the section between the existing `# Feature 104 test-injection seam` comment and the next blank line / comment, and assert `CLAUDE_CODE_DEV_MODE` appears in that block:
```bash
section=$(awk '/# Feature 104 test-injection seam/,/^[[:space:]]*$/' plugins/pd/hooks/capture-on-stop.sh)
echo "$section" | grep -q "CLAUDE_CODE_DEV_MODE" || { echo "AC-5.1 FAIL: guard missing"; exit 1; }
echo "$section" | grep -q "PD_TEST_WRITER_PYTHONPATH" || { echo "AC-5.1 FAIL: seam missing"; exit 1; }
echo "AC-5.1 PASS"
```

**AC-5.2:** `bash plugins/pd/hooks/tests/test-capture-on-stop.sh` continues to pass after the guard is added (the test must export `CLAUDE_CODE_DEV_MODE=1` so the seam is honored). The test script may need a one-line update to set this var.

### FR-6: validate.sh log_info ordering (#00316)

Move the success `log_info` for `codex_routing_exclusion_violations` to print before the success `log_info` for `codex_routing_allowlist_violations`, matching the order the checks actually run in (exclusion check first at lines 858-878, allowlist check second at lines 883-908).

**AC-6.1:** In `validate.sh`, the line `[ "$codex_routing_exclusion_violations" = "0" ] && log_info "Codex Reviewer Routing exclusions validated"` appears BEFORE the line `[ "$codex_routing_allowlist_violations" = "0" ] && log_info "Codex routing coverage allowlist validated (11 expected files)"`. Verifiable:
```bash
exclusion_line=$(grep -n "exclusions validated" validate.sh | head -1 | cut -d: -f1)
allowlist_line=$(grep -n "allowlist validated" validate.sh | head -1 | cut -d: -f1)
[ "$exclusion_line" -lt "$allowlist_line" ] && echo "AC-6.1 PASS" || echo "AC-6.1 FAIL"
```

**AC-6.2:** `./validate.sh` exits 0 after the reorder.

### FR-7: secretary.md R-8 line-number drop (#00318)

Edit `plugins/pd/commands/secretary.md` to drop the parenthetical "(line 726)" from the R-8 note. The anchor text "Step 7 DELEGATE" is content-stable; the line number is soft.

**AC-7.1:** `plugins/pd/commands/secretary.md` no longer contains `(line 726)` in the R-8 note paragraph. Verifiable:
```bash
grep -A 1 "Dynamic agent dispatch at Step 7 DELEGATE" plugins/pd/commands/secretary.md | grep -q "(line 726)" && echo "AC-7.1 FAIL" || echo "AC-7.1 PASS"
```

**AC-7.2:** The R-8 note still contains the anchor text "Step 7 DELEGATE" so the cross-reference remains intact. Verifiable:
```bash
grep -q "Step 7 DELEGATE" plugins/pd/commands/secretary.md && echo "AC-7.2 PASS" || echo "AC-7.2 FAIL"
```

### FR-8: Backlog row annotations

Update `docs/backlog.md` rows for #00310-#00319 with `(closed: ...)` annotations referencing this feature.

**AC-8.1:** All 10 backlog rows are annotated with closing rationale. Verifiable (regex grouping fixed):
```bash
for id in 00310 00311 00312 00313 00314 00315 00316 00317 00318 00319; do
  grep -E "^- \*\*#$id\*\*.*(\(closed:|fixed in feature:106|wontfix)" docs/backlog.md > /dev/null \
    || { echo "FAIL: #$id not annotated"; exit 1; }
done
echo "AC-8.1 PASS"
```

## Closure Disposition Table

| Backlog ID | Disposition | FR |
|---|---|---|
| #00310 | Documented (TD-2 canonicalized) | FR-1a |
| #00311 | Implemented (test runner wiring) | FR-2 |
| #00312 | Implemented (consolidation) | FR-3 |
| #00313 | Implemented (test refactor) | FR-4 |
| #00314 | Subsumed by #00312 (sed-extract during consolidation) | FR-3 |
| #00315 | Implemented (CLAUDE_CODE_DEV_MODE guard) | FR-5 |
| #00316 | Implemented (log_info reorder) | FR-6 |
| #00317 | wontfix (pre-existing pattern; future-audit candidate) | n/a |
| #00318 | Implemented (drop line-726 parenthetical) | FR-7 |
| #00319 | Documented (dev_guide note) | FR-1b |

## Out of Scope

- Promoting the test-injection seam to a workflow-transitions helper (deferred per `codex-routing.md` "Future Considerations" pattern).
- Refactoring the broader validate.sh structure (only FR-6's specific log_info reorder is in scope).
- Touching feature 104's or feature 105's other artifacts beyond TD-2 amendment (FR-1a) and the secretary.md R-8 fix (FR-7).
- Adding new test infrastructure beyond consolidation (FR-3) and runner wiring (FR-2).
- Mutation-resistance, Unicode-injection, exotic-concurrency hardening (per user filter).
- Resolving the abandoned 011 feature (separate concern).

## Notes

- Feature follows the same direct-orchestrator pattern proven across features 101, 102, 104, 105 — heavy upstream review (target ~10 reviewer iterations across phases) buys single-pass implementation.
- File-touch surface (verified at spec time):
  - 6 files modified: `plugins/pd/hooks/capture-on-stop.sh` (FR-5), `plugins/pd/hooks/tests/test-hooks.sh` (FR-2), `plugins/pd/hooks/tests/test-capture-on-stop.sh` (FR-4), `plugins/pd/hooks/tests/test-session-start.sh` (FR-3, expanded), `plugins/pd/commands/secretary.md` (FR-7), `validate.sh` (FR-6).
  - 1 deletion: `plugins/pd/hooks/tests/test_session_start_cleanup.sh` (FR-3).
  - 3 doc files: `docs/features/104-batch-b-test-hardening/design.md` (FR-1a), `docs/dev_guides/component-authoring.md` or equivalent (FR-1b), `docs/dev_guides/commands-reference.md` (FR-2 reference).
  - `docs/backlog.md` (FR-8).
- 8 FRs / 18 ACs total. Tight scope; binary-checkable DoDs.
