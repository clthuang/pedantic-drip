# Implementation Plan: Comprehensive Prompt Refactoring

## Overview

This plan translates the 5-phase design architecture (Foundation → Tooling → Structural Changes → Content Sweep → Enforcement + Verification) into ordered implementation steps with dependencies, TDD anchors, and verification gates.

## Execution Order

Steps are ordered by dependency. Each step lists its AC coverage, input files, output files, and verification method.

---

## Phase 0: Baseline Capture

### Step 0.1: Record Pre-Refactor Baseline Scores and Outputs
- **AC**: AC-13 (prerequisite)
- **Files**: 5 pilot files: `agents/design-reviewer.md`, `commands/secretary.md`, `skills/brainstorming/SKILL.md`, `commands/review-ds-code.md`, `commands/review-ds-analysis.md`
- **Action**: Before any modifications:
  1. Run `/iflow:promptimize` on each of the 5 pilot files and record scores in `docs/dev_artifacts/workitems/033-comprehensive-prompt-refactor/baseline-scores.md`
  2. For each pilot file, capture representative test outputs:
     - `design-reviewer.md`: run with 1 complete design input, capture JSON output
     - `secretary.md`: run 5 routing prompts (direct agent, ambiguous, help, orchestrate, no-match), capture agent selection for each
     - `brainstorming/SKILL.md`: run with 1 new topic, capture stage progression
     - `review-ds-code.md`: run with 1 mixed-quality notebook, capture JSON output
     - `review-ds-analysis.md`: run with 1 analysis with statistical pitfalls, capture JSON output
  3. Store test inputs as reproducible artifacts in `docs/dev_artifacts/workitems/033-comprehensive-prompt-refactor/test-inputs/` directory (e.g., sample design document, 5 secretary routing prompts as text, sample notebook description, sample analysis description). These stored inputs are reused in Step 5.3 for identical comparison.
  4. Store all baseline outputs in `baseline-scores.md` for Phase 5 comparison
- **Test**: baseline-scores.md exists with 5 promptimize scores and representative outputs. test-inputs/ directory exists with stored inputs per pilot file.
- **Dependencies**: None (must be first step — before any file modifications)
- **Complexity**: Medium (requires running promptimize 5 times + representative inputs)
- **Commit**: After completion — `iflow: capture baseline scores for 033 pilot files`

---

## Phase 1: Foundation (Reference File Updates)

### Step 1.1: Update scoring-rubric.md — Add Cache-Friendliness Dimension
- **AC**: AC-1 (partial)
- **File**: `plugins/iflow/skills/promptimize/references/scoring-rubric.md`
- **Action**: Add `Cache-friendliness` as 10th row to Behavioral Anchors table with anchors: Pass (3) = all static before dynamic, Partial (2) = 1-2 static blocks after dynamic, Fail (1) = freely interleaved. Add to Component Type Applicability table (evaluated for all types).
- **Test**: Read file, confirm 10 rows in anchors table, confirm `cache_friendliness` appears, confirm applicability row exists.
- **Dependencies**: None (Phase 1 modifies reference files, not pilot files — can start parallel with Step 0.1)
- **Complexity**: Simple

### Step 1.2: Update prompt-guidelines.md — Fill 3 Gaps
- **AC**: AC-2
- **File**: `plugins/iflow/skills/promptimize/references/prompt-guidelines.md`
- **Action**: Add 3 sections after "Plugin-Specific Patterns": (1) Tool Use Prompting — structured parameter descriptions, sequencing for multi-tool workflows [cite Anthropic docs], (2) System vs Human Turn Placement — static in system, dynamic in human, reminders at bottom [cite Claude 4.x], (3) Negative Framing Guidance — prefer "Do X" over "Don't do Y", exceptions for PROHIBITED sections [cite Claude 4.x]. Update `## Last Updated` date and Update Log.
- **Test**: Read file, confirm 3 new sections exist with Anthropic citations.
- **Dependencies**: None (same as Step 1.1 — reference files, not pilot files)
- **Complexity**: Simple

