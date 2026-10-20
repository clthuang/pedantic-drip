# Plan: Phase Transition Summary

## Overview

6 tasks modifying markdown skill/command files. No Python code, no tests. All changes are to LLM-interpreted procedural templates.

## Execution Order

```
Task 1: Extend commitAndComplete signature + add Step 3
  ↓
Task 2: Update specify.md call site (validates the pattern)
  ↓
Tasks 3-6 (parallel, same pattern as Task 2):
  Task 3: Update design.md call site
  Task 4: Update create-plan.md call site
  Task 5: Update create-tasks.md call site
  Task 6: Update implement.md call site
```

Task 2 runs first after Task 1 to validate the reviewerNotes construction pattern. Once confirmed, Tasks 3-6 apply the same pattern to other commands.

## Tasks

### Task 1: Add Step 3 (Phase Summary) to commitAndComplete

**File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
**Why:** Central function that all commands call — must be updated first to define the new contract.

**Changes:**
1. Update the signature line from `commitAndComplete(phaseName, artifacts[])` to `commitAndComplete(phaseName, artifacts[], iterations, capReached, reviewerNotes[])`
2. Update Step 2's `complete_phase` MCP call to wire the new parameters:
   - `iterations={iterations}` (direct pass-through of the new parameter)
   - `reviewer_notes='{JSON serialization of reviewerNotes[].map(n => n.description)}'` — serialize the description strings into a JSON array string, since `complete_phase` expects `reviewer_notes` as a string, not an object array
3. Confirm Step 1 (Auto-Commit) handles empty `artifacts[]` gracefully: the `git add` command becomes `git add {pd_artifacts_root}/features/{id}-{slug}/.meta.json {pd_artifacts_root}/features/{id}-{slug}/.review-history.md` (no artifacts prefix) — this is valid bash
4. Add new **Step 3: Phase Summary** section after Step 2, containing:
   - Outcome decision table (capReached → iterations==1 → iterations>1 → notes non-empty)
   - Header line format: `"{PhaseName} complete ({N} iteration(s)). {outcome}."`
   - Artifacts line: `"Artifacts: {comma-separated filenames}"` (omit when `artifacts[]` empty)
   - Feedback section with `[W]`/`[S]` prefixes per spec, max 5 items, sorted by severity (warnings first, then suggestions). Note: when capReached is true, blocker-severity items are included in the list but displayed with `[W]` prefix (spec only defines `[W]`/`[S]` — blockers are surfaced as high-priority warnings in the display)
   - Cap-reached variant header: "Unresolved issues carried forward:"
   - Clean pass: "All reviewer issues resolved."
   - 12-line max, 100-char truncation per feedback line

**Prerequisite:** None (must be done first).

**Verification:** Read the updated SKILL.md and confirm: Step 3 follows Step 2; uses iterations, capReached, and reviewerNotes parameters; Step 2 wires parameters to complete_phase correctly; output format matches design.

### Task 2: Update specify.md call site

**File:** `plugins/pd/commands/specify.md`
**Why:** Dual-reviewer phase (spec-reviewer + phase-reviewer) — validates the most complex pattern first.

**Changes:**
1. At the `commitAndComplete` call site (section 4b), change to: `commitAndComplete("specify", ["spec.md"], iteration + phase_iteration, capReached, reviewerNotes)`
2. Before the call, add reviewerNotes construction block:
   ```
   Construct reviewerNotes from phase-reviewer's final issues[]:
   - If phase-reviewer response lacks .issues[] or is not valid JSON: reviewerNotes = []
   - If capReached: reviewerNotes = issues[].map(i => {severity: i.severity, description: i.description})
   - Else: reviewerNotes = issues[].filter(i => i.severity in ["warning", "suggestion"]).map(...)
   ```
3. Compute capReached: `capReached = (iteration == 5 at Step 1 exit without approval) OR (phase_iteration == 5 at Step 2 exit without approval)`
4. Note: `iteration` and `phase_iteration` are already scoped to the current run (they reset on "Fix and rerun"), so their sum naturally gives the final-run-only total

**Dependency:** Task 1

### Task 3: Update design.md call site

**File:** `plugins/pd/commands/design.md`
**Why:** Also dual-reviewer — same pattern as Task 2.

**Changes:** Same pattern as Task 2:
1. At section 4c `commitAndComplete` call, change to: `commitAndComplete("design", ["design.md"], iteration + phase_iteration, capReached, reviewerNotes)`
2. Add reviewerNotes construction from phase-reviewer's final issues[] (same block as Task 2)
3. Compute capReached from both design-reviewer and phase-reviewer stage exits
4. Error handling for malformed response

