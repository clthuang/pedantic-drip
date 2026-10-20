# Tasks: Token Efficiency Improvements

## Overview

18 tasks across 4 parallel phases. Converts all inline artifact injection (`{content of X.md}`) to lazy-load file references with role-specific pruning.

**Parallel Phases:**
- Phase A: Task 1 (de-risk hybrid pattern — implementing/SKILL.md)
- Phase B: Tasks 2-9 (4 phase commands, 2 dispatches each — parallel across files, sequential within)
- Phase C: Tasks 10-15 (implement.md — 6 dispatches, sequential within file)
- Phase D: Tasks 16-18 (verification — after all conversions complete)

Phase B and C can run in parallel (different files). Phase D depends on all of A+B+C.

Task 1 (Phase A) should complete first to validate the lazy-load pattern before applying it to other files. Tasks 2-15 may then proceed (B and C in parallel).

---

## Shared Templates

Referenced by Tasks 2-15. Defined once here; each task adapts per its role-specific artifact mapping.

### I1: Required Artifacts Block

`{feature_path}` is the absolute path to the active feature directory, resolved from `.meta.json` or the feature directory discovered in step 1 of the orchestrating command (e.g., `docs/dev_artifacts/workitems/030-token-efficiency-improvements/`).

```
## Required Artifacts
You MUST read the following files before beginning your review.
After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
{for each artifact in the task's artifact list:}
- {Artifact Name}: {feature_path}/{artifact}
{if prd.md is in the list, use resolve_prd() output instead of literal path}
```

### I8: resolve_prd() Logic

Insert in the orchestrating command's context assembly (before the Task tool call):
```
1. Check if {feature_path}/prd.md exists
2. If exists → emit "- PRD: {feature_path}/prd.md"
3. If not exists → check .meta.json for brainstorm_source
   a. If brainstorm_source exists → emit "- PRD: {brainstorm_source path}"
   b. If brainstorm_source not exists → emit "- PRD: No PRD — feature created without brainstorm"
```

### I9: Fallback Detection

Insert after receiving agent response, before JSON parsing:
```
1. Search response for pattern: "Files read:" followed by file names
2. If pattern found → pass (no action)
3. If pattern NOT found:
   a. Log to .review-history.md: "LAZY-LOAD-WARNING: {agent_type} did not confirm artifact reads"
   b. Do NOT block or retry — proceed with review result as-is
```

---

## Phase A: Implementing Skill Hybrid Template

### Task 1: Convert SKILL.md Step 2b to I7 hybrid dispatch

**Why:** Plan Step 1A.1, Design I7, I8, I9; Spec R2.3, R2.1

Convert the implementing skill's per-task dispatch template from inline injection to hybrid lazy-load. This is the most complex conversion — it retains extractSection() for plan.md and design.md while adding lazy-load for spec.md and prd.md.

**Changes to `plugins/iflow/skills/implementing/SKILL.md`:**
1. Find and remove the inline `## Spec` section — look for the line containing `{spec.md content}` (currently line ~117-118)
2. Find and remove the inline `## PRD Context` section — look for `## PRD Context` followed by `{Problem Statement + Goals from prd.md}` (currently lines ~126-127)
3. Add a `## Required Artifacts` block per I7 template with mandatory-read directive:
   ```
   ## Required Artifacts
   You MUST read the following files before beginning your work.
   After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
   {resolve_prd("prd.md") → emit path or "No PRD" sentinel}
   - Spec: {feature_path}/spec.md
   ```
4. Add I8 resolve_prd() logic (see Shared Templates) in two places: (a) Find the bullet `prd.md: extract ## Problem Statement...` in the "Assemble context for dispatch" block (currently line ~80). Replace that bullet in-place with: run resolve_prd() to obtain the PRD path string; the result is consumed by the Required Artifacts block (step 3), not emitted as a separate inline injection. (b) The `## PRD Context` / `{Problem Statement + Goals from prd.md}` section (removed in step 2) is replaced by the Required Artifacts reference from step 3 — no separate action needed here
5. Add I9 fallback detection (see Shared Templates) between Step 2b (dispatch) and Step 2c (collect report): after the agent response is received, scan for "Files read:" pattern and log LAZY-LOAD-WARNING to .review-history.md if absent, then proceed to Step 2c. Per design I9, this is non-blocking
6. Retain `## Design Context (scoped)` and `## Plan Context (scoped)` inline sections with extractSection() — these are NOT converted to lazy-load (TD4: extractSection preserves token-efficient scoping for plan.md and design.md in per-task dispatches)
7. Retain inline `{task description with done-when criteria}`, `## Project Context`, and `## Files to Work On` blocks unchanged