### Step 1.3: Update component-authoring.md — Promptimize Gate + Terminology
- **AC**: AC-11 (partial), AC-9 (partial)
- **File**: `docs/dev_guides/component-authoring.md`
- **Action**: Add `[ ] Run promptimize on new/modified component files` to Quality Standards / Validation Checklist. Add "Terminology Convention" section defining Stage/Step/Phase usage per I-8 contract.
- **Test**: Read file, confirm promptimize checklist item, confirm terminology section with all 3 terms defined.
- **Dependencies**: None (same as Step 1.1 — reference files, not pilot files)
- **Complexity**: Simple

**Phase 1 gate**: Steps 1.1-1.3 are independent of each other and can start parallel with Step 0.1 (Phase 1 modifies only reference files, not pilot files). Step 0.1 must complete before Phase 2 (which modifies promptimize files that would change scoring behavior). All Phase 1 steps must also complete before Phase 2.
**Commit**: After Phase 1 completion — `iflow: update foundation reference files (rubric, guidelines, authoring)`

---

## Phase 2: Tooling (Promptimize Updates + Batch Script)

### Step 2.1a: Update test-promptimize-content.sh — 9→10 Dimension Assertions (TDD Red)
- **AC**: AC-1 (test alignment)
- **File**: `plugins/iflow/hooks/tests/test-promptimize-content.sh`
- **Action**: Update all "9" dimension references to "10", denominator from 27 to 30, and grep patterns to include `Cache`. Use function names as anchors (not line numbers — they may shift). All functions listed below by name:
  - `test_rubric_has_exactly_9_dimensions` → rename to `test_rubric_has_exactly_10_dimensions`, update grep pattern to add `|Cache` (e.g., `(Structure|...|Context|Cache)`), update assert from `9` to `10`
  - `test_scoring_formula_max_denominator_is_27` → rename to `test_scoring_formula_max_denominator_is_30`, update grep pattern to add `|Cache`, update assert from `9` to `10` and denominator from `27` to `30`
  - `test_cmd_validates_exactly_9_dimensions_in_phase1` → rename to `test_cmd_validates_exactly_10_dimensions_in_phase1`, update "exactly 9" to "exactly 10"
  - `test_cmd_lists_all_9_canonical_dimension_names` → rename to `test_cmd_lists_all_10_canonical_dimension_names`, add `cache_friendliness` to expected list, update count to 10
  - `test_skill_lists_all_9_dimension_names` → rename to `test_skill_lists_all_10_dimension_names`, add `cache_friendliness`, update count to 10
  - `test_skill_canonical_name_mapping_table_has_9_entries` → rename to `test_skill_canonical_name_mapping_table_has_10_entries`, add `cache_friendliness`, update count to 10
  - `test_cmd_score_formula_contains_27_and_100` → rename to `test_cmd_score_formula_contains_30_and_100`, update grep from `'27'` to `'30'`, update test description
  - Update ALL runner invocations to new function names (grep for old function names to find all references)
- **Test**: Run `bash plugins/iflow/hooks/tests/test-promptimize-content.sh` — tests FAIL (Red) because rubric/SKILL.md/command still say 9.
- **Dependencies**: None (Red step — update tests first, expect them to fail)
- **Complexity**: Simple

### Step 2.1b: Update promptimize SKILL.md — 10 Dimensions (TDD Green)
- **AC**: AC-1 (partial)
- **File**: `plugins/iflow/skills/promptimize/SKILL.md`
- **Action**: Add `cache_friendliness` as 10th dimension in Phase 1 evaluation list (after `context_engineering`). Add to canonical dimension name mapping table. Update text patterns (line numbers are approximate — use text-match search, e.g. grep for "Evaluate all 9" and "exactly 9 entries"):
  - ~Line 58: "Evaluate all 9 dimensions" → "Evaluate all 10 dimensions"
  - ~Line 117: "exactly 9 entries" → "exactly 10 entries"
- **Test**: Grep for "all 10 dimensions" (expect 1 match at line 58), grep for "exactly 10 entries" (expect 1 match at line 117), grep for "cache_friendliness" (expect ≥2 matches).
- **Dependencies**: Step 1.1 (rubric must define the dimension first), Step 2.1a (tests updated to expect 10)
- **Complexity**: Simple