**Dependency:** Task 1

### Task 4: Update create-plan.md call site

**File:** `plugins/pd/commands/create-plan.md`
**Why:** Single-reviewer phase (plan-reviewer + phase-reviewer in two-step loop) — simpler pattern.

**Changes:**
1. At section 4b `commitAndComplete` call, change to: `commitAndComplete("create-plan", ["plan.md"], iteration + phase_iteration, capReached, reviewerNotes)`
2. Add reviewerNotes construction from phase-reviewer's final `issues[]`
3. Compute `capReached = (iteration == 5 at Step 1 exit without approval) OR (phase_iteration == 5 at Step 2 exit without approval)`
4. Error handling: if response lacks `.issues[]`, set `reviewerNotes = []`

**Note:** create-plan.md has a two-step reviewer loop (plan-reviewer Step 1, phase-reviewer Step 2), so iterations = `iteration + phase_iteration`. **Design deviation:** design.md (line 131) incorrectly categorizes create-plan as "single-reviewer" with `iterations = iteration`, but codebase confirms two-step structure. Using actual structure.

**Dependency:** Task 1

### Task 5: Update create-tasks.md call site

**File:** `plugins/pd/commands/create-tasks.md`
**Why:** Same two-step pattern as create-plan. **Design deviation:** same as Task 4 — design says single-reviewer but codebase has two-step loop.

**Changes:**
1. At section 5b `commitAndComplete` call, change to: `commitAndComplete("create-tasks", ["tasks.md"], iteration + phase_iteration, capReached, reviewerNotes)`
2. Add reviewerNotes construction from phase-reviewer's final `issues[]`
3. Compute capReached from both reviewer stages
4. Error handling for malformed response

**Dependency:** Task 1

### Task 6: Update implement.md call site

**File:** `plugins/pd/commands/implement.md`
**Why:** Most complex — 3 concurrent reviewers, currently uses partial commitAndComplete.

**Behavioral change:** This task changes implement.md from "Step 2 only" to full `commitAndComplete`, which adds auto-commit+push behavior (Step 1) where none existed before. The design explicitly requires this (design.md line 128). Step 1 with empty `artifacts[]` commits only .meta.json and .review-history.md — verified safe in Task 1 change #3. **Edge case:** If review iterations already committed .meta.json/.review-history.md, Step 1's `git commit` may produce "nothing to commit". Task 1 must update Step 1 to treat "nothing to commit" as a success path (skip to Step 2) rather than an error.

**Changes:**
1. Replace the current "Follow the state update step from `commitAndComplete`" (section 8) with a full `commitAndComplete("implement", [], iteration, capReached, reviewerNotes)` call
2. Before the call, add reviewerNotes construction:
   - Merge all 3 concurrent reviewers' (implementation-reviewer, code-quality-reviewer, security-reviewer) final `issues[]` into one array
   - Filter: if capReached, keep all severities; else keep warning/suggestion only
   - Deduplicate: if two issues reference the same file/function AND have overlapping keywords in descriptions, keep only the higher-severity one. When uncertain, keep both.
   - Map to `{severity, description}` objects
3. Compute `capReached = (iteration == 5 at exit without approval)` — implement.md uses `iteration` as the loop counter variable (confirm by reading Step 7 loop initialization)
4. Error handling for malformed responses from any of the 3 reviewers

**Dependency:** Task 1

## Verification Checklist

After all tasks, verify each acceptance criterion by reading the modified files:

| AC | Check | File(s) |
|----|-------|---------|
| AC-1 | All 5 commands pass iterations, capReached, reviewerNotes to commitAndComplete | All 5 command files |
| AC-2 | Step 3 outputs header with iteration count and outcome | SKILL.md |
| AC-3 | Decision table row 2: iterations==1 + empty notes → "Approved on first pass." + "All reviewer issues resolved." | SKILL.md |
| AC-4 | Decision table row 1: capReached → "Review cap reached." + "Unresolved issues carried forward:" + blockers included | SKILL.md + command files (reviewerNotes includes blockers when capReached) |
| AC-5 | Feedback items prefixed with `[W]`/`[S]` | SKILL.md |
| AC-6 | Summary logic only in SKILL.md Step 3, not in any command file | All 6 files |
| AC-7 | AskUserQuestion blocks unchanged in all 5 commands | All 5 command files |
| AC-8 | Artifacts line omitted when artifacts[] empty (implement path) | SKILL.md Step 3 |

**Smoke test:** After all tasks, run at least one phase command to completion and visually confirm the summary block renders before the AskUserQuestion prompt, per spec verification guidance.
