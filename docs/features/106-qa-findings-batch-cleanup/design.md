# Design: QA Findings Batch Cleanup

## Prior Art Research

**Status:** Skipped per YOLO mode (domain-expert path). Direct prior art is the QA gates themselves — features 104 (`feature/104-batch-b-test-hardening`) and 105 (`feature/105-codex-routing-coverage-extension`) already exist and surfaced these findings. The fixes are scoped extensions of patterns already established in those features (sed-extract from 104 TD-1, codex-routing exclusion guard from 103, manual-checklist evidence from 105).

## Architecture Overview

This feature is a coverage-cleanup batch — 8 small, independent fixes across 6 files plus 2 doc updates plus 10 backlog annotations. No architectural change; no new components. Each FR maps to a small surgical edit at a specific anchor point. Implementation follows the direct-orchestrator pattern (single-pass review).

```
┌─────────────────────────────────────────────────────────────────────┐
│  6 files modified                                                   │
│                                                                     │
│  Production hooks:                                                  │
│    plugins/pd/hooks/capture-on-stop.sh ........... FR-5 (+1 guard)  │
│                                                                     │
│  Tests (consolidation + refactor + runner wiring):                  │
│    plugins/pd/hooks/tests/test-hooks.sh .......... FR-2 (3 invokes) │
│    plugins/pd/hooks/tests/test-capture-on-stop.sh  FR-4 (split fn)  │
│    plugins/pd/hooks/tests/test-session-start.sh .. FR-3 (+5 tests,  │
│                                                    sed-extract)    │
│  Test deletion:                                                     │
│    plugins/pd/hooks/tests/test_session_start_cleanup.sh             │
│                                                                     │
│  Commands/skills:                                                   │
│    plugins/pd/commands/secretary.md .............. FR-7 (drop "(line │
│                                                    726)")           │
│  Validation:                                                        │
│    validate.sh ................................... FR-6 (swap 2     │
│                                                    log_info lines)  │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3 documentation files updated                                      │
│                                                                     │
│  docs/features/104-batch-b-test-hardening/design.md ..... FR-1a     │
│    (TD-2 amendment canonicalizing PD_TEST_WRITER seam)              │
│  docs/dev_guides/component-authoring.md ................. FR-1b     │
│    (new subsection on gitignored vs committed evidence paths)       │
│  docs/dev_guides/commands-reference.md .................. FR-2      │
│    (reference to consolidated test runner)                          │
│  docs/backlog.md ........................................ FR-8      │
│    (annotate 10 rows #00310-#00319 with closing rationale)          │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

### C1: capture-on-stop.sh defensive guard (FR-5, #00315)

Wrap the existing test-injection seam (lines 42-44) with a `CLAUDE_CODE_DEV_MODE` guard. Implementer may use either:
- **(a) Inline form:** prepend `[[ "${CLAUDE_CODE_DEV_MODE:-}" == "1" ]] &&` to each `[[ -n "${PD_TEST_WRITER_*}" ]]` line.
- **(b) Block form:** wrap both lines in `if [[ "${CLAUDE_CODE_DEV_MODE:-}" == "1" ]]; then ... fi`.

Either form satisfies AC-5.1's awk-extracted-section check.

### C2: test-hooks.sh runner wiring (FR-2, #00311)

`test-hooks.sh` currently defines all tests inline as bash functions (no external test-script invocations). Add 3 invocation lines near the end of `main()`, before the result-summary block, that source/invoke the 3 external test scripts. Pattern:
```bash
echo ""
echo "--- External Test Scripts ---"
echo ""
"${SCRIPT_DIR}/test-tag-correction.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))
"${SCRIPT_DIR}/test-capture-on-stop.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))
"${SCRIPT_DIR}/test-session-start.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))
```
The external scripts return non-zero on test failure (they already follow `[[ $TESTS_FAILED -eq 0 ]]` exit pattern). Combining their pass/fail into the wrapper's TESTS_FAILED counter is sufficient; the external scripts print their own per-test PASS/FAIL output.

### C3: test-session-start.sh consolidation (FR-3, #00312, subsumes #00314)

Merge tests from `test_session_start_cleanup.sh` (5 tests for `cleanup_stale_mcp_servers`) into `test-session-start.sh` (1 test for `cleanup_stale_correction_buffers`). Apply sed-extract pattern (TD-1 from feature 104) to both function extractions.

The merged file uses two sed-extract blocks:
```bash
# Extract cleanup_stale_correction_buffers via sed (from feature 104 TD-1)
sed -n '/^cleanup_stale_correction_buffers()/,/^}/p' "${HOOKS_DIR}/session-start.sh" > "$fn_tmpfile_correction"
HOME="$tmp_home" source "$fn_tmpfile_correction"