### Step 2.2: Update promptimize.md Command — Denominator 30 (TDD Green)
- **AC**: AC-1 (partial), AC-6 (partial)
- **File**: `plugins/iflow/commands/promptimize.md`
- **Action**: Step 4c validation: "exactly 9" → "exactly 10", add `cache_friendliness` to canonical names. Step 5 preamble: "Sum all 9 dimension scores" → "Sum all 10 dimension scores" (~line 145). Step 5 formula: `round((sum/27)*100)` → `round((sum/30)*100)`, update denominator reference 27→30. Add trivial-math exception comment: `<!-- Trivial-math exception: sum of 10 integers [1-3] + divide by 30 + round. Deterministic, no ambiguity. See SC-5 refinement. -->`. Update Step 5 example to show 10 scores: `[3, 2, 1, 3, 2, 3, 3, 3, 2, 2]` → sum = 24, `round((24/30) * 100) = 80`.
- **Test**: Run `bash plugins/iflow/hooks/tests/test-promptimize-content.sh` — all dimension tests now PASS (Green). Grep for "30" in formula area, grep for "exactly 10", confirm trivial-math comment exists.
- **Dependencies**: Step 2.1b (SKILL.md must reference 10 dimensions before command validates against it)
- **Complexity**: Simple

### Step 2.3: Create batch-promptimize.sh — New Script
- **AC**: AC-3
- **File**: `plugins/iflow/scripts/batch-promptimize.sh` (new)
- **Action**: Create shell script per C2.3 and I-3 design. Key details:
  - Discovery: find all `SKILL.md`, `agents/*.md`, `commands/*.md` under `plugins/iflow/`
  - Execution: `claude -p` with inline scoring prompt (verified: `--allowedTools` and `--model` flags confirmed available in current CLI via `claude --help`)
  - Score extraction: Python JSON parsing per I-3 design
  - Score computation: bash arithmetic `$(( (sum * 100 + 15) / 30 ))` — no LLM math
  - Concurrency: max 5 parallel processes, configurable via `--max-parallel`
  - Per-file timeout: 120s via `timeout 120 claude -p ...`
  - Working directory guard: verify `plugins/iflow/skills/promptimize/references/scoring-rubric.md` exists at startup
  - CLI args: `--max-parallel N`, `--threshold N` (default 80), `--help`
- **Test**: (1) Verify script is executable. (2) Run `--help` to confirm argument parsing. (3) Verify rubric guard fails gracefully outside project root. (4) Smoke test: run on 1-2 known files (one agent, one skill) and verify parseable scores are extracted — catches extraction issues before Phase 5 full batch. Full SC-1 verification deferred to Phase 5.
- **Dependencies**: Step 1.1 (rubric must have 10 dimensions for inline prompt)
- **Note**: Step 2.3 does NOT depend on Steps 2.1b or 2.2 — the batch script reads the scoring rubric directly and embeds scoring instructions inline. It bypasses the promptimize command entirely.
- **Complexity**: Medium (new script with parallelism, JSON extraction, error handling)

**Phase 2 gate**: All tests pass. batch-promptimize.sh exists and is syntactically valid.
**Commit**: After Phase 2 completion — `iflow: update promptimize tooling to 10 dimensions + batch script`

---

## Phase 3: Structural Changes

### Step 3.1: Split review-ds-code.md — God Prompt Decomposition
- **AC**: AC-7 (partial), AC-5 (partial)
- **File**: `plugins/iflow/commands/review-ds-code.md`
- **Action**: Replace single `Task()` dispatch with 3-chain sequential dispatch per C3.1 design. Chain 1: [anti-patterns, pipeline quality, code standards]. Chain 2: [notebook quality, API correctness]. Chain 3: synthesis.
  - Add I-7 scope override instruction to Chains 1+2 at TOP of dispatch prompt
  - Add I-1 typed JSON schemas to all 3 chains
  - Add chain error handling (Chain 1/2 failure halts; Chain 3 failure returns degraded)
  - Add I-7 scope leakage filtering instruction between Chain 2 and Chain 3
  - Add output size warning (>5KB)
  - Add explicit chain output handling instruction: "After each chain's Task() completes, extract the JSON object from the agent response (ignore surrounding text). If no valid JSON found, treat as chain failure."