**Done when:**
- SKILL.md Step 2b dispatch template contains `## Required Artifacts` block with mandatory-read directive for spec.md and prd.md
- No `{spec.md content}` or `{Problem Statement + Goals from prd.md}` inline injection patterns remain in SKILL.md
- extractSection() for design.md and plan.md is preserved unchanged
- I8 PRD resolution logic is present in context assembly
- I9 fallback detection is present after response receipt

---

## Phase B: Phase Command Conversions

**Parallel groups:** Tasks 2, 4, 6, 8 (one domain-reviewer per file) can run concurrently. Within each file: domain-reviewer task must complete before phase-reviewer task since both edit the same file (2→3, 4→5, 6→7, 8→9).

### Task 2: Convert spec-reviewer dispatch in specify.md

**Why:** Plan Step 1B.1, Design I1, I5, I8, I9; Spec R2.1, R3.2

**Changes to `plugins/iflow/commands/specify.md`:**
1. In the Stage 1 spec-reviewer Task tool call, replace inline `## PRD (original requirements)\n{content of prd.md, or "None - feature created without brainstorm"}` with I1 Required Artifacts block
2. Spec.md is the review target — remains inline in the prompt body (not in Required Artifacts)
3. Apply I5 mapping: spec-reviewer gets `["prd.md"]` only in Required Artifacts
4. Add I8 resolve_prd() to replace the `or "None"` conditional
5. Add I9 fallback detection after response, before JSON parsing
6. Replace parenthetical `(always a NEW Task tool dispatch per iteration)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)`

**Done when:**
- spec-reviewer dispatch has Required Artifacts block with prd.md only
- Spec content `{content of spec.md}` remains inline in the prompt body as the review target (not moved to Required Artifacts block)
- No `{content of prd.md...}` inline injection pattern in spec-reviewer dispatch
- I8 and I9 are present
- "always a NEW Task" directive is replaced

### Task 3: Convert phase-reviewer dispatch in specify.md

**Why:** Plan Step 1B.2, Design I1, I5, I8, I9; Spec R2.1, R3.2

**Changes to `plugins/iflow/commands/specify.md`:**
1. In the Stage 2 phase-reviewer Task tool call, replace inline PRD and Spec content blocks with I1 Required Artifacts block
2. Neither PRD nor Spec is the "review target" here (phase-reviewer reviews readiness) — both go in Required Artifacts
3. Apply I5 mapping: phase-reviewer gets `["prd.md", "spec.md"]`
4. Add I8 resolve_prd()
5. Add I9 fallback detection
6. Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)`

**Done when:**
- phase-reviewer dispatch has Required Artifacts block with prd.md and spec.md
- No inline `{content of prd.md...}` or `{content of spec.md}` in phase-reviewer dispatch
- I8 and I9 are present
- "always a NEW Task" directive is replaced

### Task 4: Convert design-reviewer dispatch in design.md

**Why:** Plan Step 1C.1, Design I1, I5, I8, I9; Spec R2.1, R3.2

Stage 0 research agents (codebase-explorer, internet-researcher) are excluded — they receive feature description summaries, not artifacts. No changes for those dispatches.

**Changes to `plugins/iflow/commands/design.md`:**
1. In the Stage 3 design-reviewer Task tool call, replace inline PRD and Spec content blocks with I1 Required Artifacts block
2. Design.md is the review target — remains inline in the prompt body
3. Apply I5 mapping: design-reviewer gets `["prd.md", "spec.md"]`
4. Add I8 resolve_prd()
5. Add I9 fallback detection
6. Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)`

