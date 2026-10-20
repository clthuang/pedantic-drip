# Implementation Plan: Evidence-Grounded Workflow Phases

## Overview

This plan implements 12 components across 4 workflow phases (spec, design, plan, tasks) to add reasoning, evidence, and auto-commit capabilities. Implementation follows the phase sequence to ensure each phase's changes can be validated by running the workflow.

**Testing Approach:** This plugin modifies markdown templates and workflow orchestration - not code with unit tests. Verification is done through manual invocation and workflow execution. Each item's verification step serves as the acceptance test.

## Implementation Phases

### Phase 1: Spec Phase Enhancements

#### 1.1 Specifying Skill Enhancement
- **Why this item:** Component 1 defines the Feasibility Assessment section template that must exist before reviewers can verify it
- **Why this order:** Skills produce artifacts that reviewers validate; skill must be enhanced first
- **Deliverable:** Updated `plugins/iflow-dev/skills/specifying/SKILL.md` with Feasibility Assessment section template and 2 new self-check items
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/skills/specifying/SKILL.md`
- **Verification:** Run specifying skill manually; verify output includes Feasibility Assessment section with all required fields per Interface 1 in design

#### 1.2 Spec-Skeptic Agent Enhancement
- **Why this item:** Component 2 enables independent verification of feasibility claims using research tools
- **Why this order:** Agent must have tools AND explicit verification instructions before command expects verification results
- **Deliverable:** Updated `plugins/iflow-dev/agents/spec-skeptic.md` with:
  - Tools: `[Read, Glob, Grep, WebSearch, mcp__context7__resolve-library-id, mcp__context7__query-docs]`
  - "Feasibility Verification" category with checklist
  - Explicit instruction: "MUST use Context7 to verify at least one library/API claim OR WebSearch for external claims. Include verification result in output."
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/agents/spec-skeptic.md`
- **Verification:** Invoke spec-skeptic via Task tool with a spec containing a library claim; confirm output includes "Verified: {claim} via {source}" or "Unable to verify independently"

#### 1.3 Specify Command Auto-Commit and Push
- **Why this item:** Component 12 adds auto-commit AND auto-push after phase-reviewer approval for specify command
- **Why this order:** Command enhancement depends on skill and agent being ready to produce valid artifacts
- **Deliverable:** Updated `plugins/iflow-dev/commands/specify.md` with step "4b. Auto-Commit Phase Artifact" inserted AFTER phase-reviewer approval (Step 4) and BEFORE state update (Step 5), containing:
  - `git add docs/features/{id}-{slug}/spec.md docs/features/{id}-{slug}/.meta.json docs/features/{id}-{slug}/.review-history.md`
  - `git commit -m "phase(specify): {slug} - approved"`
  - `git push`
  - Error handling per Interface 6: commit failure blocks, push failure warns but continues
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/commands/specify.md`
- **Verification:** Run `/iflow-dev:specify` on test feature; verify git log shows commit and remote has push after approval

---

### Phase 2: Design Phase Enhancements

#### 2.1 Designing Skill Enhancement
- **Why this item:** Component 3 adds Prior Art Research section and evidence-grounded Technical Decisions format
- **Why this order:** Skill template must exist before design command can use it for Stage 0
- **Deliverable:** Updated `plugins/iflow-dev/skills/designing/SKILL.md` with Prior Art Research section (per Interface 2) and enhanced Technical Decisions format (per Interface 3)
- **Complexity:** Medium (template changes affect output structure)
- **Files:** `plugins/iflow-dev/skills/designing/SKILL.md`
- **Verification:** Run designing skill manually; verify output includes Prior Art section with Research Conducted table and enhanced Technical Decisions with all required fields

#### 2.2 Design-Reviewer Agent Enhancement
- **Why this item:** Component 4 enables independent verification of design claims
- **Why this order:** Agent must have verification capabilities before design command expects verification results
- **Deliverable:** Updated `plugins/iflow-dev/agents/design-reviewer.md` with:
  - Tools: `[Read, Glob, Grep, WebSearch, mcp__context7__resolve-library-id, mcp__context7__query-docs]`
  - "Prior Art Verification" and "Evidence Grounding" categories
  - Explicit instruction: "MUST independently verify at least 2 claims using Context7/WebSearch/Grep. Include verification evidence in review output."
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/agents/design-reviewer.md`
- **Verification:** Invoke design-reviewer via Task tool with design containing library claims; confirm output includes 2+ verification results