- **Test**: Read file, confirm 3 separate `Task()` dispatch blocks. Grep for "SCOPE RESTRICTION" (expect 2 — Chains 1+2). Grep for typed schema blocks. Grep for chain error handling.
- **Dependencies**: None (independent of Phase 1-2)
- **Complexity**: Complex (dispatch contract change)
- **Commit**: `iflow: split review-ds-code.md into 3-chain dispatch`

### Step 3.2: Split review-ds-analysis.md — God Prompt Decomposition
- **AC**: AC-7 (partial), AC-5 (partial)
- **File**: `plugins/iflow/commands/review-ds-analysis.md`
- **Action**: Same 3-chain pattern as Step 3.1 per C3.2 design. Chain 1: [methodology, statistical validity, data quality]. Chain 2: [conclusion validity, reproducibility]. Chain 3: synthesis. Same scope override, JSON schemas, error handling, and chain output handling patterns.
- **Test**: Same verification as Step 3.1 adapted for analysis review.
- **Dependencies**: None (parallel with Step 3.1)
- **Complexity**: Complex (dispatch contract change)
- **Commit**: `iflow: split review-ds-analysis.md into 3-chain dispatch`

### Step 3.3: Fix Math-in-LLM — Document Exceptions
- **AC**: AC-6
- **Files**: `plugins/iflow/commands/promptimize.md`, `plugins/iflow/commands/secretary.md`
- **Action**: (1) promptimize.md: already handled in Step 2.2 (trivial-math comment). Verify it's present. (2) secretary.md: add code comment `<!-- Trivial-math exception: 5-signal additive integer counting (SC-5). Addition only, no division/rounding. -->` near complexity scoring section. (3) batch-promptimize.sh: already computes in bash (Step 2.3). Verify no LLM math.
- **Test**: Grep promptimize.md for "Trivial-math exception". Grep secretary.md for "Trivial-math exception". Verify batch script uses `$(( ))` for arithmetic.
- **Dependencies**: Step 2.2 (for verification sub-step only — checking promptimize.md has the trivial-math comment). For secretary.md specifically: complete Step 3.4 (cache restructure) first, then add the trivial-math comment — avoids re-editing a file mid-restructure. The secretary.md comment can otherwise proceed in parallel with other Phase 2 work.
- **Complexity**: Simple

### Step 3.4: Restructure 9 Files for Prompt Caching
- **AC**: AC-4
- **Files**: 6 commands (`specify.md`, `design.md`, `create-plan.md`, `create-tasks.md`, `implement.md`, `secretary.md`) + 3 skills (`brainstorming/SKILL.md`, `implementing/SKILL.md`, `retrospecting/SKILL.md`)
- **Action**: For each file, move all static content (reviewer templates, routing tables, schemas, rules, PROHIBITED sections, YOLO overrides) above all dynamic content (user input, feature context, iteration state, $ARGUMENTS). Use block-movement only (no content rewriting) per TD-3.
  - **Secretary.md exception to TD-3**: Secretary.md requires limited content rewriting beyond block movement — extracting static tables into a `## Static Reference Tables` section at top and converting inline table references to named anchors (e.g., "See Fast-Path Table above"). This is the specific reason secretary.md is in the pilot verification set (Step 5.3). All other files use pure block movement.
  - **Secretary.md intermediate verification**: After restructuring secretary.md, immediately run 3 routing prompts (direct agent match, help subcommand, ambiguous request) to catch silent breakage. Do NOT wait for Phase 5 pilot.
  - **Secretary.md final ordering check**: After ALL secretary.md edits complete (Steps 3.3 + 3.4 + 4.1 + 4.2 + 4.3), re-verify static-first ordering before the Phase 4 gate commit. This is necessary because 5 separate editing passes could invalidate the ordering established in Step 3.4.
