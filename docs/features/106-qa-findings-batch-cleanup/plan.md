# Plan: QA Findings Batch Cleanup

## Overview

11 file changes (10 modifies + 1 delete) implementing 8 FRs across 11 tasks. All edits have verbatim diffs in design I-1..I-9. Direct-orchestrator implement (no per-task implementer dispatch).

## Approach

Each task is a small, independent surgical edit at a specific anchor. Implementation follows the verbatim diffs in design.md interfaces (I-1 through I-9). Most tasks are 5-10 minutes; the consolidation (T3, FR-3) is the largest at ~15 minutes.

**TDD ordering:** No new test infrastructure required (tests already exist from features 104, 105). Refactor + consolidation tasks (T3, T4) come BEFORE runner-wiring (T2) so the wiring picks up the consolidated test files in their final state.

## Tasks

### Phase 1: Independent Code Edits (parallelizable group A — T1, T5-T8)

**T1 (FR-5, #00315): Add CLAUDE_CODE_DEV_MODE guard + test export**
- Why this item: implements design C1 / FR-5; defensive guard so production behavior is unchanged when dev-mode flag unset (per #00315).
- Why this order: independent — Group A; must precede T2 (runner wiring) so test-capture-on-stop.sh runs cleanly when invoked by the wrapper.
- Files: `plugins/pd/hooks/capture-on-stop.sh` AND `plugins/pd/hooks/tests/test-capture-on-stop.sh`
- Edit 1 (production hook): per design I-1 — replace seam lines with inline-guarded form (each line gets `[[ "${CLAUDE_CODE_DEV_MODE:-}" == "1" ]] &&` prefix). Add `# Feature 106 FR-5:` comment above.
- Edit 2 (test script): add `export CLAUDE_CODE_DEV_MODE=1` near the top of `test-capture-on-stop.sh` (after `set -uo pipefail`, before any test setup) so the FR-5 guard honors the seam during tests. Without this export, the seam stays no-op when tests run, and AC-5.2 / AC-2.2 fail.
- DoD: AC-5.1 verification snippet (awk-extract seam section, grep for `CLAUDE_CODE_DEV_MODE`) prints PASS; `bash plugins/pd/hooks/tests/test-capture-on-stop.sh` exits 0 (confirms AC-5.2 — guard + export work together).
- Complexity: Simple.

**T5 (FR-6, #00316): Swap validate.sh log_info ordering**
- Why this item: implements design C5 / FR-6; cosmetic ordering fix per #00316.
- Why this order: independent — Group A; can run before/after any other Group-A task.
- File: `validate.sh`
- Edit: per design I-5 — swap the two `log_info` lines so "exclusions validated" prints before "allowlist validated".
- DoD: AC-6.1 line-order check prints PASS; `./validate.sh` exits 0.
- Complexity: Simple.

**T6 (FR-7, #00318): Drop "(line 726)" from secretary.md R-8 note**
- Why this item: implements design C6 / FR-7; remove stale line-number reference per #00318.
- Why this order: independent — Group A.
- File: `plugins/pd/commands/secretary.md`
- Edit: per design I-6 — single-line edit removing `(line 726)` parenthetical, anchor text "Step 7 DELEGATE" preserved.
- DoD: AC-7.1 negative-grep prints PASS; AC-7.2 anchor-grep prints PASS.
- Complexity: Simple.

**T7 (FR-1a, #00310): Append TD-2 amendment to feature 104 design.md**
- Why this item: implements design C7 / FR-1a; canonicalize the test-injection seam per #00310.
- Why this order: independent — Group A; documentation update touches a sealed feature 104 artifact (per design R-5).
- File: `docs/features/104-batch-b-test-hardening/design.md`
- Edit: per design I-7 — append the verbatim TD-2 amendment paragraph to the existing TD-2 section.
- DoD: AC-1.1 verification snippet (grep for `PD_TEST_WRITER_PYTHONPATH` AND `PD_TEST_WRITER_PYTHON` within 30 lines after `### TD-2`) prints PASS.
- Complexity: Simple.

**T8 (FR-1b, #00319): Add dev_guide subsection on evidence paths**
- Why this item: implements design C8 / FR-1b; document the gitignore-verification process lesson per #00319.
- Why this order: independent — Group A.
- File: `docs/dev_guides/component-authoring.md`
- Edit: per design I-8 — append the verbatim "## Committed vs gitignored evidence paths" subsection.
- DoD: AC-1.2 verification (grep for `agent_sandbox` AND `gitignore`/`gitignored` within same section) prints PASS.
- Complexity: Simple.

### Phase 2: Test Refactor + Consolidation (sequential — T3 before T4)

**T3 (FR-3, #00312, subsumes #00314): Consolidate test-session-start files**
- Why this item: implements design C3 / FR-3; consolidate two files for the same source script per #00312, applying sed-extract from feature 104 TD-1 to subsume #00314.
- Why this order: must precede T2 (per TDD-ordering note in Approach: runner wiring picks up the consolidated test file in its final state); parallel with T4 (different file).
- Files modified: `plugins/pd/hooks/tests/test-session-start.sh` (expanded)
- Files deleted: `plugins/pd/hooks/tests/test_session_start_cleanup.sh`
- Edit: per design I-3 — copy 5 mcp-server tests from underscored file into hyphenated file, replacing each test's copy-paste extraction with sed-extract. Update bottom-of-file invocation to call all 6 tests. Delete underscored file.
- DoD:
  - AC-3.1: hyphenated file exists, underscored file does not, both function names referenced
  - AC-3.2: sed-extract pattern present for both functions
  - AC-3.3: ≥6 test functions in consolidated file
  - AC-3.4: `bash plugins/pd/hooks/tests/test-session-start.sh` exits 0
- Complexity: Medium (largest task — sed-extract conversion of 5 tests).

**T4 (FR-4, #00313): Refactor test_category_mapping in test-capture-on-stop.sh**
- Why this item: implements design C4 / FR-4; split interleaved-teardown function per #00313.
- Why this order: must precede T2 (runner wiring depends on consolidated test state); parallel with T3.
- File: `plugins/pd/hooks/tests/test-capture-on-stop.sh`
- Edit: per design I-4 — split `test_category_mapping` (line 188) into `test_category_mapping_anti_patterns` and `test_category_mapping_preference`, each with own setup/teardown. Update bottom-of-file invocation.
- DoD:
  - AC-4.1: ≥2 test functions matching the new naming pattern
  - AC-4.2: `bash plugins/pd/hooks/tests/test-capture-on-stop.sh` exits 0
- Complexity: Medium.

### Phase 3: Runner Wiring (depends on T3 + T4)

**T2 (FR-2, #00311): Wire 3 test scripts into test-hooks.sh runner + commands-reference.md**
- Why this item: implements design C2 / FR-2; wire 3 standalone test scripts into the unified runner per #00311.
- Why this order: depends on T3 (consolidated test-session-start.sh) and T4 (refactored test-capture-on-stop.sh) — wiring must reference final test state.
- Files: `plugins/pd/hooks/tests/test-hooks.sh`, `docs/dev_guides/commands-reference.md`
- Edit (test-hooks.sh): per design I-2 — insert 3-script invocation block near end of `main()`, before result-summary block. Use `[[ -x ... ]]` guards.
- Edit (commands-reference.md): add a one-line reference to `bash plugins/pd/hooks/tests/test-hooks.sh` running the consolidated suite.
- DoD:
  - AC-2.1: tightened invocation grep finds ≥1 match per script
  - AC-2.2: `bash plugins/pd/hooks/tests/test-hooks.sh` exits 0
  - AC-2.3: `commands-reference.md` references `test-hooks.sh`
- Complexity: Simple.

### Phase 4: Validation (BEFORE backlog annotations — per plan-reviewer iter 1 warning)

**T10: Run validate.sh + all hook tests + pattern_promotion pytest**
- Why this item: gate all FR-implementing work; ensures rolled-back state is clean if validation fails.
- Why this order: depends on all FR-implementing tasks (T1-T8); precedes T9 so backlog annotations only land after validation confirms closure.
- Run `./validate.sh` → expect exit 0
- Run `bash plugins/pd/hooks/tests/test-hooks.sh` → expect exit 0 (now includes 3 external scripts)
- Run `cd plugins/pd && .venv/bin/python -m pytest hooks/lib/pattern_promotion/ -q` → expect exit 0
- DoD: all 3 commands pass.
- Complexity: Simple.

### Phase 5: Backlog Annotations (after T10 passes)

**T9 (FR-8): Annotate 10 backlog rows with closing rationale**
- Why this item: implements FR-8; closes #00310-#00319 backlog tracking per design C9.
- Why this order: depends on T10 (validation passed) — annotations should only land if all FR-implementations are validated; otherwise rollback leaves backlog mis-annotated.
- File: `docs/backlog.md`
- Edit: per design I-9 — append closing-rationale text to each of 10 rows (#00310-#00319) using the disposition table.
- DoD: AC-8.1 grep loop confirms all 10 rows match the closing pattern.
- Complexity: Simple.

## Dependency Graph

```
T1 (capture-on-stop guard + test export) ──┐
T5 (validate.sh log_info) ─────────────────┤
T6 (secretary.md R-8 drop) ────────────────┼─── all parallelizable (different files)
T7 (104 design TD-2) ──────────────────────┤
T8 (component-authoring) ──────────────────┘
                                           │
T3 (test-session-start consolidation) ─────┐ both parallel — different files
T4 (test_category_mapping refactor) ───────┘ both must precede T2
                                           │
T2 (test-hooks.sh wiring) ─── depends on T3 + T4 (wiring references final test state)
                                           │
T10 (validation) ─────────── depends on T1-T8 (all FR-implementing tasks)
                                           │
T9 (backlog annotations) ─── depends on T10 (only annotate after validation confirms closure)
```

## Parallel Execution Groups

- **Group A (5 tasks parallelizable):** T1, T5, T6, T7, T8 — different files, no overlap.
- **Group B (2 tasks parallelizable):** T3, T4 — different test files.
- **Sequential:** Group A + Group B → T2 → T10 → T9.

## Risks Inherited from Design

R-1 through R-6 from design.md apply unchanged. All low-severity. No new risks introduced by the plan.

## Rollback Strategy

If any task fails or T10 validation fails, revert via `git reset --hard HEAD~N` where N is the commit count for this feature branch. Branch deletion via `/pd:abandon-feature` if rollback is permanent. The 11 file changes are atomic and small; no cascading dependencies.