#### 2.3 Design Command Enhancement
- **Why this item:** Component 5 adds Stage 0 Research before architecture and auto-commit after approval
- **Why this order:** Command orchestrates skill and agent; must be updated last in phase
- **Deliverable:** Updated `plugins/iflow-dev/commands/design.md` with:
  - Stage 0 (Research) inserted BEFORE Stage 1 (Architecture)
  - New stage tracking: `stages.research: { started, completed }` in .meta.json
  - Failure handling: if codebase-explorer/internet-researcher fail, note "unavailable" in Prior Art section and proceed
  - User skip option: "Skip (domain expert)" bypasses Stage 0 entirely
  - Partial recovery: if `stages.research.started` exists but not `completed`, offer resume/restart
  - Auto-commit step "4c. Auto-Commit Phase Artifact" after handoff review approval
- **Complexity:** Medium (new stage with agent dispatch and state tracking)
- **Files:** `plugins/iflow-dev/commands/design.md`
- **Verification:** Run `/iflow-dev:design` on test feature; verify .meta.json shows `stages.research` timestamps and git log shows commit after approval

---

### Phase 3: Plan Phase Enhancements

#### 3.1 Planning Skill Enhancement
- **Why this item:** Component 6 adds reasoning fields to plan items
- **Why this order:** Skill template must produce artifacts with Why fields before reviewers can validate them
- **Deliverable:** Updated `plugins/iflow-dev/skills/planning/SKILL.md` with:
  - Plan item format per Interface 4: "Why this item", "Why this order", "Deliverable" (NOT LOC), "Verification"
  - Estimation Approach section with guidance: "Use deliverables, not LOC or time"
  - Anti-pattern examples: "BAD: ~50 lines of code, BAD: ~2 hours"
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/skills/planning/SKILL.md`
- **Verification:** Run planning skill manually; verify output includes all reasoning fields and no LOC estimates

#### 3.2 Plan-Reviewer Agent Enhancement
- **Why this item:** Component 7 adds reasoning verification and LOC estimate rejection
- **Why this order:** Skill produces deliverable-based estimates; agent REJECTS if LOC estimates found
- **Deliverable:** Updated `plugins/iflow-dev/agents/plan-reviewer.md` with:
  - "Reasoning Verification" category checking Why fields exist and reference design/dependencies
  - Challenge pattern: if LOC found → "Replace with deliverable - what artifact proves completion?"
  - Challenge pattern: if Why missing → "Why needed? Which design requirement?"
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/agents/plan-reviewer.md`
- **Verification:** Invoke plan-reviewer on plan with LOC estimate; verify it flags as issue with "Replace with deliverable" suggestion

#### 3.3 Create-Plan Command Auto-Commit and Push
- **Why this item:** Component 8 adds auto-commit AND auto-push after approval
- **Why this order:** Command enhancement comes after skill/agent to ensure valid artifacts
- **Deliverable:** Updated `plugins/iflow-dev/commands/create-plan.md` with step "5b. Auto-Commit Phase Artifact" after chain-reviewer approval, containing:
  - `git add docs/features/{id}-{slug}/plan.md docs/features/{id}-{slug}/.meta.json docs/features/{id}-{slug}/.review-history.md`
  - `git commit -m "phase(plan): {slug} - approved"`
  - `git push`
  - Error handling per Interface 6
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/commands/create-plan.md`
- **Verification:** Run `/iflow-dev:create-plan` on test feature; verify git log and remote after approval

---

### Phase 4: Task Phase Enhancements

#### 4.1 Breaking-Down-Tasks Skill Enhancement
- **Why this item:** Component 9 adds traceability "Why" field to task template
- **Why this order:** Skill template must include Why field before reviewers can validate traceability
- **Deliverable:** Updated `plugins/iflow-dev/skills/breaking-down-tasks/SKILL.md` with "Why" field per Interface 5: "Implements Plan {X.Y} / Design Component {Name}"
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/skills/breaking-down-tasks/SKILL.md`
- **Verification:** Run breaking-down-tasks skill manually; verify each task includes Why field with explicit plan/design reference