- **Verification approach**:
  - Pilot files (secretary.md, brainstorming/SKILL.md): full AC-13 behavioral equivalence deferred to Phase 5 Step 5.3
  - Remaining 7 non-pilot files: automated diff check — (a) no lines deleted/added, only moved, (b) dynamic markers after all static content, (c) named static sections before first dynamic marker
- **Test**: For each file, verify static-before-dynamic ordering by confirming all `$ARGUMENTS`, `{feature_path}`, and iteration context references appear after all reviewer template blocks, routing tables, and rule sections.
- **Dependencies**: None (can proceed in parallel with Steps 3.1-3.3)
- **Complexity**: Complex (secretary.md), Medium (other 8 files)
- **Commit**: `iflow: restructure 9 files for prompt caching (static-first ordering)`

**Phase 3 gate**: All structural changes complete. God Prompt splits in place, math exceptions documented, caching restructure done.

---

## Phase 4: Content Sweep

### Step 4.0: Pre-Sweep Audit — Definitive In-Scope File List
- **AC**: AC-8 (prerequisite)
- **Action**: Run the exact exclusion grep to produce a definitive in-scope file list before beginning replacements:
  1. Run `grep -rlEi '\bappropriate\b|\bsufficient\b|\brobust\b|\bthorough\b|\bproper\b|\badequate\b|\breasonable\b' plugins/iflow/{agents,skills,commands} --include='*.md'`
  2. Exclude `*/references/*` paths
  3. For each file, count raw matches and domain-specific matches (compound terms: "sufficient sample", "appropriate statistical test", "sufficient data", "robust standard error")
  4. Produce definitive file list with per-file net match counts
  5. Store in `docs/dev_artifacts/workitems/033-comprehensive-prompt-refactor/adjective-audit.md`
- **Test**: adjective-audit.md exists with exact file list and counts.
- **Dependencies**: Steps 3.4 (caching restructure should be done before content sweep)
- **Note**: This audit runs AFTER cache restructuring (Step 3.4). Block movement preserves content but the ~38 file estimate from the PRD is pre-restructure; this audit produces the authoritative count. Word-boundary regex intentionally excludes derived forms ('appropriateness', 'robustness') per design I-5.
- **Complexity**: Simple

### Step 4.1: Subjective Adjective Removal — Replace All In-Scope Matches
- **AC**: AC-8, SC-2
- **Files**: Files identified in Step 4.0 audit
- **Action**: For each in-scope match from the audit:
  1. Replace adjective with measurable criterion (context-specific — per C4.1 examples)
  2. Verify agent file replacements preserve static-first ordering (SC-10)
  3. For secretary.md: batch all content changes (adjective removal + passive voice + terminology) into a single editing pass to minimize re-edits. Run 3 routing prompts after all secretary.md changes complete.
- **Test**: Re-run grep — expect zero matches (excluding reference files and domain-specific compounds).
- **Dependencies**: Step 4.0 (audit provides definitive file list)
- **Complexity**: Medium (volume of ~38+ files, but each change is small)

### Step 4.2: Passive Voice Fix
- **AC**: AC-10
- **Files**: Affected prompt files (~12 instances)
- **Action**: Review files for passive constructions. Convert each to imperative mood. Example: "JSON should be returned" → "Return JSON".
- **Test**: After fixes, each file should score Pass (3) on `technique_currency` when evaluated by promptimize.
- **Dependencies**: Step 4.1 (adjective removal may touch same files; do adjectives first)
- **Complexity**: Simple

### Step 4.3: Terminology Normalization
- **AC**: AC-9, SC-3
- **Files**: All 85 prompt files + READMEs
- **Action**: (1) Grep for "Stage", "Step", "Phase" across all files. (2) For each instance, verify it conforms to convention: Stage = top-level skill divisions, Step = command sections and skill sub-items, Phase = workflow-state phase names only. (3) Fix all violations. (4) Verify hook scripts referencing phase names by string are unbroken.
- **Test**: Post-fix grep confirms all instances conform. Run hook tests (`bash plugins/iflow/hooks/tests/test-hooks.sh`) to verify hooks unbroken.
- **Dependencies**: Step 4.1 (normalize after adjective removal to capture any terminology introduced by replacements)
- **Complexity**: Medium