**Done when:**
- design-reviewer dispatch has Required Artifacts block with prd.md and spec.md
- Design content remains inline as review target
- No `{content of prd.md...}` or `{content of spec.md}` in design-reviewer dispatch
- Stage 0 research agent dispatches are untouched
- I8 and I9 are present
- "always a NEW Task" directive is replaced

### Task 5: Convert phase-reviewer dispatch in design.md

**Why:** Plan Step 1C.2, Design I1, I5, I8, I9; Spec R2.1, R3.2

**Changes to `plugins/iflow/commands/design.md`:**
1. In the Stage 4 phase-reviewer Task tool call, replace inline PRD, Spec, and Design content blocks with I1 Required Artifacts block
2. Apply I5 mapping: phase-reviewer gets `["prd.md", "spec.md", "design.md"]`
3. Add I8 resolve_prd()
4. Add I9 fallback detection
5. Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)`

**Done when:**
- phase-reviewer dispatch has Required Artifacts block with prd.md, spec.md, design.md
- No inline `{content of ...}` patterns in phase-reviewer dispatch
- I8 and I9 are present
- "always a NEW Task" directive is replaced

### Task 6: Convert plan-reviewer dispatch in create-plan.md

**Why:** Plan Step 1D.1, Design I1, I5, I8, I9; Spec R2.1, R3.2

**Changes to `plugins/iflow/commands/create-plan.md`:**
1. In the Stage 1 plan-reviewer Task tool call, replace inline PRD, Spec, and Design content blocks with I1 Required Artifacts block
2. Plan.md is the review target — remains inline in the prompt body
3. Apply I5 mapping: plan-reviewer gets `["prd.md", "spec.md", "design.md"]`
4. Add I8 resolve_prd()
5. Add I9 fallback detection
6. Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)`

**Done when:**
- plan-reviewer dispatch has Required Artifacts block with prd.md, spec.md, design.md
- Plan content remains inline as review target
- No `{content of prd.md...}`, `{content of spec.md}`, or `{content of design.md}` in plan-reviewer dispatch
- I8 and I9 are present
- "always a NEW Task" directive is replaced

### Task 7: Convert phase-reviewer dispatch in create-plan.md

**Why:** Plan Step 1D.2, Design I1, I5, I8, I9; Spec R2.1, R3.2

**Changes to `plugins/iflow/commands/create-plan.md`:**
1. In the Stage 2 phase-reviewer Task tool call, replace inline PRD, Spec, Design, and Plan content blocks with I1 Required Artifacts block
2. Apply I5 mapping: phase-reviewer gets `["prd.md", "spec.md", "design.md", "plan.md"]`
3. Add I8 resolve_prd()
4. Add I9 fallback detection
5. Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)`

**Done when:**
- phase-reviewer dispatch has Required Artifacts block with prd.md, spec.md, design.md, plan.md
- No inline `{content of ...}` patterns in phase-reviewer dispatch
- I8 and I9 are present
- "always a NEW Task" directive is replaced

### Task 8: Convert task-reviewer dispatch in create-tasks.md

**Why:** Plan Step 1E.1, Design I1, I5, I8, I9; Spec R2.1, R3.2

**Changes to `plugins/iflow/commands/create-tasks.md`:**
1. In the Stage 1 task-reviewer Task tool call, replace inline PRD, Spec, Design, and Plan content blocks with I1 Required Artifacts block
2. Tasks.md is the review target — remains inline in the prompt body
3. Apply I5 mapping: task-reviewer gets `["prd.md", "spec.md", "design.md", "plan.md"]`
4. Add I8 resolve_prd()
5. Add I9 fallback detection
6. Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)`

**Done when:**
- task-reviewer dispatch has Required Artifacts block with prd.md, spec.md, design.md, plan.md
- Tasks content remains inline as review target
- No `{content of prd.md...}`, `{content of spec.md}`, `{content of design.md}`, or `{content of plan.md}` in task-reviewer dispatch
- I8 and I9 are present
- "always a NEW Task" directive is replaced

### Task 9: Convert phase-reviewer dispatch in create-tasks.md

**Why:** Plan Step 1E.2, Design I1, I5, I8, I9; Spec R2.1, R3.2