# Extract cleanup_stale_mcp_servers via sed (new for FR-3)
sed -n '/^cleanup_stale_mcp_servers()/,/^}/p' "${HOOKS_DIR}/session-start.sh" > "$fn_tmpfile_mcp"
source "$fn_tmpfile_mcp"
```

Both functions are at top-level in session-start.sh (verified at design time): `cleanup_stale_mcp_servers()` at line 227, `cleanup_stale_correction_buffers()` at line 282. The sed-extract regex `/^{name}()/,/^}/p` works on both.

After merge, delete `test_session_start_cleanup.sh`.

### C4: test-capture-on-stop.sh test_category_mapping refactor (FR-4, #00313)

The existing `test_category_mapping` function at line 188 covers two branches (anti-patterns vs preference-statement) with interleaved teardown. Refactor into:
- `test_category_mapping_anti_patterns()` — covers anti-pattern branch with own setup/teardown
- `test_category_mapping_preference()` — covers patterns branch with own setup/teardown

The original `test_category_mapping` invocation at the bottom of the file is replaced by the two new function invocations.

### C5: validate.sh log_info reorder (FR-6, #00316)

Two `log_info` lines at the end of the codex-routing block (currently lines 909, 911 after feature 105's changes):
```bash
[ "$codex_routing_allowlist_violations" = "0" ] && log_info "Codex routing coverage allowlist validated (11 expected files)"
# ... blank line ...
[ "$codex_routing_exclusion_violations" = "0" ] && log_info "Codex Reviewer Routing exclusions validated"
```

Swap so the exclusion-validated message comes first (matches check order: exclusion check at lines 858-878, allowlist check at 883-908).

### C6: secretary.md R-8 line-number drop (FR-7, #00318)

Edit the R-8 note paragraph to remove the parenthetical "(line 726)". Single-line edit. Anchor text "Step 7 DELEGATE" stays for cross-reference stability.

### C7: feature 104 design.md TD-2 amendment (FR-1a, #00310)

Add a paragraph after the existing TD-2 body documenting the canonicalized test-injection seam. Body content:
```markdown
**Amendment (feature 106 #00310):** The canonical test-injection mechanism is the
`PD_TEST_WRITER_PYTHONPATH` / `PD_TEST_WRITER_PYTHON` env-var seam at
`capture-on-stop.sh:42-44`. PYTHONPATH-only override (the original TD-2 design)
does not survive the subprocess boundary because `capture-on-stop.sh` re-assigns
`PYTHONPATH` before invoking the writer. The env-var seam is gated by
`CLAUDE_CODE_DEV_MODE=1` (added by feature 106 FR-5) so production behavior is
unchanged when the dev-mode flag is unset.
```

### C8: dev_guide note on gitignored evidence paths (FR-1b, #00319)

Add a new subsection to `docs/dev_guides/component-authoring.md` titled "Committed vs gitignored evidence paths". Body content:
```markdown
## Committed vs gitignored evidence paths

When designing a feature that prescribes evidence files (terminal output of manual checklists,
QA gate procedure logs, etc.) be committed at a specific path, verify the target path's
`.gitignore` status FIRST. Common pitfall: `agent_sandbox/` is the project convention for
agent-generated non-workflow content (per CLAUDE.md), but it is gitignored at the repo root.

If evidence files MUST be committed for QA-gate verification:
- Place them under `docs/features/{id}-{slug}/.qa-gate-evidence.md` or similar (committed by
  default).
- Or under any other non-gitignored path verified via `git check-ignore <path>`.

Precedent: feature 105 originally prescribed `agent_sandbox/2026-05-06/feature-105-evidence/`
in design I-5 ("Evidence files ARE committed..."), discovered at implement-time that the path
was gitignored, resolved by committing the procedure outputs to `.qa-gate-evidence.md` in the
feature directory. See `docs/features/105-codex-routing-coverage-extension/.qa-gate-evidence.md`.
```

### C9: backlog.md annotations (FR-8)

Update 10 rows under the "From Feature 104 Pre-Release QA Findings" and "From Feature 105 Pre-Release QA Findings" sections, appending one of:
- `(closed: implemented in feature:106-qa-findings-batch-cleanup)` — for FR-implemented items (#00310, 00311, 00312, 00313, 00315, 00316, 00318)
- `(closed: subsumed by #00312 in feature:106)` — for #00314
- `(closed: wontfix — pre-existing pattern, future-audit candidate)` — for #00317
- `(closed: documented in docs/dev_guides/component-authoring.md, feature:106)` — for #00319

## Technical Decisions

### TD-1: Use direct-orchestrator pattern for implement

**Decision:** Implement all 8 FRs inline in the implement phase orchestrator, no per-task implementer dispatches.

**Rationale:** This batch-cleanup is the 6th consecutive feature applying the heavy-upstream / cheap-downstream pattern (101, 102, 104, 105, 106). All 8 FRs have binary-checkable DoDs at specific anchor points. No subagent dispatch needed for execution; the AC verification snippets ARE the test plan.

### TD-2: Keep capture-on-stop.sh test-injection seam (don't remove it)

**Decision:** Resolve #00310 by amending feature 104's design TD-2 to canonicalize the env-var seam, not by removing the seam.

**Rationale:** The seam is real, working test infrastructure. PYTHONPATH-only override (the original TD-2 plan) doesn't survive the subprocess boundary because capture-on-stop.sh hardcodes its own PYTHONPATH. Removing the seam would invalidate feature 104's test scripts. Adding a `CLAUDE_CODE_DEV_MODE` guard (FR-5) is a small hardening that preserves the seam's utility while reducing the production-code surface to "no-op when dev-mode flag unset".

**Validation:** AC-1.1 (TD-2 amendment present) + AC-5.1 (guard present) + AC-5.2 (existing tests still pass with guard).

### TD-3: Refactor test_category_mapping into 2 functions, not 4

**Decision:** Split into 2 functions (one per category branch), not 4 (one per assertion).

**Rationale:** The user-direction filter says "primary feature + primary/secondary defense; NO edge-case hardening". Splitting into 4 functions would over-fragment. Two functions per category branch matches the actual semantic boundary (anti-patterns vs preference-statement), each with its own setup/teardown.

### TD-4: Test runner wiring uses external invocation, not function inlining

**Decision:** test-hooks.sh wires the 3 external test scripts via path invocation (`"${SCRIPT_DIR}/test-foo.sh"`), not by inlining each test as a bash function.

**Rationale:** The 3 external scripts are already self-contained with their own log_test/log_pass/log_fail helpers and their own test runners. Inlining would duplicate that scaffolding. External invocation keeps each test script independently runnable AND wired into the unified runner. Combining their non-zero exit into the wrapper's TESTS_FAILED counter is sufficient signal — the external scripts print their own per-test details.

### TD-5: Skip Step 0 research (domain expert path)

**Decision:** Per YOLO mode, skip codebase-explorer and internet-researcher dispatches.

**Rationale:** Direct prior art is features 104 + 105 themselves. The patterns being extended (sed-extract from 104 TD-1, codex-routing exclusion from 103, evidence-commit-stance from 105) are all in scope of this feature. There is no external industry pattern to research.

### TD-6: FR-1b dev_guide section is additive, not modifying existing content

**Decision:** Add a NEW `## Committed vs gitignored evidence paths` subsection to `docs/dev_guides/component-authoring.md`. Do not modify existing content.

**Rationale:** Minimum-intrusion. The existing component-authoring.md content is unrelated to evidence paths. Adding a new subsection at the end is the cleanest way to satisfy AC-1.2 without affecting other sections.

## Risks

### R-1: test-hooks.sh exit-code propagation

**Risk:** TD-4's `"${SCRIPT_DIR}/test-foo.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))` increments by 1 on any non-zero exit, regardless of how many tests inside that script failed. The wrapper counter doesn't reflect actual test count.

**Mitigation:** This is acceptable for the wrapper's "did the suite pass" signal — TESTS_FAILED ≥ 1 means at least one external test failed and the wrapper exits non-zero. The external script's own output shows which specific tests failed. AC-2.2 only requires the wrapper exit 0 when all tests pass, which this satisfies.

**Severity:** Low.

### R-2: sed-extract regex ambiguity if function bodies contain unbalanced `}`

**Risk:** The sed-extract regex `/^{name}()/,/^}/p` uses `^}` (closing brace at column 0) as the end-marker. If `cleanup_stale_mcp_servers` body contains a `^}` at column 0 (e.g., end of a multi-line if-block), the extract terminates early.

**Mitigation:** Verified at design time: both target functions in session-start.sh have indented inner `}` (e.g., `    }`) and a single `^}` at the actual function end. The pattern works correctly. Same as feature 104 TD-1's existing usage.

**Severity:** Low (verified non-issue for these specific functions).

### R-3: Backlog row regex assumes consistent format

**Risk:** AC-8.1's grep regex assumes all 10 backlog rows start with `- **#0031N**` (markdown bullet + bold ID). If any row uses a different format (e.g., `| 00310 | ...` table form), the AC fails despite correct annotation.

**Mitigation:** Verified at design time: rows #00310-#00319 are all in the "Pre-Release QA Findings" sections at the bottom of backlog.md, all using `- **#0031N**` bullet format. Older rows use table format but are out of scope.

**Severity:** Low.

### R-4: validate.sh log_info reorder may affect other parsing

**Risk:** Some downstream tool may parse validate.sh output line-order. Reordering the two `log_info` lines could break parsers expecting a specific order.

**Mitigation:** No known downstream parser depends on the order of these specific log_info lines (both are success-path informational output). The check order is the actual signal; the message order is the cosmetic artifact this fix corrects.

**Severity:** Low.

### R-5: feature 104 design.md TD-2 amendment is documentation-only

**Risk:** Amending feature 104's design.md is editing a sealed artifact (already merged + released). Some processes may expect feature artifacts to be immutable post-merge.

**Mitigation:** No such immutability convention exists in this project. Design.md is documentation; amendment is appropriate when scope-decisions are revisited. Amendment is annotated with feature reference: `**Amendment (feature 106 #00310):**`. Future readers see both the original TD-2 and the amendment.

**Severity:** Low.

### R-6: external script stderr swallowing in test-hooks.sh

**Risk:** TD-4's pipe pattern `"${SCRIPT_DIR}/test-foo.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))` runs in the same process; stderr passes through to the wrapper's stdout. Should be fine. But if the external script uses `set -e` and exits early, the wrapper still continues (the `||` clause catches non-zero).

**Mitigation:** Verified: the 3 external test scripts use `set -uo pipefail` (NOT `set -e`) and explicit `[[ $TESTS_FAILED -eq 0 ]]` exit pattern. Compatible with the wrapper invocation.

**Severity:** Low.

## File Change Summary

| File | Change Type | FR | Description |
|------|-------------|-----|-------------|
| `plugins/pd/hooks/capture-on-stop.sh` | Modify | FR-5 | Add CLAUDE_CODE_DEV_MODE guard to test-injection seam |
| `plugins/pd/hooks/tests/test-hooks.sh` | Modify | FR-2 | Add 3 external-script invocations near end of main() |
| `plugins/pd/hooks/tests/test-capture-on-stop.sh` | Modify | FR-4 | Split test_category_mapping into 2 functions |
| `plugins/pd/hooks/tests/test-session-start.sh` | Modify | FR-3 | Add 5 sed-extract tests for cleanup_stale_mcp_servers |
| `plugins/pd/hooks/tests/test_session_start_cleanup.sh` | Delete | FR-3 | Underscored file deleted post-merge |
| `plugins/pd/commands/secretary.md` | Modify | FR-7 | Drop "(line 726)" from R-8 note |
| `validate.sh` | Modify | FR-6 | Swap 2 log_info lines in codex-routing block |
| `docs/features/104-batch-b-test-hardening/design.md` | Modify | FR-1a | Append TD-2 amendment paragraph |
| `docs/dev_guides/component-authoring.md` | Modify | FR-1b | Add new subsection on evidence paths |
| `docs/dev_guides/commands-reference.md` | Modify | FR-2 | Reference consolidated test runner |
| `docs/backlog.md` | Modify | FR-8 | Annotate 10 rows #00310-#00319 |

11 file changes total (10 modifies + 1 delete).

## Test Strategy

| Layer | What to test | Where |
|-------|--------------|-------|
| Static contract | All 8 FRs satisfy their AC verification snippets | Inline AC checks in tasks.md |
| Static contract | Backlog rows #00310-#00319 annotated with closing rationale | AC-8.1 grep loop |
| Regression | Existing hook tests (test-hooks.sh) pass after FR-2 wiring | `bash plugins/pd/hooks/tests/test-hooks.sh` |
| Regression | Consolidated test-session-start.sh runs both function tests | AC-3.4 |
| Regression | test-capture-on-stop.sh refactored tests pass | AC-4.2 |
| Regression | validate.sh exits 0 with reordered log_info | AC-6.2 |
| Regression | pattern_promotion pytest passes | `cd plugins/pd && .venv/bin/python -m pytest hooks/lib/pattern_promotion/` |
| Regression | capture-on-stop.sh seam still honored when CLAUDE_CODE_DEV_MODE=1 | AC-5.2 (test scripts must export the flag) |

## Interfaces

### I-1: FR-5 capture-on-stop.sh guard (recommended inline form)

Existing lines 42-44:
```bash
[[ -n "${PD_TEST_WRITER_PYTHONPATH:-}" ]] && writer_pythonpath="$PD_TEST_WRITER_PYTHONPATH"
[[ -n "${PD_TEST_WRITER_PYTHON:-}" ]] && writer_python="$PD_TEST_WRITER_PYTHON"
```

Replace with inline-guarded form:
```bash
# Feature 106 FR-5: gate test-injection seam on CLAUDE_CODE_DEV_MODE so production behavior is unchanged when flag is unset.
[[ "${CLAUDE_CODE_DEV_MODE:-}" == "1" ]] && [[ -n "${PD_TEST_WRITER_PYTHONPATH:-}" ]] && writer_pythonpath="$PD_TEST_WRITER_PYTHONPATH"
[[ "${CLAUDE_CODE_DEV_MODE:-}" == "1" ]] && [[ -n "${PD_TEST_WRITER_PYTHON:-}" ]] && writer_python="$PD_TEST_WRITER_PYTHON"
```

The existing comment "# Feature 104 test-injection seam:" stays. Add the FR-5 comment above the two updated lines.

### I-2: FR-2 test-hooks.sh wiring (insertion location)

Insert before `echo "=========================================="` block in `main()` (currently around line 1750+). New block:
```bash
echo ""
echo "--- External Test Scripts (feature 106 FR-2) ---"
echo ""

if [[ -x "${SCRIPT_DIR}/test-tag-correction.sh" ]]; then
    echo "Running test-tag-correction.sh..."
    "${SCRIPT_DIR}/test-tag-correction.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))
fi
if [[ -x "${SCRIPT_DIR}/test-capture-on-stop.sh" ]]; then
    echo "Running test-capture-on-stop.sh..."
    "${SCRIPT_DIR}/test-capture-on-stop.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))
fi
if [[ -x "${SCRIPT_DIR}/test-session-start.sh" ]]; then
    echo "Running test-session-start.sh..."
    "${SCRIPT_DIR}/test-session-start.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))
fi
```

The `[[ -x ... ]]` guard makes the wiring resilient to future test-script refactors (e.g., if a script is renamed/removed, the wrapper degrades gracefully rather than failing on a missing file).

### I-3: FR-3 test-session-start.sh structure (after consolidation)

Top of file (preserve):
```bash
#!/bin/bash
# Feature 104 FR-6: integration test for session-start.sh
# cleanup_stale_correction_buffers + cleanup_stale_mcp_servers (consolidated by feature 106 FR-3)
set -uo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
HOOKS_DIR=$(dirname "$SCRIPT_DIR")
# ... color codes, log helpers ...
```

Test-1 (existing, AC-6.1, correction-buffers): keep verbatim.

Tests 2-6 (new, mcp-servers): copy from `test_session_start_cleanup.sh` with the copy-paste extraction REPLACED by sed-extract:
```bash
test_stale_pid_file_removed() {
    log_test "Stale PID file (non-running PID) is removed"
    # ... fixture setup ...
    # Sed-extract cleanup_stale_mcp_servers (replaces copy-paste from underscored file)
    local fn_tmpfile
    fn_tmpfile=$(mktemp -t pd-fn-extract.XXXXXX)
    sed -n '/^cleanup_stale_mcp_servers()/,/^}/p' "${HOOKS_DIR}/session-start.sh" > "$fn_tmpfile"
    source "$fn_tmpfile"
    # ... existing assertion logic (PID file removal etc.) ...
    rm -f "$fn_tmpfile"
}
# ... test_missing_pid_dir, test_invalid_pid_content, test_non_orphaned_process, test_orphan_double_fork ...
```

Each test uses its own `fn_tmpfile` (separate sed-extract per test, so each is hermetic). Or share one extract at the top via a setup helper. Either approach satisfies AC-3.2 grep ≥1 for each pattern.

Bottom of file (call all 6 tests):
```bash
test_cleanup_stale_correction_buffers
test_stale_pid_file_removed
test_missing_pid_dir
test_invalid_pid_content
test_non_orphaned_process
test_orphan_double_fork
```

Then results summary, exit code per `[[ $TESTS_FAILED -eq 0 ]]`.

### I-4: FR-4 test_category_mapping refactor (test-capture-on-stop.sh)

Existing (line 188 onwards):
```bash
test_category_mapping() {
    log_test "AC-5.4a: category mapping (anti-patterns + patterns branches)"
    # ... setup ...
    # ... assert anti-patterns case ...
    # ... teardown 1 ...
    # ... setup 2 ...
    # ... assert patterns case ...
    # ... teardown 2 ...
}
```

Replace with two functions:
```bash
test_category_mapping_anti_patterns() {
    log_test "AC-5.4a: category mapping anti-patterns branch"
    # ... setup, assert anti-patterns case, teardown ...
}

test_category_mapping_preference() {
    log_test "AC-5.4a: category mapping preference (patterns) branch"
    # ... setup, assert patterns case, teardown ...
}
```

Update bottom-of-file invocation:
- Remove: `test_category_mapping`
- Add: `test_category_mapping_anti_patterns; test_category_mapping_preference`

### I-5: FR-6 validate.sh log_info swap (exact diff)

Find the two log_info lines at the end of the codex-routing block. Current order:
```bash
[ "$codex_routing_allowlist_violations" = "0" ] && log_info "Codex routing coverage allowlist validated (11 expected files)"

[ "$codex_routing_exclusion_violations" = "0" ] && log_info "Codex Reviewer Routing exclusions validated"
```

New order (swap):
```bash
[ "$codex_routing_exclusion_violations" = "0" ] && log_info "Codex Reviewer Routing exclusions validated"

[ "$codex_routing_allowlist_violations" = "0" ] && log_info "Codex routing coverage allowlist validated (11 expected files)"
```

### I-6: FR-7 secretary.md R-8 note (exact edit)

Current:
```markdown
**Security exclusion:** This command does NOT dispatch `pd:security-reviewer`, so the codex-routing exclusion does not need to be enforced here. The exclusion is enforced wherever `pd:security-reviewer` IS dispatched (implement, finish-feature). Note: Dynamic agent dispatch at Step 7 DELEGATE (line 726) is a runtime-templated routing, not a static reviewer dispatch; codex routing is not applied at that delegation site.
```

Updated (drop "(line 726)"):
```markdown
**Security exclusion:** This command does NOT dispatch `pd:security-reviewer`, so the codex-routing exclusion does not need to be enforced here. The exclusion is enforced wherever `pd:security-reviewer` IS dispatched (implement, finish-feature). Note: Dynamic agent dispatch at Step 7 DELEGATE is a runtime-templated routing, not a static reviewer dispatch; codex routing is not applied at that delegation site.
```

### I-7: FR-1a TD-2 amendment text (verbatim insert)

Append to `docs/features/104-batch-b-test-hardening/design.md` immediately after the existing TD-2 body (before TD-3 heading or end of TD section):

```markdown
**Amendment (feature 106 #00310):** The canonical test-injection mechanism is the `PD_TEST_WRITER_PYTHONPATH` / `PD_TEST_WRITER_PYTHON` env-var seam at `capture-on-stop.sh:42-44`. PYTHONPATH-only override (the original TD-2 design) does not survive the subprocess boundary because `capture-on-stop.sh` re-assigns `PYTHONPATH` before invoking the writer. The env-var seam is gated by `CLAUDE_CODE_DEV_MODE=1` (added by feature 106 FR-5) so production behavior is unchanged when the dev-mode flag is unset.
```

### I-8: FR-1b dev_guide subsection (verbatim insert)

Append to `docs/dev_guides/component-authoring.md` (or insert at a topically-appropriate location):

```markdown
## Committed vs gitignored evidence paths

When designing a feature that prescribes evidence files (terminal output of manual checklists, QA gate procedure logs, etc.) be committed at a specific path, verify the target path's `.gitignore` status FIRST. Common pitfall: `agent_sandbox/` is the project convention for agent-generated non-workflow content (per CLAUDE.md), but it is gitignored at the repo root.

If evidence files MUST be committed for QA-gate verification:
- Place them under `docs/features/{id}-{slug}/.qa-gate-evidence.md` or similar (committed by default).
- Or under any other non-gitignored path verified via `git check-ignore <path>`.

Precedent: feature 105 originally prescribed `agent_sandbox/2026-05-06/feature-105-evidence/` in design I-5 ("Evidence files ARE committed..."), discovered at implement-time that the path was gitignored, resolved by committing the procedure outputs to `.qa-gate-evidence.md` in the feature directory. See `docs/features/105-codex-routing-coverage-extension/.qa-gate-evidence.md`.
```

### I-9: FR-8 backlog annotation patterns

For each backlog row #00310-#00319, append the closing rationale per the disposition table in spec:

| ID | Append text |
|---|---|
| #00310 | ` (closed: documented in feature:106-qa-findings-batch-cleanup TD-2 amendment)` |
| #00311 | ` (closed: implemented in feature:106-qa-findings-batch-cleanup FR-2)` |
| #00312 | ` (closed: implemented in feature:106-qa-findings-batch-cleanup FR-3)` |
| #00313 | ` (closed: implemented in feature:106-qa-findings-batch-cleanup FR-4)` |
| #00314 | ` (closed: subsumed by #00312 in feature:106-qa-findings-batch-cleanup FR-3)` |
| #00315 | ` (closed: implemented in feature:106-qa-findings-batch-cleanup FR-5)` |
| #00316 | ` (closed: implemented in feature:106-qa-findings-batch-cleanup FR-6)` |
| #00317 | ` (closed: wontfix — pre-existing pattern, future-audit candidate)` |
| #00318 | ` (closed: implemented in feature:106-qa-findings-batch-cleanup FR-7)` |
| #00319 | ` (closed: documented in docs/dev_guides/component-authoring.md, feature:106)` |

## Verification Checks (V-1)

Pre-design verification confirming spec assumptions (already performed at design time):
- `docs/dev_guides/component-authoring.md` exists (FR-1b target file). ✓
- `cleanup_stale_mcp_servers()` is at line 227 of `plugins/pd/hooks/session-start.sh`. ✓
- `cleanup_stale_correction_buffers()` is at line 282 of `plugins/pd/hooks/session-start.sh`. ✓
- `test_session_start_cleanup.sh` covers `cleanup_stale_mcp_servers` (5 tests, copy-paste extraction). ✓
- `test-session-start.sh` covers `cleanup_stale_correction_buffers` (1 test, sed-extract). ✓
- `test-hooks.sh` defines all current tests inline as bash functions; no current external-script invocations (FR-2 adds the wiring). ✓
- `test_category_mapping` is at line 188 of `test-capture-on-stop.sh` (NOT `test-tag-correction.sh` per backlog typo). ✓

## Open Questions

None. All ambiguities resolved during 2 spec-review iterations.

## Out of Scope

Per spec "Out of Scope" section, plus:
- Reorganizing test-hooks.sh structure beyond the FR-2 wiring (e.g., moving inline tests to external scripts).
- Refactoring validate.sh structure beyond FR-6's specific log_info reorder.
- Adding new test infrastructure beyond FR-2 / FR-3 / FR-4.
- Modifying `agent_sandbox/` behavior (it stays gitignored; FR-1b just documents the convention).
- Touching feature 105's artifacts (only feature 104's design.md TD-2 is amended in FR-1a).