**Phase 4 gate**: Content sweep complete. Zero adjectives (SC-2), terminology normalized (SC-3), passive voice fixed (AC-10).
**Commit**: `iflow: complete content sweep — adjectives, passive voice, terminology`

---

## Phase 5: Enforcement + Verification

### Step 5.1: Extend validate.sh — Content-Level Check
- **AC**: AC-12, SC-9
- **File**: `validate.sh`
- **Action**: Add content-level check section per C5.1 design. Grep for subjective adjective pattern with word boundaries. Skip `*/references/*`. Subtract domain-specific compound matches (hardcoded patterns: "sufficient sample", "appropriate statistical test", "sufficient data", "robust standard error"). If additional domain-specific false positives emerge during Phase 4, add them to the compound list. Fail with descriptive output if violations found.
- **Test**: (1) Run validate.sh — should pass (Phase 4 removed all adjectives). (2) Temporarily add "appropriate tools" to a component file, run validate.sh, confirm it fails. Remove test string.
- **Dependencies**: Step 4.1 (adjectives must be removed first, otherwise validate.sh immediately fails)
- **Complexity**: Simple
- **Commit**: `iflow: add subjective adjective content check to validate.sh`

### Step 5.2: Create Hookify Rule — Promptimize Reminder
- **AC**: AC-11, SC-8
- **File**: `.claude/hookify.promptimize-reminder.local.md` (new, local-only)
- **Action**: Invoke `/iflow:hookify` or manually create the hookify rule file targeting PostToolUse Write/Edit events on `plugins/iflow/{agents,skills,commands}/**/*.md`. Advisory message: "Component file modified. Consider running /iflow:promptimize to verify prompt quality."
- **Test**: Edit a component file, verify advisory message appears.
- **Dependencies**: None (independent)
- **Complexity**: Simple
- **Commit**: Not committed (`.local.md` is local-only, gitignored)

### Step 5.3: 5-File Pilot with Behavioral Verification
- **AC**: AC-13
- **Pilot files**: `design-reviewer.md`, `secretary.md`, `brainstorming/SKILL.md`, `review-ds-code.md`, `review-ds-analysis.md`
- **Action**:
  1. Run post-refactor promptimize on all 5 pilot files, record scores
  2. Compare with pre-refactor scores from Step 0.1 baseline-scores.md
  3. For each pilot file, run 2-3 representative inputs per C5.3 design (using identical stored inputs from `test-inputs/` directory created in Step 0.1):
     - `design-reviewer.md`: complete design, design missing interfaces, design with consistency issues
     - `secretary.md`: 5 routing prompts (direct agent, ambiguous, help, orchestrate, no-match)
     - `brainstorming/SKILL.md`: new topic, continuation with research, with advisory team
     - `review-ds-code.md`: clean notebook, anti-pattern notebook, mixed-quality
     - `review-ds-analysis.md`: sound methodology, statistical pitfalls, missing reproducibility
  4. Compare pre/post: same JSON structure (Chain 3 output for ds-code/ds-analysis), same approval decision, issue count +/-1, no new categories, severity shift ≤1 level
  5. **GATE**: If any pilot fails → halt and investigate. Remaining ~80 files blocked until pilot passes.
- **Test**: All 5 pilots pass behavioral equivalence. Score improvements or parity documented.
- **Dependencies**: All Phase 1-4 changes must be applied to pilot files first, Step 0.1 (baseline data)
- **Complexity**: Complex (behavioral verification with multiple inputs per file)
- **Commit**: `iflow: verify pilot files pass behavioral equivalence for 033`

### Step 5.4: Full Batch Promptimize Run — SC-1 Verification
- **AC**: SC-1
- **Action**: Run `batch-promptimize.sh` on all 85 files. Verify all files score ≥80. Investigate and fix any files scoring <80 (iterate: fix, re-score).
- **Test**: batch-promptimize.sh exits with code 0. All files in summary show `[PASS]`.
- **Dependencies**: Step 5.3 (pilot must pass first), Steps 2.3 + 1.1 (batch script + rubric), all Phase 3-4 changes
- **Complexity**: Medium (batch run + potential iteration on failing files)
- **Commit**: `iflow: all 85 files score ≥80 on promptimize rubric`

