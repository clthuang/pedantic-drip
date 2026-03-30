# Tasks: Phase Transition Summary

## Phase 1: Core (sequential)

### Task 1.1: Extend commitAndComplete signature in SKILL.md
- **File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
- **Action:** Update the `## commitAndComplete(phaseName, artifacts[])` header and description to `commitAndComplete(phaseName, artifacts[], iterations, capReached, reviewerNotes[])`
- **Done when:** Signature line shows 5 parameters with descriptions for iterations (integer), capReached (boolean), reviewerNotes[] (object array with severity+description)
- **Depends on:** nothing

### Task 1.2: Wire new parameters to complete_phase MCP call in Step 2
- **File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
- **Action:** In Step 2, replace `iterations={count}` with `iterations={iterations}` and replace `reviewer_notes='["any unresolved concerns"]'` with `reviewer_notes='{JSON serialization of reviewerNotes[].map(n => n.description)}'`
- **Done when:** Step 2's complete_phase call uses the caller-provided iterations and serialized reviewerNotes descriptions
- **Depends on:** 1.1

### Task 1.3: Add nothing-to-commit success path to Step 1
- **File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
- **Action:** In Step 1 Error handling (~line 187-189, after "On commit failure: Display error..." and "On push failure: Commit succeeds locally..."), append a third bullet: "On nothing to commit (git commit output contains 'nothing to commit'): treat as success — skip to Step 2. This handles implement phase where review-loop commits may have already staged .meta.json/.review-history.md."
- **Done when:** Error handling has three cases: commit failure (block), push failure (warn), nothing-to-commit (skip)
- **Depends on:** 1.1

### Task 1.4: Add Step 3 Phase Summary section
- **File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
- **Action:** Add `### Step 3: Phase Summary` after Step 2 with:
  - Outcome decision table: (1) capReached → "Review cap reached." (2) iterations==1 AND reviewerNotes empty → "Approved on first pass." (3) iterations>1 AND reviewerNotes empty → "Approved after {N} iterations." (4) reviewerNotes non-empty → "Approved with notes."
  - Output header line: `"{PhaseName} complete ({N} iteration(s)). {outcome}."`
  - Artifacts line: `"Artifacts: {comma-separated filenames}"` — omit when artifacts[] empty
  - Feedback section when reviewerNotes non-empty: `"Remaining feedback ({W} warnings, {S} suggestions):"` with `[W]`/`[S]` prefixed items, max 5, sorted by severity (warnings first). Blocker items displayed with `[W]` prefix. Cap-reached variant: `"Unresolved issues carried forward:"`. Truncate descriptions at 100 chars. If >5 items: `"...and {N} more"`
  - Clean pass when reviewerNotes empty: `"All reviewer issues resolved."`
  - 12-line max constraint note
- **Done when:** Step 3 section exists after Step 2, contains decision table, output format, and all edge cases
- **Depends on:** 1.2

## Phase 2: Command call sites (parallel after Phase 1)

### Task 2.1: Update specify.md call site
- **File:** `plugins/pd/commands/specify.md`
- **Action:** At section 4b (commitAndComplete call), add reviewerNotes construction block before the call: extract phase-reviewer's final issues[], filter to warning/suggestion (or all if capReached), map to {severity, description}. Error handling: if response lacks issues[], set reviewerNotes=[]. Compute capReached = (iteration==5 at Step 1 exit without approval) OR (phase_iteration==5 at Step 2 exit without approval). Change call to `commitAndComplete("specify", ["spec.md"], iteration + phase_iteration, capReached, reviewerNotes)`. Note: iteration and phase_iteration already scoped to current run (reset on "Fix and rerun").
- **Done when:** specify.md passes 5 parameters to commitAndComplete with correct reviewerNotes construction
- **Depends on:** 1.4

### Task 2.2: Update design.md call site
- **File:** `plugins/pd/commands/design.md`
- **Action:** Same pattern as Task 2.1. At section 4c, add reviewerNotes construction from phase-reviewer's final issues[]. Change call to `commitAndComplete("design", ["design.md"], iteration + phase_iteration, capReached, reviewerNotes)`. Variables: iteration (design-reviewer loop), phase_iteration (phase-reviewer loop).
- **Done when:** design.md passes 5 parameters with correct construction
- **Depends on:** 1.4

### Task 2.3: Update create-plan.md call site
- **File:** `plugins/pd/commands/create-plan.md`
- **Pre-step:** Read create-plan.md section 4 and confirm the loop variable names for both stages. If two-step loop exists, use actual variable names found; if single-step, use `iterations = iteration` only.
- **Action:** At section 4b, add reviewerNotes construction from phase-reviewer's final issues[]. Change call to `commitAndComplete("create-plan", ["plan.md"], iteration + phase_iteration, capReached, reviewerNotes)`. Two-step loop: iteration (plan-reviewer), phase_iteration (phase-reviewer). Design deviation: design says single-reviewer but codebase has two-step loop — use actual structure.
- **Done when:** create-plan.md passes 5 parameters with correct construction
- **Depends on:** 1.4

### Task 2.4: Update create-tasks.md call site
- **File:** `plugins/pd/commands/create-tasks.md`
- **Pre-step:** Read create-tasks.md section 5 and confirm the two-step loop variable names before writing.
- **Action:** At section 5b, add reviewerNotes construction from phase-reviewer's final issues[]. Change call to `commitAndComplete("create-tasks", ["tasks.md"], iteration + phase_iteration, capReached, reviewerNotes)`. Two-step loop same as create-plan. Design deviation same as Task 2.3.
- **Done when:** create-tasks.md passes 5 parameters with correct construction
- **Depends on:** 1.4

### Task 2.5: Update implement.md call site
- **File:** `plugins/pd/commands/implement.md`
- **Action:** Replace "Follow the state update step from `commitAndComplete`" (section 8) with full `commitAndComplete("implement", [], iteration, capReached, reviewerNotes)`. Before the call: merge all 3 reviewers' (implementation-reviewer, code-quality-reviewer, security-reviewer) final issues[] into one array. Filter: if capReached keep all severities, else warning/suggestion only. Deduplicate: same file/function + overlapping keywords → keep higher-severity. Map to {severity, description}. Error handling for malformed responses. capReached = (iteration==5 at exit without approval). Behavioral change: adds Step 1 auto-commit (empty artifacts[] commits .meta.json/.review-history.md only) — design-required.
- **Done when:** implement.md calls full commitAndComplete with 5 parameters, multi-reviewer merge logic present, dedup rule includes "when uncertain, keep both" fallback
- **Depends on:** 1.4

## Phase 3: Verification

### Task 3.1: Run verification checklist
- **Action:** Read the modified SKILL.md and all 5 command files. Verify each AC from the plan's Verification Checklist:
  - AC-1: All 5 commands pass iterations, capReached, reviewerNotes to commitAndComplete
  - AC-2: Step 3 outputs header with iteration count and outcome
  - AC-3: iterations==1 + empty notes → "Approved on first pass." + "All reviewer issues resolved."
  - AC-4: capReached → "Review cap reached." + "Unresolved issues carried forward:" + blocker items with [W] prefix
  - AC-5: Feedback items prefixed with [W]/[S]
  - AC-6: Summary logic only in SKILL.md Step 3
  - AC-7: AskUserQuestion blocks unchanged
  - AC-8: Artifacts line omitted when empty
- **Done when:** All 8 ACs verified by reading the files
- **Depends on:** 2.1, 2.2, 2.3, 2.4, 2.5