**Changes to `plugins/iflow/commands/create-tasks.md`:**
1. In the Stage 2 phase-reviewer Task tool call, replace inline content blocks with I1 Required Artifacts block
2. Apply I5 mapping: phase-reviewer gets `["prd.md", "spec.md", "design.md", "plan.md", "tasks.md"]`
3. Add I8 resolve_prd()
4. Add I9 fallback detection
5. Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)`

**Done when:**
- phase-reviewer dispatch has Required Artifacts block with all 5 artifacts
- No inline `{content of ...}` patterns in phase-reviewer dispatch
- I8 and I9 are present
- "always a NEW Task" directive is replaced

---

## Phase C: implement.md Command Conversions

Tasks 10-15 must be executed sequentially (same file, ordered by document step number).

### Task 10: Convert code-simplifier dispatch in implement.md Step 5

**Why:** Plan Step 1F.1, Design I1, I4, I9, TD5b; Spec R2.5, R3.1

**R3 pruning change**: Current template has 2 artifacts (spec.md, design.md); new template has 1 (design.md only). Spec.md removal is intentional per TD5b — YAGNI judgment relies on design patterns only.

**Changes to `plugins/iflow/commands/implement.md`:**
1. In the Step 5 code-simplifier Task tool call, replace inline Spec and Design content blocks with I1 Required Artifacts block
2. Apply I4 mapping: code-simplifier gets `["design.md"]` only
3. Add I9 fallback detection after response
4. I8 PRD resolution omitted (PRD not in I4 mapping for this role — resolve_prd() is not called)

**Done when:**
- code-simplifier dispatch has Required Artifacts block with design.md only
- No inline `{content of spec.md}` or `{content of design.md}` in code-simplifier dispatch
- I9 is present
- No PRD reference in the dispatch (intentional R3 pruning)

### Task 11: Convert test-deepener dispatch in implement.md Step 6

**Why:** Plan Step 1F.2, Design I1, I4, I8, I9, TD5b; Spec R2.5, R3.1

Phase A only — Phase B receives Phase A output and file lists only, with no upstream artifact injection. No changes needed for Phase B. Leave Phase B unchanged.

**R3 pruning change**: Current template has section-scoped PRD (Problem Statement + Goals only); new template gives full PRD via lazy-load. This expands context — intentional per TD5b.

**Changes to `plugins/iflow/commands/implement.md`:**
1. In the Step 6 test-deepener Phase A Task tool call, replace inline Spec, Design, Tasks, and PRD content blocks with I1 Required Artifacts block
2. Apply I4 mapping: test-deepener gets `["spec.md", "design.md", "tasks.md", "prd.md"]`
3. Add I8 resolve_prd() for Phase A
4. Add I9 fallback detection for Phase A
5. Phase B dispatch: leave unchanged

**Done when:**
- test-deepener Phase A dispatch has Required Artifacts block with spec.md, design.md, tasks.md, prd.md
- No inline `{content of ...}` patterns in Phase A dispatch
- Phase B dispatch is unchanged
- I8 and I9 are present for Phase A

### Task 12: Convert implementation-reviewer dispatch in implement.md Step 7a

**Why:** Plan Step 1F.3, Design I1, I4, I8, I9; Spec R2.5, R3.1

No R3 pruning — implementation-reviewer retains full chain (same 5 artifacts as current).

Note: implement.md uses `{content of prd.md or brainstorm file}` (not the phase command form `{content of prd.md, or "None"...}`) — both map to the same I8 3-step resolve_prd() logic per plan conventions.

**Changes to `plugins/iflow/commands/implement.md`:**
1. In the Step 7a implementation-reviewer Task tool call, replace all 5 inline artifact content blocks with I1 Required Artifacts block
2. Apply I4 mapping: implementation-reviewer gets `["prd.md", "spec.md", "design.md", "plan.md", "tasks.md"]`
3. Keep Implementation files list inline (agents need to know which files to review)
4. Add I8 resolve_prd()
5. Add I9 fallback detection

**Done when:**
- implementation-reviewer dispatch has Required Artifacts block with all 5 artifacts
- Implementation files list remains inline
- No `{content of ...}` inline injection patterns in implementation-reviewer dispatch
- I8 and I9 are present

### Task 13: Convert code-quality-reviewer dispatch in implement.md Step 7b

**Why:** Plan Step 1F.4, Design I1, I4, I9; Spec R2.5, R3.1

**R3 pruning change**: Current template has 5 artifacts; new template has 2 (design.md, spec.md). PRD, Plan, and Tasks removal is intentional per R3.1.

**Changes to `plugins/iflow/commands/implement.md`:**
1. In the Step 7b code-quality-reviewer Task tool call, replace inline content blocks with I1 Required Artifacts block
2. Apply I4 mapping: code-quality-reviewer gets `["design.md", "spec.md"]`
3. Keep Files changed list inline
4. Add I9 fallback detection
5. I8 PRD resolution omitted (PRD not in I4 mapping for this role — resolve_prd() is not called)

**Done when:**
- code-quality-reviewer dispatch has Required Artifacts block with design.md and spec.md only
- Files changed list remains inline
- No `{content of ...}` inline injection patterns in code-quality-reviewer dispatch
- I9 is present
- No PRD, plan.md, or tasks.md reference (intentional R3 pruning)

### Task 14: Convert security-reviewer dispatch in implement.md Step 7c

**Why:** Plan Step 1F.5, Design I1, I4, I9; Spec R2.5, R3.1

**R3 pruning change**: Current template has 5 artifacts; new template has 2 (design.md, spec.md). PRD, Plan, and Tasks removal is intentional per R3.1.

**Changes to `plugins/iflow/commands/implement.md`:**
1. In the Step 7c security-reviewer Task tool call, replace inline content blocks with I1 Required Artifacts block
2. Apply I4 mapping: security-reviewer gets `["design.md", "spec.md"]`
3. Keep Files changed list inline
4. Add I9 fallback detection
5. I8 PRD resolution omitted (PRD not in I4 mapping for this role — resolve_prd() is not called)

**Done when:**
- security-reviewer dispatch has Required Artifacts block with design.md and spec.md only
- Files changed list remains inline
- No `{content of ...}` inline injection patterns in security-reviewer dispatch
- I9 is present
- No PRD, plan.md, or tasks.md reference (intentional R3 pruning)

### Task 15: Convert implementer fix dispatch in implement.md Step 7e

**Why:** Plan Step 1F.6, Design I1, I4, I8, I9; Spec R2.5, R3.1

No R3 pruning — implementer retains full chain (same 5 artifacts as current).

Note: implement.md uses `{content of prd.md or brainstorm file}` (not the phase command form `{content of prd.md, or "None"...}`) — both map to the same I8 3-step resolve_prd() logic per plan conventions.

**Changes to `plugins/iflow/commands/implement.md`:**
1. In the Step 7e implementer fix Task tool call, replace all 5 inline artifact content blocks with I1 Required Artifacts block
2. Apply I4 mapping: implementer gets `["prd.md", "spec.md", "design.md", "plan.md", "tasks.md"]`
3. Keep Implementation files list and Issues to fix list inline
4. Add I8 resolve_prd()
5. Add I9 fallback detection

**Done when:**
- implementer fix dispatch has Required Artifacts block with all 5 artifacts
- Implementation files and Issues to fix lists remain inline
- No `{content of ...}` inline injection patterns in implementer fix dispatch
- I8 and I9 are present

---

## Phase D: Verification

All Phase D tasks depend on completion of all tasks in Phases A, B, and C.

### Task 16: Run grep audit for remaining inline injections

**Why:** Plan Step 1G.1, Spec Test Strategy

Run two grep patterns to verify no inline injection patterns remain in the 6 changed files.

**Steps:**
1. Primary grep — scoped to the 6 changed files only (eliminates excluded-file noise):
   ```
   grep -E "\{.*content.*\.md\}" plugins/iflow/commands/{specify,design,create-plan,create-tasks,implement}.md plugins/iflow/skills/implementing/SKILL.md
   ```
2. Reversed-form grep (catches SKILL.md's `{spec.md content}` pattern):
   ```
   grep -E "\{[^}]*\.md[^}]*content\}" plugins/iflow/commands/{specify,design,create-plan,create-tasks,implement}.md plugins/iflow/skills/implementing/SKILL.md
   ```
3. Verify zero matches from both greps. Any match = incomplete conversion in that file
4. Expected retained patterns in implementing/SKILL.md that should NOT match: `{extractSection(design.md, ...)}` — these don't contain "content" so they won't trigger the grep
5. Secondary grep for section-scoped PRD patterns (primarily targets implement.md's `{Problem Statement + Goals from prd.md}` variant):
   ```
   grep -E "Problem Statement.*(prd|PRD)|Goals.*(prd|PRD)|prd.*Problem Statement" plugins/iflow/commands/{specify,design,create-plan,create-tasks,implement}.md plugins/iflow/skills/implementing/SKILL.md
   ```
   Note: SKILL.md's `prd.md: extract ## Problem Statement...` bullet (line ~80) is validated by Task 1's done-when criteria. This secondary grep primarily catches implement.md's variant. If the SKILL.md bullet survived, it would match the `prd.*Problem Statement` alternative in the pattern.