**Phase 5 gate**: All enforcement mechanisms in place. Pilot verified. Full batch scoring confirmed ≥80.

---

## Dependency Summary

```
Phase 0 + Phase 1 (parallel):
  Step 0.1 (baseline capture) ──→ Phase 2 (blocks scoring tool changes)
  Step 1.1 (rubric) ─┐
  Step 1.2 (guidelines)  │ Phase 1 runs parallel with Step 0.1
  Step 1.3 (authoring) ──┘   (Phase 1 modifies reference files, not pilot files)

Phase 2 (partially parallel, requires both 0.1 and Phase 1 complete):
  Step 2.1a (test update — Red)
    ↓
  Step 1.1 + 2.1a ──→ Step 2.1b (SKILL.md — Green) ──→ Step 2.2 (command — Green)
  Step 1.1 ──→ Step 2.3 (batch script)  ← parallel with 2.1b/2.2

Phase 3 (mostly parallel):
  Step 3.1 (ds-code split)    ─┐
  Step 3.2 (ds-analysis split) ─┤ All complete before Phase 4
  Step 3.3 (math docs)         ─┤ (secretary.md comment independent; promptimize.md verification needs 2.2)
  Step 3.4 (cache restructure) ─┘

Phase 4 (sequential within):
  Step 3.4 ──→ Step 4.0 (audit) ──→ Step 4.1 (adjectives) ──→ Step 4.2 (passive) ──→ Step 4.3 (terminology)
  After 4.3: re-verify secretary.md static-first ordering (final ordering check)

Phase 5 (gated):
  Step 4.1 ──→ Step 5.1 (validate.sh)
  Step 5.2 (hookify) — independent
  All Phase 1-4 + Step 0.1 ──→ Step 5.3 (pilot) ──GATE──→ Step 5.4 (full batch)
```

## TDD Anchors

| Step | Red (test expects new state, fails against current) | Green (make changes, tests pass) | Refactor |
|------|-----------------------------------------------------|----------------------------------|----------|
| 2.1a/2.1b/2.2 | Update `test-promptimize-content.sh`: all "9" → "10", add `cache_friendliness` to expected lists, update denominator 27→30. Tests FAIL against current 9-dimension files. | Apply rubric (1.1) + SKILL.md (2.1b) + command (2.2) changes. Run tests — all PASS. | — |
| 2.3 | Run `batch-promptimize.sh --help` → fails (no file) | Create script | Refine argument parsing |
| 3.1 | Grep ds-code for "SCOPE RESTRICTION" → fails (0 matches) | Implement 3-chain split | — | Note: structural verification only; behavioral correctness deferred to Step 5.3 pilot |
| 3.2 | Grep ds-analysis for "SCOPE RESTRICTION" → fails (0 matches) | Implement 3-chain split | — | Note: structural verification only; behavioral correctness deferred to Step 5.3 pilot |
| 4.1 | Run adjective grep → finds violations | Replace all adjectives | — |
| 5.1 | Run validate.sh with injected adjective → should fail → currently passes | Add content check to validate.sh | Remove test adjective |

## Risk Mitigation Checkpoints

1. **After Step 2.1a + 2.1b + 2.2**: Run `bash plugins/iflow/hooks/tests/test-promptimize-content.sh` — all tests must pass.
2. **After Step 3.1 + 3.2**: Verify chain dispatch structure (3 Task() blocks each). Manually trace one input through the 3-chain flow to confirm data flow.
3. **After Step 3.4 (secretary.md)**: Immediately test 3 routing prompts to catch silent breakage from restructure. Do not wait for Phase 5.
4. **After Step 4.0**: Verify in-scope file count matches expectations (~38 files).
5. **After Step 4.1**: Run manual grep to confirm zero adjectives before proceeding.
6. **After Step 5.3 (pilot)**: This is the hard gate. Do NOT proceed to Step 5.4 if any pilot fails.

## Commit Strategy

Commits are placed at logical boundaries to enable `git bisect` if behavioral verification fails in Phase 5:

| Commit Point | Content |
|---|---|
| After Step 0.1 | Baseline scores |
| After Phase 1 | Reference file updates (rubric, guidelines, authoring) |
| After Phase 2 | Tooling (tests, SKILL.md, command, batch script) |
| After Step 3.1 | ds-code God Prompt split |
| After Step 3.2 | ds-analysis God Prompt split |
| After Step 3.4 | Cache restructure (9 files) |
| After Phase 4 | Content sweep (adjectives, passive, terminology) |
| After Step 5.1 | validate.sh content check |
| After Step 5.3 | Pilot verification pass |
| After Step 5.4 | Full batch SC-1 verification |

## File Manifest

| File | Action | Steps |
|------|--------|-------|
| `docs/dev_artifacts/workitems/033-comprehensive-prompt-refactor/baseline-scores.md` | Create | 0.1 |
| `docs/dev_artifacts/workitems/033-comprehensive-prompt-refactor/test-inputs/` | Create | 0.1 |
| `docs/dev_artifacts/workitems/033-comprehensive-prompt-refactor/adjective-audit.md` | Create | 4.0 |
| `plugins/iflow/skills/promptimize/references/scoring-rubric.md` | Edit | 1.1 |
| `plugins/iflow/skills/promptimize/references/prompt-guidelines.md` | Edit | 1.2 |
| `docs/dev_guides/component-authoring.md` | Edit | 1.3 |
| `plugins/iflow/hooks/tests/test-promptimize-content.sh` | Edit | 2.1a |
| `plugins/iflow/skills/promptimize/SKILL.md` | Edit | 2.1b |
| `plugins/iflow/commands/promptimize.md` | Edit | 2.2, 3.3 |
| `plugins/iflow/scripts/batch-promptimize.sh` | Create | 2.3 |
| `plugins/iflow/commands/review-ds-code.md` | Edit | 3.1 |
| `plugins/iflow/commands/review-ds-analysis.md` | Edit | 3.2 |
| `plugins/iflow/commands/secretary.md` | Edit | 3.3, 3.4, 4.1, 4.2, 4.3 |
| `plugins/iflow/commands/specify.md` | Edit | 3.4, 4.1, 4.2, 4.3 |
| `plugins/iflow/commands/design.md` | Edit | 3.4, 4.1, 4.2, 4.3 |
| `plugins/iflow/commands/create-plan.md` | Edit | 3.4, 4.1, 4.2, 4.3 |
| `plugins/iflow/commands/create-tasks.md` | Edit | 3.4, 4.1, 4.2, 4.3 |
| `plugins/iflow/commands/implement.md` | Edit | 3.4, 4.1, 4.2, 4.3 |
| `plugins/iflow/skills/brainstorming/SKILL.md` | Edit | 3.4, 4.1, 4.2, 4.3 |
| `plugins/iflow/skills/implementing/SKILL.md` | Edit | 3.4, 4.1, 4.2, 4.3 |
| `plugins/iflow/skills/retrospecting/SKILL.md` | Edit | 3.4, 4.1, 4.2, 4.3 |
| ~38 additional agent/skill/command files | Edit | 4.1, 4.2, 4.3 |
| `validate.sh` | Edit | 5.1 |
| `.claude/hookify.promptimize-reminder.local.md` | Create | 5.2 |
| 5 pilot files (subset of above) | Verify | 5.3 |

## Estimated Scope

| Phase | Files | Complexity | Notes |
|-------|-------|------------|-------|
| Phase 0 | 1 new | Medium | Promptimize runs + representative inputs |
| Phase 1 | 3 edits | Simple | Reference/guide file additions |
| Phase 2 | 3 edits + 1 new | Simple–Medium | Test update + SKILL/command updates + new script |
| Phase 3 | 2 rewrites + 1 comment + 9 restructures | Complex | God Prompt splits + caching |
| Phase 4 | ~38-40 edits + 1 new audit file | Medium | Volume, but each change is small |
| Phase 5 | 1 edit + 1 new + pilot + batch | Medium–Complex | Verification-heavy |

Total unique files touched: ~55 (including test file and audit artifacts).