#### 4.2 Task-Reviewer Agent Enhancement
- **Why this item:** Component 10 adds reasoning traceability verification
- **Why this order:** Agent must check Why fields before command can rely on verification
- **Deliverable:** Updated `plugins/iflow-dev/agents/task-reviewer.md` with:
  - "Reasoning Traceability" category
  - Challenge pattern: if Why missing → "What plan item does this implement?"
  - Challenge pattern: if can't trace → "Doesn't map to plan - scope creep?"
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/agents/task-reviewer.md`
- **Verification:** Invoke task-reviewer on tasks with missing Why fields; verify it flags as potential scope creep

#### 4.3 Create-Tasks Command Auto-Commit and Push
- **Why this item:** Component 11 adds auto-commit AND auto-push after approval
- **Why this order:** Command enhancement comes after skill/agent updates
- **Deliverable:** Updated `plugins/iflow-dev/commands/create-tasks.md` with step "6b. Auto-Commit Phase Artifact" after chain-reviewer approval, containing:
  - `git add docs/features/{id}-{slug}/tasks.md docs/features/{id}-{slug}/.meta.json docs/features/{id}-{slug}/.review-history.md`
  - `git commit -m "phase(tasks): {slug} - approved"`
  - `git push`
  - Error handling per Interface 6
- **Complexity:** Simple
- **Files:** `plugins/iflow-dev/commands/create-tasks.md`
- **Verification:** Run `/iflow-dev:create-tasks` on test feature; verify git log and remote after approval

---

### Phase 5: Integration Validation

#### 5.1 Run Validation Script
- **Why this item:** Ensures all plugin components remain valid after changes
- **Why this order:** Must validate after all changes are complete
- **Deliverable:** Clean `./validate.sh` output with no errors
- **Complexity:** Simple
- **Files:** (none modified, validation only)
- **Verification:** `./validate.sh` exits with status 0

#### 5.2 End-to-End Test
- **Why this item:** Validates complete workflow with all enhancements
- **Why this order:** Final validation after all components enhanced
- **Deliverable:** Test feature `999-test-evidence-grounded` created and progressed through spec → design → plan → tasks
- **Complexity:** Medium (requires running full workflow)
- **Files:** Test feature created in `docs/dev_artifacts/workitems/999-test-evidence-grounded/`, deleted after validation
- **Verification:**
  - spec.md contains Feasibility Assessment section
  - design.md contains Prior Art Research section
  - plan.md contains Why fields for each item (no LOC)
  - tasks.md contains Why fields tracing to plan/design
  - Git log shows 4 phase commits (specify, design, plan, tasks)
  - After validation: `rm -rf docs/features/999-test-evidence-grounded`

---

## Dependency Graph

```
Phase 1: Spec
  1.1 Specifying Skill ─┬─▶ 1.3 Specify Command
  1.2 Spec-Skeptic Agent ─┘

Phase 2: Design
  2.1 Designing Skill ─┬─▶ 2.3 Design Command
  2.2 Design-Reviewer Agent ─┘

Phase 3: Plan
  3.1 Planning Skill ─┬─▶ 3.3 Create-Plan Command
  3.2 Plan-Reviewer Agent ─┘

Phase 4: Tasks
  4.1 Breaking-Down-Tasks Skill ─┬─▶ 4.3 Create-Tasks Command
  4.2 Task-Reviewer Agent ─┘

Phase 5: Validation
  All Phase 1-4 items ─▶ 5.1 Validation ─▶ 5.2 E2E Test
```

## Files Summary

| File | Items | Changes |
|------|-------|---------|
| `plugins/iflow-dev/skills/specifying/SKILL.md` | 1.1 | +Feasibility Assessment section |
| `plugins/iflow-dev/agents/spec-skeptic.md` | 1.2 | +Tools, +Verification category, +MUST verify instruction |
| `plugins/iflow-dev/commands/specify.md` | 1.3 | +Auto-commit/push step 4b |
| `plugins/iflow-dev/skills/designing/SKILL.md` | 2.1 | +Prior Art, +Enhanced Decisions |
| `plugins/iflow-dev/agents/design-reviewer.md` | 2.2 | +Tools, +Verification categories, +MUST verify instruction |
| `plugins/iflow-dev/commands/design.md` | 2.3 | +Stage 0 with state tracking, +Auto-commit/push |
| `plugins/iflow-dev/skills/planning/SKILL.md` | 3.1 | +Why fields, +Estimation guidance, +Anti-patterns |
| `plugins/iflow-dev/agents/plan-reviewer.md` | 3.2 | +Reasoning verification, +LOC rejection |
| `plugins/iflow-dev/commands/create-plan.md` | 3.3 | +Auto-commit/push step 5b |
| `plugins/iflow-dev/skills/breaking-down-tasks/SKILL.md` | 4.1 | +Why traceability field |
| `plugins/iflow-dev/agents/task-reviewer.md` | 4.2 | +Traceability verification |
| `plugins/iflow-dev/commands/create-tasks.md` | 4.3 | +Auto-commit/push step 6b |

## Risk Mitigations Applied

- **Parallel execution within phases:** Items 1.1/1.2, 2.1/2.2, 3.1/3.2, 4.1/4.2 can be done in parallel
- **Validation checkpoints:** Each phase has verification criteria before moving to next
- **Incremental testing:** Skills tested before agents before commands
- **Test feature cleanup:** E2E test uses `999-` prefix and is deleted after validation

## Blockers Addressed

1. **TDD Order:** This plugin modifies markdown templates, not code. Verification steps serve as acceptance tests.
2. **Auto-commit integration:** Each command specifies exact step number (e.g., "4b") and placement (after approval, before state update).
3. **Agent verification instructions:** Each agent deliverable now includes explicit "MUST verify" instruction text.
4. **Stage 0 state tracking:** Design command deliverable specifies `stages.research` tracking and partial recovery handling.