6. Verify zero matches. Any match = PRD section-scoping not fully removed

**Done when:**
- Both primary greps return zero matches across the 6 changed files
- Secondary grep returns zero matches across the 6 changed files

### Task 17: Verify agent frontmatter has Read tool

**Why:** Plan Step 1G.2, Spec Test Strategy

Verify all 11 agents that will receive lazy-load prompts have `Read` in their frontmatter tools list.

**Steps:**
1. For each of the 11 target agents, check for Read in frontmatter (all agents use inline bracket format `tools: [Read, ...]` — confirmed in design.md Prior Art):
   ```
   for agent in implementation-reviewer code-quality-reviewer security-reviewer code-simplifier test-deepener implementer spec-reviewer design-reviewer plan-reviewer task-reviewer phase-reviewer; do
     grep -qE "(tools:.*Read|^  - Read)" plugins/iflow/agents/$agent.md && echo "OK: $agent" || echo "MISSING Read: $agent"
   done
   ```
2. If any agent reports "MISSING Read", add Read to that agent's frontmatter tools list following existing format: `tools: [Read, Glob, Grep]` (add Read to existing list, do not replace other tools)

**Done when:**
- All 11 agents report "OK" (Read found in frontmatter tools line)
- Any previously missing agents have been fixed

### Task 18: Manual end-to-end validation

