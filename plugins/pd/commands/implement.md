---
description: Start or continue implementation of current feature
argument-hint: "[--feature=<id-slug>]"
---

Invoke the implementing skill for the current feature context.

## Static Reference

<!-- Placeholder: static content injected here for prompt cache efficiency -->

## YOLO Mode Overrides

If `[YOLO_MODE]` is active:
- **Circuit breaker (3 iterations) — applies to Review Phase (Step 7) only, not Test Deepening (Step 6):** STOP execution and report failure to user.
  Do NOT force-approve. This is a safety boundary — autonomous operation should not
  merge code that fails review 3 times. Output:
  "YOLO MODE STOPPED: Implementation review failed after 3 iterations.
   Unresolved issues: {issue list}
   Resume with: /secretary continue"
- Completion prompt → skip AskUserQuestion, directly invoke `/pd:finish-feature` with `[YOLO_MODE]`

## Workflow Integration

### 1-3. Validate, Branch Check, Partial Recovery, Mark Started

Follow `validateAndSetup("implement")` from the **workflow-transitions** skill.

**Hard prerequisite:** Before standard validation, validate spec.md exists and has substantive content (>100 bytes, has ## headers, has required sections). If validation fails:
```
BLOCKED: Valid spec.md required before implementation.

{Level 1}: spec.md not found. Run /pd:specify first.
{Level 2}: spec.md appears empty or stub. Run /pd:specify to complete it.
{Level 3}: spec.md missing markdown structure. Run /pd:specify to fix.
{Level 4}: spec.md missing required sections (Success Criteria or Acceptance Criteria). Run /pd:specify to add them.
```
Stop execution. Do not proceed.

**Hard prerequisite:** Additionally, validate tasks.md exists and has substantive content (>100 bytes, has ## headers, has required sections). If validation fails:
```
BLOCKED: Valid tasks.md required before implementation.

{Level 1}: tasks.md not found. Run /pd:create-plan first.
{Level 2}: tasks.md appears empty or stub. Run /pd:create-plan to complete it.
{Level 3}: tasks.md missing markdown structure. Run /pd:create-plan to fix.
{Level 4}: tasks.md missing required sections (Phase or Task). Run /pd:create-plan to add them.
```
Stop execution. Do not proceed.

### 4. Implementation Phase

Execute the implementing skill which:
- Parses tasks.md for all task headings
- Dispatches implementer agent per task with scoped context
- Collects structured reports (files changed, decisions, deviations, concerns)
- Appends per-task entries to implementation-log.md
- Returns aggregate summary (files changed, completion status)

### 5. Code Simplification Phase

Invoke Claude Code's native `/simplify` skill to review recently changed code for unnecessary complexity:

```
Skill tool call:
  skill: "simplify"
```

The native skill has full conversation context (files changed, implementation decisions) and handles:
- Reviewing changed code for unnecessary abstractions, dead code, over-engineering, verbose patterns
- Applying approved simplifications
- Verifying tests still pass

No pre-dispatch memory enrichment or post-dispatch influence tracking needed — the native skill operates within the main conversation context.

### 6. Test Deepening Phase

Dispatch test-deepener agent in two phases. Phase A generates spec-driven test outlines without implementation access. Phase B writes executable tests.

**PRD resolution (I8) — resolve once, reuse in Steps 6, 7a, 7e:**
1. Check if `{feature_path}/prd.md` exists
2. If exists → PRD line = `- PRD: {feature_path}/prd.md`
3. If not → check `.meta.json` for `brainstorm_source`
   a. If found → PRD line = `- PRD: {brainstorm_source path}`
   b. If not → PRD line = `- PRD: No PRD — feature created without brainstorm`

Store the resolved PRD line for reuse below.

**Phase A — Generate test outlines from spec only:**

**Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
limit=5, brief=true, and category="anti-patterns".
Store the returned entry names for post-dispatch influence tracking.
Include non-empty results inside the prompt below.

```
Task tool call:
  description: "Generate test outlines from spec"
  subagent_type: pd:test-deepener
  model: opus
  prompt: |
    PHASE A: Generate test outlines from specifications only.
    Do NOT read implementation files. Do NOT use Glob/Grep to find source code.
    You will receive implementation access in Phase B.

    Feature: {feature name from .meta.json slug}

    ## Required Artifacts
    You MUST read the following files before beginning your work.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    - Spec: {feature_path}/spec.md
    - Design: {feature_path}/design.md
    - Tasks: {feature_path}/tasks.md
    {resolved PRD line from I8}

    Generate Given/When/Then test outlines for all applicable dimensions.
    Return as structured JSON with dimension, scenario name, given/when/then text,
    and derived_from reference to spec criterion.

    ## Relevant Engineering Memory
    {search_memory results from the pre-dispatch call above}
```

**Fallback detection (I9):** After receiving the test-deepener Phase A response, search for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: test-deepener did not confirm artifact reads` to `.review-history.md`. Proceed regardless.

<!-- influence-tracking-site: s8 -->
**Influence tracking (mandatory, unconditional):**
Call `record_influence_by_content(
  subagent_output_text=<full agent output text>,
  injected_entry_names=<list from search_memory results, or [] if none>,
  agent_role="test-deepener",
  feature_type_id=<current feature type_id from .meta.json>)`
Emit one line to your output: `Influence recorded: N matches`.
On MCP failure: warn "Influence tracking failed: {error}", continue.
If .meta.json missing or type_id unresolvable: skip with warning.

**Phase A validation:** If `outlines` array is empty, log warning: "Test deepening Phase A returned no outlines — skipping test deepening" and proceed to Step 7.

**Files-changed union assembly:**

Build the union of files from Step 4 (implementation) and Step 5 (simplification):

```
# files from Step 4 (already in orchestrator context)
implementation_files = step_4_aggregate.files_changed

# files from Step 5 (already in orchestrator context)
simplification_files = [s.location.split(":")[0] for s in step_5_output.simplifications]

# union and deduplicate
files_changed = sorted(set(implementation_files + simplification_files))
```

**Fallback if context was compacted:** If the orchestrator no longer holds Step 4/5 data in context (due to conversation compaction), parse `implementation-log.md` directly. Each task section contains a "Files changed" or "files_changed" field with file paths. Match lines that look like file paths (contain `/` and end with a file extension). Validate extracted paths: reject any containing `..`, `%2e`, null bytes, or backslashes; reject paths starting with `/`; only accept relative paths within the project root. Step 5 paths are always a subset of Step 4 paths, so no coverage gap exists.

**Phase B — Write executable tests:**

**Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
limit=5, brief=true, and category="anti-patterns".
Store the returned entry names for post-dispatch influence tracking.
Include non-empty results inside the prompt below.

```
Task tool call:
  description: "Write and verify deepened tests"
  subagent_type: pd:test-deepener
  model: opus
  prompt: |
    PHASE B: Write executable test code from these outlines.

    Feature: {feature name}

    ## Test Outlines (from Phase A)
    {Phase A JSON output — the full outlines array}

    ## Files Changed (implementation + simplification)
    {deduplicated file list}

    Step 1: Read existing test files for changed code to identify the test
    framework, assertion patterns, and file organization conventions. Match
    these exactly when writing new tests.

    Step 2: Skip scenarios already covered by existing TDD tests.

    Step 3: Write executable tests, run the suite, and report.

    ## Relevant Engineering Memory
    {search_memory results from the pre-dispatch call above}
```

<!-- influence-tracking-site: s9 -->
**Influence tracking (mandatory, unconditional):**
Call `record_influence_by_content(
  subagent_output_text=<full agent output text>,
  injected_entry_names=<list from search_memory results, or [] if none>,
  agent_role="test-deepener",
  feature_type_id=<current feature type_id from .meta.json>)`
Emit one line to your output: `Influence recorded: N matches`.
On MCP failure: warn "Influence tracking failed: {error}", continue.
If .meta.json missing or type_id unresolvable: skip with warning.

**Divergence control flow:**

After Phase B completes, check `spec_divergences` in the output:

- **If `spec_divergences` is empty:** Proceed to Step 7 (Review Phase).

- **If `spec_divergences` is non-empty AND YOLO mode OFF:**
  ```
  AskUserQuestion:
    questions: [{
      "question": "Test deepening found {n} spec divergences. How to proceed?",
      "header": "Spec Divergences",
      "options": [
        {"label": "Fix implementation", "description": "Dispatch implementer to fix code to match spec, then re-run Phase B"},
        {"label": "Accept implementation", "description": "Remove divergent tests and proceed to review"},
        {"label": "Review manually", "description": "Inspect divergences before deciding"}
      ],
      "multiSelect": false
    }]
  ```

  - **"Fix implementation":**
    1. Dispatch implementer agent with `spec_divergences` formatted as issues (spec_criterion as requirement, expected as target, actual as bug, failing_test as evidence). Include spec.md, design.md, and implementation files in context.
    2. Re-run Phase B only (Phase A outlines are unchanged since spec inputs don't change when implementation is fixed).
    3. Max 2 re-runs. If divergences persist after 2 cycles, escalate with AskUserQuestion offering only "Accept implementation" and "Review manually".

  - **"Accept implementation":**
    1. For each divergence in `spec_divergences`, delete the test function identified by `failing_test` from the file.
    2. After ALL deletions, re-run the test suite once to verify remaining tests pass.
    3. Proceed to Step 7.

  - **"Review manually":** Stop execution.

- **If `spec_divergences` is non-empty AND YOLO mode ON:**
  - If re-run count < 2: Auto-select "Fix implementation" (dispatch implementer, re-run Phase B only).
  - If re-run count >= 2: STOP execution and surface to user:
    "YOLO MODE STOPPED: Test deepening found persistent spec divergences after 2 fix cycles.
     Divergences: {divergence list}
     Resume with: /secretary continue"

**Error handling:** If Phase A or Phase B agent dispatch fails (tool error, timeout, or agent crash), log the error and proceed to Step 7. Test deepening is additive — failure should not block the review phase.

### 6b. Pre-validation Against Knowledge Bank

Before dispatching reviewers, run a self-check against accumulated anti-patterns.

1. **Determine changed files:**
   ```
   Bash: git diff --name-only {base_branch}...HEAD
   ```
   Capture as `changed_files`.

2. **Query knowledge bank:**
   ```
   search_memory(query="{feature slug} {current phase} {space-separated changed file names}", limit=20, category="anti-patterns", brief=true)
   ```

3. **Skip threshold:** If fewer than 5 entries returned, skip pre-validation — insufficient KB data for meaningful matching. Proceed directly to Step 7.

4. **Inline self-check:** Build a prompt presenting ONLY the returned anti-pattern descriptions and the changed file contents:
   ```
   The knowledge bank contains these anti-patterns relevant to this feature:
   {list of anti-pattern names and descriptions from search_memory}

   Review the following implementation files for any of these specific anti-patterns:
   {changed file contents}

   For each anti-pattern that applies, explain which code exhibits it and suggest a fix.
   Do NOT identify issues beyond the listed anti-patterns.
   ```
   Execute this as an inline self-directed reasoning step (no subagent dispatch).

5. **Auto-fix matches:** For each matched anti-pattern, apply the suggested fix. Log each fix to `.review-history.md` as:
   ```markdown
   ## Pre-validation Auto-fix - {ISO timestamp}
   - Fixed: {anti-pattern name} in {file} — {brief description of fix}
   ```

6. **Error handling:** If `search_memory` MCP is unavailable, times out, or the self-check errors out, skip pre-validation and proceed directly to Step 7. Log: `"Pre-validation skipped: {reason}"` to `.review-history.md`.

### 7. Review Phase (3-Level Sequential Verification)

Maximum 3 iterations (total, shared across all levels, including the final validation round). Loop continues until ALL reviewers approve or cap is reached.

**3-Level Structure:**
- **Level 1: Task-Level Verification** -- implementation-reviewer validates each task's DoD against implementation
- **Level 2: Spec-Level Verification** -- relevance-verifier validates each spec AC is satisfied by the implementation
- **Level 3: Standards-Level Verification** -- code-quality-reviewer + security-reviewer for engineering standards

Dispatch order is Level 1 -> Level 2 -> Level 3 (sequential, not parallel). Level 1/2 failures may trigger backward travel via handleReviewerResponse. Level 3 failures use the existing fix-and-iterate pattern (no backward travel).

**Reviewer State Tracking:**

Before entering the iteration loop, initialize per-reviewer status:

```
reviewer_status = {
  "implementation": "pending",
  "relevance": "pending",
  "quality": "pending",
  "security": "pending"
}
is_final_validation = false
```

Values: `pending` (not yet reviewed), `passed`, `failed`.

**Resume state initialization:**

Initialize `resume_state = {}` at the start of the review loop. This dict tracks per-role agent context for resume across iterations. Keys: `"implementation-reviewer"`, `"relevance-verifier"`, `"code-quality-reviewer"`, `"security-reviewer"`, `"implementer"`. Each entry: `{ agent_id, iteration1_prompt_length, last_iteration, last_commit_sha }`.

```
resume_state = {}
fix_summaries = []
```

The `fix_summaries` list accumulates implementer fix summaries across iterations (used by I2-FV final validation template to show consolidated changes since a reviewer's last review).

**Iteration 1:** Always dispatch all 4 reviewers (full scope, sequentially by level).
**Iterations 2+:** Only dispatch reviewers where `reviewer_status == "failed"`. Skip reviewers where `reviewer_status == "passed"`.
**Final validation:** When all reviewers have individually passed, dispatch all 4 again for a mandatory full regression check.

Execute review cycle with 3-level sequential verification:

**7a. Level 1: Task-Level Verification (Implementation Review):**

Use the PRD line resolved in Step 6 (I8).

**Dispatch decision for implementation-reviewer:**

**If iteration == 1 OR resume_state["implementation-reviewer"] is missing/empty OR resume_state["implementation-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

**Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
limit=5, brief=true, and category="anti-patterns".
Store the returned entry names for post-dispatch influence tracking.
Include non-empty results inside the prompt below.

```
Task tool call:
  description: "Review implementation against requirements chain"
  subagent_type: pd:implementation-reviewer
  model: opus
  prompt: |
    Validate implementation against full requirements chain with 4-level validation.

    ## Required Artifacts
    You MUST read the following files before beginning your review.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    {resolved PRD line from I8}
    - Spec: {feature_path}/spec.md
    - Design: {feature_path}/design.md
    - Plan: {feature_path}/plan.md
    - Tasks: {feature_path}/tasks.md

    Validate all 4 levels:
    - Level 1: Task completeness
    - Level 2: Spec compliance
    - Level 3: Design alignment
    - Level 4: PRD delivery

    Return JSON with approval status, level results, issues, and evidence:
    {
      "approved": true/false,
      "levels": {
        "tasks": {"passed": true/false, "issues_count": 0},
        "spec": {"passed": true/false, "issues_count": 0},
        "design": {"passed": true/false, "issues_count": 0},
        "prd": {"passed": true/false, "issues_count": 0}
      },
      "issues": [{"severity": "blocker|warning|suggestion", "level": "tasks|spec|design|prd", "category": "missing|extra|misunderstood|incomplete", "description": "...", "location": "...", "suggestion": "..."}],
      "evidence": {"verified": [], "missing": []},
      "summary": "..."
    }

    ## Implementation Files
    {newline-separated list of file paths}

    ## Relevant Engineering Memory
    {search_memory results from the pre-dispatch call above}
```

After fresh dispatch: capture the `agent_id` from the Task tool result. Record the character count of the prompt above as `prompt_length`. Capture current HEAD SHA via `Bash: git rev-parse HEAD`. Store in resume_state:
```
resume_state["implementation-reviewer"] = {
  "agent_id": {agent_id from Task result},
  "iteration1_prompt_length": {prompt_length} (only set on iteration 1; preserved on subsequent fresh dispatches),
  "last_iteration": {iteration},
  "last_commit_sha": {HEAD SHA}
}
```
If this is not iteration 1 (fresh dispatch due to fallback/reset), preserve the original `iteration1_prompt_length` from the first fresh dispatch of this loop if available; otherwise set it from this dispatch's prompt length.

**If iteration >= 2 AND this reviewer failed (status "failed") AND resume_state["implementation-reviewer"] exists with non-null agent_id** — attempt I2 resumed dispatch:

Compute the delta using the per-iteration commit (see 7e-commit below). The `delta_content` and `delta_stat` are already captured after the implementer fix commit.

**Delta size guard**: If `len(delta_content)` > 50% of `resume_state["implementation-reviewer"].iteration1_prompt_length`, the delta is too large — fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context added). Reset `resume_state["implementation-reviewer"]`.

**If delta is within threshold**, attempt I2 resumed dispatch:
```
Task tool call:
  resume: {resume_state["implementation-reviewer"].agent_id}
  prompt: |
    You already have the upstream artifacts and implementation files
    in context from your prior review.

    The following changes were made to address your previous issues:

    ## Delta
    {delta_stat from git diff --stat}
    {delta_content from git diff}

    ## Fix Summary
    {implementer fix summary text from this iteration}

    Review the changes above. Assess whether your previous issues are resolved
    and check for new issues introduced by the fixes.

    This is iteration {iteration} of {max}.

    Return JSON with approval status, level results, issues, and evidence:
    {
      "approved": true/false,
      "levels": {
        "tasks": {"passed": true/false, "issues_count": 0},
        "spec": {"passed": true/false, "issues_count": 0},
        "design": {"passed": true/false, "issues_count": 0},
        "prd": {"passed": true/false, "issues_count": 0}
      },
      "issues": [{"severity": "blocker|warning|suggestion", "level": "tasks|spec|design|prd", "category": "missing|extra|misunderstood|incomplete", "description": "...", "location": "...", "suggestion": "..."}],
      "evidence": {"verified": [], "missing": []},
      "summary": "..."
    }
```

**If resume succeeds**: Update resume_state:
```
resume_state["implementation-reviewer"].agent_id = {agent_id from resumed Task result}
resume_state["implementation-reviewer"].last_iteration = {iteration}
resume_state["implementation-reviewer"].last_commit_sha = {current HEAD SHA}
```

**If resume fails** (Task tool returns an error): I3 fallback — fresh I1-R4 dispatch (same template as iteration 1, with additional line in prompt: `"(Fresh dispatch — prior review session unavailable.)"` and previous issues appended). Log to `.review-history.md`: `RESUME-FALLBACK: implementation-reviewer iteration {iteration} — {error summary}`. Reset `resume_state["implementation-reviewer"]` with the new fresh dispatch's agent_id.

**If is_final_validation AND this reviewer previously passed (status "passed")** — attempt I2-FV resumed dispatch:

No delta size guard for final validation. Compute the diff between the reviewer's last review commit and current HEAD:
```
Bash: git diff {resume_state["implementation-reviewer"].last_commit_sha} HEAD --stat
Bash: git diff {resume_state["implementation-reviewer"].last_commit_sha} HEAD
```

```
Task tool call:
  resume: {resume_state["implementation-reviewer"].agent_id}
  prompt: |
    You already have the upstream artifacts and implementation files
    in context from your prior review at iteration {resume_state["implementation-reviewer"].last_iteration}.

    Since your last review, the following fixes were applied to address
    issues from other reviewers:

    ## Changes Since Your Last Review
    {git diff --stat between last_iteration commit and current HEAD}
    {git diff between last_iteration commit and current HEAD}

    ## Fix Summary
    {consolidated fix summaries from all intermediate iterations (from fix_summaries list)}

    Perform a full regression check. Verify your previous approval still
    holds given these changes, and check for any new issues.

    This is the final validation round (iteration {iteration} of {max}).

    Return JSON with approval status, level results, issues, and evidence:
    {
      "approved": true/false,
      "levels": {
        "tasks": {"passed": true/false, "issues_count": 0},
        "spec": {"passed": true/false, "issues_count": 0},
        "design": {"passed": true/false, "issues_count": 0},
        "prd": {"passed": true/false, "issues_count": 0}
      },
      "issues": [{"severity": "blocker|warning|suggestion", "level": "tasks|spec|design|prd", "category": "missing|extra|misunderstood|incomplete", "description": "...", "location": "...", "suggestion": "..."}],
      "evidence": {"verified": [], "missing": []},
      "summary": "..."
    }
```

**If I2-FV resume succeeds**: Update resume_state:
```
resume_state["implementation-reviewer"].agent_id = {agent_id from resumed Task result}
resume_state["implementation-reviewer"].last_iteration = {iteration}
resume_state["implementation-reviewer"].last_commit_sha = {current HEAD SHA}
```

**If I2-FV resume fails**: I3 fallback — fresh I1-R4 dispatch (same template as iteration 1, with `"(Fresh dispatch — prior review session unavailable.)"` annotation). Log: `RESUME-FALLBACK: implementation-reviewer iteration {iteration} — {error summary}`. Reset `resume_state["implementation-reviewer"]`.

**Context compaction detection**: Before attempting any resume (I2 or I2-FV), if `resume_state["implementation-reviewer"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I1-R4 dispatch. Log: `RESUME-FALLBACK: implementation-reviewer iteration {iteration} — agent_id lost (context compaction)`.

**Fallback detection (I9):** After receiving the implementation-reviewer's response, search for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: implementation-reviewer did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I2/I2-FV templates) do not include Required Artifacts, so "Files read:" may not appear — only apply I9 detection to fresh dispatches.

<!-- influence-tracking-site: s10 -->
**Influence tracking (mandatory, unconditional):**
Call `record_influence_by_content(
  subagent_output_text=<full agent output text>,
  injected_entry_names=<list from search_memory results, or [] if none>,
  agent_role="implementation-reviewer",
  feature_type_id=<current feature type_id from .meta.json>)`
Emit one line to your output: `Influence recorded: N matches`.
On MCP failure: warn "Influence tracking failed: {error}", continue.
If .meta.json missing or type_id unresolvable: skip with warning.

**7a2. Level 2: Spec-Level Verification (Relevance Check):**

**Dispatch decision for relevance-verifier:**

**If iteration == 1 OR resume_state["relevance-verifier"] is missing/empty OR resume_state["relevance-verifier"].agent_id is null** -- use fresh I1-R4 dispatch:

**Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
call `search_memory` with query: "relevance-verifier spec compliance artifact coherence",
limit=5, brief=true, and category="anti-patterns".
Store the returned entry names for post-dispatch influence tracking.
Include non-empty results inside the prompt below.

```
Task tool call:
  description: "Verify spec compliance"
  subagent_type: pd:relevance-verifier
  model: opus
  prompt: |
    Verify the implementation satisfies spec acceptance criteria.

    ## Required Artifacts
    You MUST read the following files before beginning your review.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    - Spec: {feature_path}/spec.md
    - Design: {feature_path}/design.md
    - Plan: {feature_path}/plan.md
    - Tasks: {feature_path}/tasks.md

    ## Implementation Files
    {complete list of all files assigned to this implementation task}

    For each spec AC, verify it is satisfied by the implementation.
    Use deterministic checks where possible (run tests if configured).

    Run all 4 checks: coverage, completeness, testability, coherence.

    Return JSON with pass/fail per check, gaps, and optional backward_to.

    ## Relevant Engineering Memory
    {search_memory results from the pre-dispatch call above}

    ## Phase Context (backward transitions only)
    If .meta.json `phases[current_phase]` has a `completed` timestamp (indicating re-entry into a completed phase):
    1. Read `backward_context` and `phase_summaries` from .meta.json
    2. Construct `## Phase Context` block per workflow-transitions SKILL.md Step 1b format
    3. Include this block here
    If no `completed` timestamp for current phase: skip injection entirely.
```
After fresh dispatch: capture the `agent_id` from the Task tool result. Record the character count of the prompt above as `prompt_length`. Capture current HEAD SHA via `Bash: git rev-parse HEAD`. Store in resume_state:
```
resume_state["relevance-verifier"] = {
  "agent_id": {agent_id from Task result},
  "iteration1_prompt_length": {prompt_length} (only set on iteration 1; preserved on subsequent fresh dispatches),
  "last_iteration": {iteration},
  "last_commit_sha": {HEAD SHA}
}
```
If this is not iteration 1 (fresh dispatch due to fallback/reset), preserve the original `iteration1_prompt_length` from the first fresh dispatch of this loop if available; otherwise set it from this dispatch's prompt length.

**If iteration >= 2 AND this reviewer failed (status "failed") AND resume_state["relevance-verifier"] exists with non-null agent_id** -- attempt I2 resumed dispatch:

First, compute the delta between the last reviewed commit and current HEAD:
```
Bash: git diff {resume_state["relevance-verifier"].last_commit_sha} HEAD --stat
Bash: git diff {resume_state["relevance-verifier"].last_commit_sha} HEAD
```
Capture as `delta_stat` and `delta_content`.

**Delta size guard**: If `len(delta_content)` > 50% of `resume_state["relevance-verifier"].iteration1_prompt_length`, the delta is too large -- fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context added). Reset `resume_state["relevance-verifier"]`.

**If delta is within threshold**, attempt resumed dispatch:
```
Task tool call:
  resume: {resume_state["relevance-verifier"].agent_id}
  prompt: |
    You already have the upstream artifacts and the previous implementation state
    in context from your prior review.

    The following changes were made to address your previous issues:

    ## Delta
    {delta_content from git diff}

    ## Fix Summary
    {summary of revisions made to address the reviewer's issues}

    Review the changes above. Assess whether your previous issues are resolved
    and check for new issues introduced by the fixes.

    This is iteration {iteration} of {max}.

    Return JSON with pass/fail per check, gaps, and optional backward_to.
```

**If resume succeeds**: Update resume_state:
```
resume_state["relevance-verifier"].agent_id = {agent_id from resumed Task result}
resume_state["relevance-verifier"].last_iteration = {iteration}
resume_state["relevance-verifier"].last_commit_sha = {current HEAD SHA}
```

**If resume fails** (Task tool returns an error): I3 fallback -- fresh I1-R4 dispatch (same template as iteration 1, with additional line in prompt: `"(Fresh dispatch -- prior review session unavailable.)"` and previous issues appended). Log to `.review-history.md`: `RESUME-FALLBACK: relevance-verifier iteration {iteration} -- {error summary}`. Reset `resume_state["relevance-verifier"]` with the new fresh dispatch's agent_id.

**If is_final_validation AND this reviewer previously passed (status "passed")** -- attempt I2-FV resumed dispatch:

No delta size guard for final validation. Compute the diff between the reviewer's last review commit and current HEAD:
```
Bash: git diff {resume_state["relevance-verifier"].last_commit_sha} HEAD --stat
Bash: git diff {resume_state["relevance-verifier"].last_commit_sha} HEAD
```
```
Task tool call:
  resume: {resume_state["relevance-verifier"].agent_id}
  prompt: |
    You already have the upstream artifacts and the implementation state
    in context from your prior review at iteration {resume_state["relevance-verifier"].last_iteration}.

    Since your last review, the following fixes were applied to address
    issues from other reviewers:

    ## Changes Since Your Last Review
    {delta_stat}

    ## Full Diff
    {delta_content}

    ## Fix Summaries (consolidated)
    {fix_summaries entries since this reviewer's last_iteration}

    Re-verify all 4 checks with these changes in mind. Confirm your
    previous approval still holds, or flag new issues introduced by
    the fixes.

    This is iteration {iteration} (final validation round).

    Return JSON with pass/fail per check, gaps, and optional backward_to.
```

**If I2-FV resume succeeds**: Update resume_state:
```
resume_state["relevance-verifier"].agent_id = {agent_id from resumed Task result}
resume_state["relevance-verifier"].last_iteration = {iteration}
resume_state["relevance-verifier"].last_commit_sha = {current HEAD SHA}
```

**If I2-FV resume fails**: I3 fallback -- fresh I1-R4 dispatch (same template as iteration 1, with `"(Fresh dispatch -- prior review session unavailable.)"` annotation). Log: `RESUME-FALLBACK: relevance-verifier iteration {iteration} -- {error summary}`. Reset `resume_state["relevance-verifier"]`.

**Context compaction detection**: Before attempting any resume (I2 or I2-FV), if `resume_state["relevance-verifier"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I1-R4 dispatch. Log: `RESUME-FALLBACK: relevance-verifier iteration {iteration} -- agent_id lost (context compaction)`.

**Fallback detection (I9):** After receiving the relevance-verifier's response, search for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: relevance-verifier did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I2/I2-FV templates) do not include Required Artifacts, so "Files read:" may not appear -- only apply I9 detection to fresh dispatches.

<!-- influence-tracking-site: s11 -->
**Influence tracking (mandatory, unconditional):**
Call `record_influence_by_content(
  subagent_output_text=<full agent output text>,
  injected_entry_names=<list from search_memory results, or [] if none>,
  agent_role="relevance-verifier",
  feature_type_id=<current feature type_id from .meta.json>)`
Emit one line to your output: `Influence recorded: N matches`.
On MCP failure: warn "Influence tracking failed: {error}", continue.
If .meta.json missing or type_id unresolvable: skip with warning.

**Handle relevance-verifier result:**
- Apply strict threshold: **PASS** = `pass: true` with zero gaps across all checks. **FAIL** = `pass: false` OR any check has gaps.
- Update `reviewer_status["relevance"]` based on result.
- If FAIL AND `backward_to` exists in response: invoke `handleReviewerResponse()` with the gate's response (triggers backward travel). Do not proceed to Level 3.
- If FAIL AND no `backward_to`: treat as standard reviewer failure (dispatch implementer to fix, then re-review).

**7b. Level 3: Standards-Level Verification -- Code Quality Review:**

**Dispatch decision for code-quality-reviewer:**

**If iteration == 1 OR resume_state["code-quality-reviewer"] is missing/empty OR resume_state["code-quality-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

**Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
limit=5, brief=true, and category="anti-patterns".
Store the returned entry names for post-dispatch influence tracking.
Include non-empty results inside the prompt below.

```
Task tool call:
  description: "Review code quality"
  subagent_type: pd:code-quality-reviewer
  model: sonnet
  prompt: |
    Review implementation quality.

    ## Required Artifacts
    You MUST read the following files before beginning your review.
    Also read implementation files listed below as needed.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    - Design: {feature_path}/design.md
    - Spec: {feature_path}/spec.md

    Check:
    - Readability
    - KISS principle
    - YAGNI principle
    - Formatting
    - Holistic flow

    Return your assessment as JSON:
    {
      "approved": true/false,
      "issues": [{"severity": "blocker|warning|suggestion", "category": "readability|kiss|yagni|formatting|flow", "description": "...", "location": "...", "suggestion": "..."}],
      "summary": "..."
    }

    ## Implementation Files
    {newline-separated list of file paths}

    ## Relevant Engineering Memory
    {search_memory results from the pre-dispatch call above}

    ## Phase Context (backward transitions only)
    If .meta.json `phases[current_phase]` has a `completed` timestamp (indicating re-entry into a completed phase):
    1. Read `backward_context` and `phase_summaries` from .meta.json
    2. Construct `## Phase Context` block per workflow-transitions SKILL.md Step 1b format
    3. Include this block here
    If no `completed` timestamp for current phase: skip injection entirely.
```

After fresh dispatch: capture the `agent_id` from the Task tool result. Record the character count of the prompt above as `prompt_length`. Capture current HEAD SHA via `Bash: git rev-parse HEAD`. Store in resume_state:
```
resume_state["code-quality-reviewer"] = {
  "agent_id": {agent_id from Task result},
  "iteration1_prompt_length": {prompt_length} (only set on iteration 1; preserved on subsequent fresh dispatches),
  "last_iteration": {iteration},
  "last_commit_sha": {HEAD SHA}
}
```
If this is not iteration 1 (fresh dispatch due to fallback/reset), preserve the original `iteration1_prompt_length` from the first fresh dispatch of this loop if available; otherwise set it from this dispatch's prompt length.

**If iteration >= 2 AND this reviewer failed (status "failed") AND resume_state["code-quality-reviewer"] exists with non-null agent_id** — attempt I2 resumed dispatch:

Compute the delta using the per-iteration commit (see 7e-commit below). The `delta_content` and `delta_stat` are already captured after the implementer fix commit.

**Delta size guard**: If `len(delta_content)` > 50% of `resume_state["code-quality-reviewer"].iteration1_prompt_length`, the delta is too large — fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context added). Reset `resume_state["code-quality-reviewer"]`.

**If delta is within threshold**, attempt I2 resumed dispatch:
```
Task tool call:
  resume: {resume_state["code-quality-reviewer"].agent_id}
  prompt: |
    You already have the upstream artifacts and implementation files
    in context from your prior review.

    The following changes were made to address your previous issues:

    ## Delta
    {delta_stat from git diff --stat}
    {delta_content from git diff}

    ## Fix Summary
    {implementer fix summary text from this iteration}

    Review the changes above. Assess whether your previous issues are resolved
    and check for new issues introduced by the fixes.

    This is iteration {iteration} of {max}.

    Return your assessment as JSON:
    {
      "approved": true/false,
      "issues": [{"severity": "blocker|warning|suggestion", "category": "readability|kiss|yagni|formatting|flow", "description": "...", "location": "...", "suggestion": "..."}],
      "summary": "..."
    }
```

**If resume succeeds**: Update resume_state:
```
resume_state["code-quality-reviewer"].agent_id = {agent_id from resumed Task result}
resume_state["code-quality-reviewer"].last_iteration = {iteration}
resume_state["code-quality-reviewer"].last_commit_sha = {current HEAD SHA}
```

**If resume fails** (Task tool returns an error): I3 fallback — fresh I1-R4 dispatch (same template as iteration 1, with additional line in prompt: `"(Fresh dispatch — prior review session unavailable.)"` and previous issues appended). Log to `.review-history.md`: `RESUME-FALLBACK: code-quality-reviewer iteration {iteration} — {error summary}`. Reset `resume_state["code-quality-reviewer"]` with the new fresh dispatch's agent_id.

**If is_final_validation AND this reviewer previously passed (status "passed")** — attempt I2-FV resumed dispatch:

No delta size guard for final validation. Compute the diff between the reviewer's last review commit and current HEAD:
```
Bash: git diff {resume_state["code-quality-reviewer"].last_commit_sha} HEAD --stat
Bash: git diff {resume_state["code-quality-reviewer"].last_commit_sha} HEAD
```

```
Task tool call:
  resume: {resume_state["code-quality-reviewer"].agent_id}
  prompt: |
    You already have the upstream artifacts and implementation files
    in context from your prior review at iteration {resume_state["code-quality-reviewer"].last_iteration}.

    Since your last review, the following fixes were applied to address
    issues from other reviewers:

    ## Changes Since Your Last Review
    {git diff --stat between last_iteration commit and current HEAD}
    {git diff between last_iteration commit and current HEAD}

    ## Fix Summary
    {consolidated fix summaries from all intermediate iterations (from fix_summaries list)}

    Perform a full regression check. Verify your previous approval still
    holds given these changes, and check for any new issues.

    This is the final validation round (iteration {iteration} of {max}).

    Return your assessment as JSON:
    {
      "approved": true/false,
      "issues": [{"severity": "blocker|warning|suggestion", "category": "readability|kiss|yagni|formatting|flow", "description": "...", "location": "...", "suggestion": "..."}],
      "summary": "..."
    }
```

**If I2-FV resume succeeds**: Update resume_state:
```
resume_state["code-quality-reviewer"].agent_id = {agent_id from resumed Task result}
resume_state["code-quality-reviewer"].last_iteration = {iteration}
resume_state["code-quality-reviewer"].last_commit_sha = {current HEAD SHA}
```

**If I2-FV resume fails**: I3 fallback — fresh I1-R4 dispatch (same template as iteration 1, with `"(Fresh dispatch — prior review session unavailable.)"` annotation). Log: `RESUME-FALLBACK: code-quality-reviewer iteration {iteration} — {error summary}`. Reset `resume_state["code-quality-reviewer"]`.

**Context compaction detection**: Before attempting any resume (I2 or I2-FV), if `resume_state["code-quality-reviewer"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I1-R4 dispatch. Log: `RESUME-FALLBACK: code-quality-reviewer iteration {iteration} — agent_id lost (context compaction)`.

**Fallback detection (I9):** After receiving the code-quality-reviewer's response, search for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: code-quality-reviewer did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I2/I2-FV templates) do not include Required Artifacts, so "Files read:" may not appear — only apply I9 detection to fresh dispatches.

<!-- influence-tracking-site: s12 -->
**Influence tracking (mandatory, unconditional):**
Call `record_influence_by_content(
  subagent_output_text=<full agent output text>,
  injected_entry_names=<list from search_memory results, or [] if none>,
  agent_role="code-quality-reviewer",
  feature_type_id=<current feature type_id from .meta.json>)`
Emit one line to your output: `Influence recorded: N matches`.
On MCP failure: warn "Influence tracking failed: {error}", continue.
If .meta.json missing or type_id unresolvable: skip with warning.

**7c. Level 3: Standards-Level Verification -- Security Review:**

**Dispatch decision for security-reviewer:**

**If iteration == 1 OR resume_state["security-reviewer"] is missing/empty OR resume_state["security-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

**Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
limit=5, brief=true, and category="anti-patterns".
Store the returned entry names for post-dispatch influence tracking.
Include non-empty results inside the prompt below.

```
Task tool call:
  description: "Review security"
  subagent_type: pd:security-reviewer
  model: opus
  prompt: |
    Review implementation for security vulnerabilities.

    ## Required Artifacts
    You MUST read the following files before beginning your review.
    Also read implementation files listed below as needed.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    - Design: {feature_path}/design.md
    - Spec: {feature_path}/spec.md

    Check:
    - Input validation
    - Authentication/authorization
    - Data protection
    - OWASP top 10

    Return your assessment as JSON:
    {
      "approved": true/false,
      "issues": [{"severity": "blocker|warning|suggestion", "category": "injection|auth|crypto|exposure|config", "description": "...", "location": "...", "suggestion": "..."}],
      "summary": "..."
    }

    ## Implementation Files
    {newline-separated list of file paths}

    ## Relevant Engineering Memory
    {search_memory results from the pre-dispatch call above}

    ## Phase Context (backward transitions only)
    If .meta.json `phases[current_phase]` has a `completed` timestamp (indicating re-entry into a completed phase):
    1. Read `backward_context` and `phase_summaries` from .meta.json
    2. Construct `## Phase Context` block per workflow-transitions SKILL.md Step 1b format
    3. Include this block here
    If no `completed` timestamp for current phase: skip injection entirely.
```

After fresh dispatch: capture the `agent_id` from the Task tool result. Record the character count of the prompt above as `prompt_length`. Capture current HEAD SHA via `Bash: git rev-parse HEAD`. Store in resume_state:
```
resume_state["security-reviewer"] = {
  "agent_id": {agent_id from Task result},
  "iteration1_prompt_length": {prompt_length} (only set on iteration 1; preserved on subsequent fresh dispatches),
  "last_iteration": {iteration},
  "last_commit_sha": {HEAD SHA}
}
```
If this is not iteration 1 (fresh dispatch due to fallback/reset), preserve the original `iteration1_prompt_length` from the first fresh dispatch of this loop if available; otherwise set it from this dispatch's prompt length.

**If iteration >= 2 AND this reviewer failed (status "failed") AND resume_state["security-reviewer"] exists with non-null agent_id** — attempt I2 resumed dispatch:

Compute the delta using the per-iteration commit (see 7e-commit below). The `delta_content` and `delta_stat` are already captured after the implementer fix commit.

**Delta size guard**: If `len(delta_content)` > 50% of `resume_state["security-reviewer"].iteration1_prompt_length`, the delta is too large — fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context added). Reset `resume_state["security-reviewer"]`.

**If delta is within threshold**, attempt I2 resumed dispatch:
```
Task tool call:
  resume: {resume_state["security-reviewer"].agent_id}
  prompt: |
    You already have the upstream artifacts and implementation files
    in context from your prior review.

    The following changes were made to address your previous issues:

    ## Delta
    {delta_stat from git diff --stat}
    {delta_content from git diff}

    ## Fix Summary
    {implementer fix summary text from this iteration}

    Review the changes above. Assess whether your previous issues are resolved
    and check for new issues introduced by the fixes.

    This is iteration {iteration} of {max}.

    Return your assessment as JSON:
    {
      "approved": true/false,
      "issues": [{"severity": "blocker|warning|suggestion", "category": "injection|auth|crypto|exposure|config", "description": "...", "location": "...", "suggestion": "..."}],
      "summary": "..."
    }
```

**If resume succeeds**: Update resume_state:
```
resume_state["security-reviewer"].agent_id = {agent_id from resumed Task result}
resume_state["security-reviewer"].last_iteration = {iteration}
resume_state["security-reviewer"].last_commit_sha = {current HEAD SHA}
```

**If resume fails** (Task tool returns an error): I3 fallback — fresh I1-R4 dispatch (same template as iteration 1, with additional line in prompt: `"(Fresh dispatch — prior review session unavailable.)"` and previous issues appended). Log to `.review-history.md`: `RESUME-FALLBACK: security-reviewer iteration {iteration} — {error summary}`. Reset `resume_state["security-reviewer"]` with the new fresh dispatch's agent_id.

**If is_final_validation AND this reviewer previously passed (status "passed")** — attempt I2-FV resumed dispatch:

No delta size guard for final validation. Compute the diff between the reviewer's last review commit and current HEAD:
```
Bash: git diff {resume_state["security-reviewer"].last_commit_sha} HEAD --stat
Bash: git diff {resume_state["security-reviewer"].last_commit_sha} HEAD
```

```
Task tool call:
  resume: {resume_state["security-reviewer"].agent_id}
  prompt: |
    You already have the upstream artifacts and implementation files
    in context from your prior review at iteration {resume_state["security-reviewer"].last_iteration}.

    Since your last review, the following fixes were applied to address
    issues from other reviewers:

    ## Changes Since Your Last Review
    {git diff --stat between last_iteration commit and current HEAD}
    {git diff between last_iteration commit and current HEAD}

    ## Fix Summary
    {consolidated fix summaries from all intermediate iterations (from fix_summaries list)}

    Perform a full regression check. Verify your previous approval still
    holds given these changes, and check for any new issues.

    This is the final validation round (iteration {iteration} of {max}).

    Return your assessment as JSON:
    {
      "approved": true/false,
      "issues": [{"severity": "blocker|warning|suggestion", "category": "injection|auth|crypto|exposure|config", "description": "...", "location": "...", "suggestion": "..."}],
      "summary": "..."
    }
```

**If I2-FV resume succeeds**: Update resume_state:
```
resume_state["security-reviewer"].agent_id = {agent_id from resumed Task result}
resume_state["security-reviewer"].last_iteration = {iteration}
resume_state["security-reviewer"].last_commit_sha = {current HEAD SHA}
```

**If I2-FV resume fails**: I3 fallback — fresh I1-R4 dispatch (same template as iteration 1, with `"(Fresh dispatch — prior review session unavailable.)"` annotation). Log: `RESUME-FALLBACK: security-reviewer iteration {iteration} — {error summary}`. Reset `resume_state["security-reviewer"]`.

**Context compaction detection**: Before attempting any resume (I2 or I2-FV), if `resume_state["security-reviewer"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I1-R4 dispatch. Log: `RESUME-FALLBACK: security-reviewer iteration {iteration} — agent_id lost (context compaction)`.

**Fallback detection (I9):** After receiving the security-reviewer's response, search for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: security-reviewer did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I2/I2-FV templates) do not include Required Artifacts, so "Files read:" may not appear — only apply I9 detection to fresh dispatches.

<!-- influence-tracking-site: s13 -->
**Influence tracking (mandatory, unconditional):**
Call `record_influence_by_content(
  subagent_output_text=<full agent output text>,
  injected_entry_names=<list from search_memory results, or [] if none>,
  agent_role="security-reviewer",
  feature_type_id=<current feature type_id from .meta.json>)`
Emit one line to your output: `Influence recorded: N matches`.
On MCP failure: warn "Influence tracking failed: {error}", continue.
If .meta.json missing or type_id unresolvable: skip with warning.

**7d. Selective Dispatch Logic:**

Determine which reviewers to dispatch this iteration:

```
IF iteration == 1:
  → Dispatch all 4 reviewers sequentially by level (7a → 7a2 → 7b + 7c)

ELIF is_final_validation:
  → Dispatch all 4 reviewers sequentially by level (7a → 7a2 → 7b + 7c) — full regression check

ELSE (intermediate iteration):
  → Only dispatch reviewers where reviewer_status == "failed"
  → Skip reviewers where reviewer_status == "passed"
  → Maintain level order: Level 1 before Level 2 before Level 3
```

**7e. Collect Results and Update State:**

Collect results from all dispatched reviewers.

**Apply strict threshold to each dispatched reviewer result:**
- **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
- **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"

Update `reviewer_status` for each dispatched reviewer based on its result.

**Decision logic:**

```
all_individually_passed = every reviewer has reviewer_status == "passed"
all_dispatched_passed = every reviewer dispatched THIS iteration passed

IF all_dispatched_passed AND is_final_validation:
  → APPROVED. Mark phase completed. Proceed to step 8.

ELIF all_individually_passed AND NOT is_final_validation:
  → Trigger final validation: set is_final_validation = true
  → Increment iteration counter
  → If iteration >= 3 (circuit breaker): handle circuit breaker (see below)
  → Else: Loop back to 7d (dispatch all 3 reviewers)

ELIF some dispatched reviewers failed:
  → Append iteration to .review-history.md
  → Dispatch implementer to fix issues from FAILED reviewers only
  → Increment iteration counter
  → If iteration >= 3 (circuit breaker): handle circuit breaker (see below)
  → Else: Loop back to 7d (dispatch only failed reviewers)
```

**Edge case — final validation catches regression:**
If the final validation round fails (e.g., security passed in iter 1, but a quality fix introduced a security issue):
- That reviewer's `reviewer_status` becomes `failed`, `is_final_validation` resets to `false`
- Normal fix cycle resumes — only the newly-failed reviewer dispatches next iteration
- When it passes again → another final validation round triggers
- Circuit breaker still applies to total iterations

**Implementer fix dispatch** (only includes issues from failed reviewers):

Use the PRD line resolved in Step 6 (I8).

**Dispatch decision for implementer:**

**If resume_state["implementer"] is missing/empty OR resume_state["implementer"].agent_id is null** — use fresh I7 dispatch:

**Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
limit=5, brief=true.
Store the returned entry names for post-dispatch influence tracking.
Include non-empty results inside the prompt below.

```
Task tool call:
  description: "Fix review issues iteration {n}"
  subagent_type: pd:implementer
  model: opus
  prompt: |
    Fix the following review issues:

    ## Required Artifacts
    You MUST read the following files before beginning your work.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    {resolved PRD line from I8}
    - Spec: {feature_path}/spec.md
    - Design: {feature_path}/design.md
    - Plan: {feature_path}/plan.md
    - Tasks: {feature_path}/tasks.md

    ## All Implementation Files
    {complete list of all files assigned to this implementation task}

    ## Issues to fix (from failed reviewers only)
    {consolidated issue list from reviewers with reviewer_status == "failed"}

    After fixing, return summary of changes made.

    ## Relevant Engineering Memory
    {search_memory results from the pre-dispatch call above}
```

After fresh dispatch: capture the `agent_id` from the Task tool result. Record the character count of the prompt above as `prompt_length`. Store in resume_state:
```
resume_state["implementer"] = {
  "agent_id": {agent_id from Task result},
  "iteration1_prompt_length": {prompt_length} (only set on first fix dispatch; preserved on subsequent fresh dispatches),
  "last_iteration": {iteration},
  "last_commit_sha": {HEAD SHA before fix}
}
```
If this is not the first fix dispatch (fresh dispatch due to fallback/reset), preserve the original `iteration1_prompt_length` from the first fresh dispatch if available; otherwise set it from this dispatch's prompt length.

**If resume_state["implementer"] exists with non-null agent_id** — attempt I7 resumed dispatch:

First, determine the list of files changed since last fix iteration:
```
Bash: git diff {resume_state["implementer"].last_commit_sha} HEAD --name-only
```
Capture output as `changed_files_list`.

**Delta size guard**: Construct the I7 resumed prompt below. If its character count > 50% of `resume_state["implementer"].iteration1_prompt_length`, the prompt is too large — fall back to fresh I7 dispatch (same template as above). Reset `resume_state["implementer"]`.

**If within threshold**, attempt I7 resumed dispatch:
```
Task tool call:
  resume: {resume_state["implementer"].agent_id}
  prompt: |
    You already have the upstream artifacts and implementation files
    in context from your previous fix session.

    ## New Issues to Fix
    {consolidated issue list from reviewers that failed THIS iteration}

    ## Changed Files to Re-read
    {changed_files_list — implementer should re-read these}

    ## All Implementation Files (for reference)
    {complete list of all files assigned to this implementation task}

    Fix all listed issues. After fixing, briefly summarize what you changed.
```

**If I7 resume succeeds**: Update resume_state:
```
resume_state["implementer"].agent_id = {agent_id from resumed Task result}
resume_state["implementer"].last_iteration = {iteration}
```

**If I7 resume fails** (Task tool returns an error): I3 fallback — fresh I7 dispatch (same template as above, with `"(Fresh dispatch — prior fix session unavailable.)"` annotation). Log to `.review-history.md`: `RESUME-FALLBACK: implementer iteration {iteration} — {error summary}`. Reset `resume_state["implementer"]` with the new fresh dispatch's agent_id.

**Context compaction detection**: Before attempting I7 resume, if `resume_state["implementer"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I7 dispatch. Log: `RESUME-FALLBACK: implementer iteration {iteration} — agent_id lost (context compaction)`.

**Fallback detection (I9):** After receiving the implementer's response, search for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: implementer did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I7 resumed template) do not include Required Artifacts, so "Files read:" may not appear — only apply I9 detection to fresh dispatches.

<!-- influence-tracking-site: s14 -->
**Influence tracking (mandatory, unconditional):**
Call `record_influence_by_content(
  subagent_output_text=<full agent output text>,
  injected_entry_names=<list from search_memory results, or [] if none>,
  agent_role="implementer",
  feature_type_id=<current feature type_id from .meta.json>)`
Emit one line to your output: `Influence recorded: N matches`.
On MCP failure: warn "Influence tracking failed: {error}", continue.
If .meta.json missing or type_id unresolvable: skip with warning.

**7e-commit. Per-iteration git commit after implementer fixes:**

After the implementer fix dispatch completes (whether fresh or resumed), commit the changes and capture delta for subsequent reviewer resume dispatches:

```
Bash: git add {space-separated list of files from files_changed} && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "pd: implement review iteration {n} fixes" && echo COMMIT_OK || echo COMMIT_FAILED)
```

Handle the three outcomes:

- **NO_CHANGES**: No changes were committed. The reviewers will use fresh I1-R4 dispatches since there is no meaningful delta to resume with.

- **COMMIT_FAILED**: Git commit failed. Proceed with fresh I1-R4 dispatches for reviewers.

- **COMMIT_OK**: Commit succeeded. Capture the new SHA and compute delta:
  ```
  Bash: git rev-parse HEAD
  ```
  Capture as `new_sha`.
  ```
  Bash: git diff {resume_state[reviewer_role].last_commit_sha for the reviewer being dispatched next} HEAD --stat
  Bash: git diff {resume_state[reviewer_role].last_commit_sha for the reviewer being dispatched next} HEAD
  ```
  Capture as `delta_stat` and `delta_content` respectively. These are used by the I2 resumed templates in 7a/7b/7c above.

  Update `resume_state["implementer"].last_commit_sha = new_sha`.

  Append the implementer's fix summary to `fix_summaries` list for use by I2-FV templates.

**Circuit breaker (iteration >= 3):**
```
AskUserQuestion:
  questions: [{
    "question": "Review loop reached 3 iterations without full approval. How to proceed?",
    "header": "Circuit Breaker",
    "options": [
      {"label": "Force approve with warnings", "description": "Accept current state, log unresolved issues"},
      {"label": "Pause and review manually", "description": "Stop loop, inspect code yourself"},
      {"label": "Abandon changes", "description": "Discard implementation, return to planning"}
    ],
    "multiSelect": false
  }]
```
- "Force approve": Record unresolved issues in `.meta.json` reviewerNotes, proceed to step 8
- "Pause and review manually": Stop execution, output file list for manual review
- "Abandon changes": Stop execution, do NOT mark phase completed

**Review History Entry Format** (append to `.review-history.md`):
```markdown
## Iteration {n} - {ISO timestamp} {final_validation_tag}

**Level 1 — Implementation Review:** {Approved / Issues found / Skipped (passed iter {m})}
  - Task Completeness: {pass/fail}
  - Spec Compliance: {pass/fail}
  - Design Alignment: {pass/fail}
  - PRD Delivery: {pass/fail}
**Level 2 — Relevance Verification:** {Approved / Issues found / Skipped (passed iter {m})}
  - Coverage: {pass/fail}
  - Completeness: {pass/fail}
  - Testability: {pass/fail}
  - Coherence: {pass/fail}
**Level 3 — Quality Review:** {Approved / Issues found / Skipped (passed iter {m})}
**Level 3 — Security Review:** {Approved / Issues found / Skipped (passed iter {m})}

**Issues:**
- [{severity}] [{level}] {reviewer}: {description} (at: {location})
  Suggestion: {suggestion}

**Changes Made:**
{Summary of revisions made to address issues}

---
```

Where `{final_validation_tag}` is `[FINAL VALIDATION]` when the iteration is a mandatory full regression review, otherwise empty. Skipped reviewers show which iteration they last passed in.

### 7f. Capture Review Learnings (Automatic)

**Trigger:** Execute after any review iteration that found blocker or warning issues.

**Two-path capture:**
- **IF exactly 1 iteration with blockers found and fixed:** Store each blocker directly via `store_memory` with `confidence="low"` (single observation, not a confirmed pattern). Budget: max 2 entries.
- **IF 2+ iterations:** Use recurring-pattern grouping logic below. Budget: max 3 entries.

**Process (for 2+ iterations):**
1. Read `.review-history.md` entries for THIS phase only (implementation-reviewer, relevance-verifier, code-quality-reviewer, and security-reviewer entries)
2. Group issues by description similarity (same category, overlapping file patterns)
3. Identify issues that appeared in 2+ iterations — these are recurring patterns

**For each recurring issue, call `store_memory`:**
- `name`: derived from issue description (max 60 chars)
- `description`: issue description + the suggestion that resolved it
- `reasoning`: "Recurred across {n} review iterations in feature {id} implement phase"
- `category`: infer from issue type:
  - Security issues → `anti-patterns`
  - Quality/SOLID/naming → `heuristics`
  - Missing requirements → `anti-patterns`
  - Feasibility/complexity → `heuristics`
  - Scope/assumption issues → `heuristics`
- `references`: ["feature/{id}-{slug}"]
- `confidence`: "low"

**Budget:** Max 3 entries per review cycle to avoid noise.

**Notable catches (single-iteration blockers):**
If the review loop completed in 1 iteration AND the reviewer found issues with severity "blocker":
1. For each blocker issue (max 2):
   - Store via `store_memory` MCP tool:
     - `name`: derived from issue description (max 60 chars)
     - `description`: issue description + the suggestion that resolved it
     - `reasoning`: "Single-iteration blocker catch in feature {id} implement phase"
     - `category`: inferred from issue type (same mapping as recurring patterns above)
     - `confidence`: "low"
     - `references`: ["feature/{id}-{slug}"]

**Circuit breaker capture:** If review loop hit max iterations (cap reached), also capture a single entry:
- `name`: "Implement review cap: {brief issue category}"
- `description`: summary of unresolved issues that prevented approval
- `category`: "anti-patterns"
- `confidence`: "low"

**Fallback:** If `store_memory` MCP tool unavailable, use `semantic_memory.writer` CLI.

**Output:** `"Review learnings: {n} patterns captured from {m}-iteration review cycle"` (inline, no prompt)

### 8. Update State on Completion

**Construct reviewerNotes before committing:**
```
capReached = (iteration == 3 at exit without approval)
Merge all 4 reviewers' (implementation-reviewer, relevance-verifier, code-quality-reviewer, security-reviewer) final issues[] into one array.
If any reviewer response lacks .issues[] or is not valid JSON: skip that reviewer's issues.
If capReached: reviewerNotes = merged issues[].map(i => {severity: i.severity, description: i.description})
Else: reviewerNotes = merged issues[].filter(i => i.severity in ["warning", "suggestion"]).map(i => {severity: i.severity, description: i.description})
Deduplicate: if two issues reference the same file/function AND have overlapping keywords in descriptions, keep only the higher-severity one. When uncertain, keep both.
```

Follow `commitAndComplete("implement", [], iteration, capReached, reviewerNotes)` from the **workflow-transitions** skill.

### 9. Completion Message

Output: "Implementation complete."

```
AskUserQuestion:
  questions: [{
    "question": "Implementation complete. Continue to next phase?",
    "header": "Next Step",
    "options": [
      {"label": "Continue to /pd:finish-feature (Recommended)", "description": "Complete the feature"},
      {"label": "Review implementation first", "description": "Inspect the code before finishing"},
      {"label": "Fix and rerun reviews", "description": "Apply fixes then rerun the 3-level review cycle"}
    ],
    "multiSelect": false
  }]
```

If "Continue to /pd:finish-feature (Recommended)": Invoke `/pd:finish-feature`
If "Review implementation first": Show "Run /pd:finish-feature when ready." → STOP
If "Fix and rerun reviews": Ask user what needs fixing (plain text via AskUserQuestion with free-text), apply the requested changes to the implementation, then reset `resume_state = {}` and `fix_summaries = []` (clear all entries — the user has made manual edits outside the review loop, so prior agent contexts are stale) and return to Step 7 (3-reviewer loop) with the iteration counter reset to 0.

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Read {pd_artifacts_root}/features/ to find active feature, then follow the workflow below.