**Why:** Plan Step 1G.3, Spec Test Strategy

Run one phase command on a test feature to validate the full lazy-load pipeline works correctly.

**Steps:**
1. Find or create a test feature with prd.md: run `ls docs/features/` and pick any feature that has a prd.md file, or create a minimal test feature with a stub prd.md and spec.md. Note: feature 030 has no prd.md (created without brainstorm) — use it for the optional No-PRD sentinel test in step 6, not for the primary happy-path test
2. Run `/iflow:specify` on the test feature (simplest phase command, exercises Tasks 2-3 changes)
3. In Claude Code UI, expand the Task tool call in the agent transcript sidebar and verify at least one Read tool call targets spec.md or prd.md path within the feature directory
4. Check the reviewer's response contains "Files read:" confirmation line
5. Check .review-history.md has no LAZY-LOAD-WARNING entries for this test run
6. Optionally repeat on a feature without prd.md (e.g., one created via `/iflow:create-feature`) to exercise the I8 "No PRD" sentinel path
7. This is a manual post-implementation sanity check

**Done when:**
- Agent transcript shows Read tool calls for referenced artifact files
- Review result is non-blank, returns valid JSON, and is consistent with expected outcome for the test feature (approval or issue detection — not blank/error)
- No LAZY-LOAD-WARNING entries in .review-history.md for the test run

---

## Dependency Graph

```
Task 1 (SKILL.md hybrid) ← no deps, start first
  ↓ validates pattern

Tasks 2→3 (specify.md: sequential, same file)    ─┐
Tasks 4→5 (design.md: sequential, same file)      │ parallel across files
Tasks 6→7 (create-plan.md: sequential, same file)  │
Tasks 8→9 (create-tasks.md: sequential, same file) ─┘

Tasks 10→11→12→13→14→15 (implement.md: sequential, same file)

Tasks 16, 17, 18 (verification) ← depend on ALL tasks 1-15
```
