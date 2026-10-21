# Tasks: Evidence-Grounded Workflow Phases

## Phase 1: Spec Phase Enhancements

### Plan Item 1.1: Specifying Skill Enhancement

#### Task 1.1.1: Add Feasibility Assessment Section Template
- **Why:** Implements Plan 1.1 / Design Component 1 - defines the output template for feasibility
- **Depends on:** None
- **Blocks:** 1.1.2
- **Files:** `plugins/iflow-dev/skills/specifying/SKILL.md`
- **Do:**
  1. Read current SKILL.md to find Output Format section
  2. Add "## Feasibility Assessment" section after Acceptance Criteria
  3. Include: Assessment Approach (First Principles, Codebase Evidence, External Evidence)
  4. Include: Feasibility Scale table (Confirmed/Likely/Uncertain/Unlikely/Impossible)
  5. Include: Assessment template (Overall, Reasoning, Key Assumptions, Open Risks)
- **Test:** Read the updated SKILL.md, confirm Feasibility Assessment section present
- **Done when:** Feasibility Assessment section matches Interface 1 from design.md
- **Estimated:** 10 min

#### Task 1.1.2: Add Feasibility Self-Check Items
- **Why:** Implements Plan 1.1 - ensures skill author validates feasibility section
- **Depends on:** 1.1.1
- **Blocks:** 1.3.1
- **Files:** `plugins/iflow-dev/skills/specifying/SKILL.md`
- **Do:**
  1. Find Self-Check section in SKILL.md
  2. Add: "- [ ] Feasibility assessment uses evidence, not opinion?"
  3. Add: "- [ ] Assumptions explicitly listed?"
- **Test:** Read Self-Check section, confirm 2 new items present
- **Done when:** Self-Check has 2 new feasibility-related items
- **Estimated:** 5 min

---

### Plan Item 1.2: Spec-Skeptic Agent Enhancement

#### Task 1.2.1: Add Research Tools to Spec-Skeptic Agent
- **Why:** Implements Plan 1.2 / Design Component 2 - enables verification capability
- **Depends on:** None (parallel with 1.1.1)
- **Blocks:** 1.2.2
- **Files:** `plugins/iflow-dev/agents/spec-skeptic.md`
- **Do:**
  1. Read current spec-skeptic.md frontmatter
  2. Update tools array to: `[Read, Glob, Grep, WebSearch, mcp__context7__resolve-library-id, mcp__context7__query-docs]`
- **Test:** Read frontmatter, confirm tools array includes WebSearch and Context7
- **Done when:** Tools array has 6 items including WebSearch and Context7
- **Estimated:** 5 min

#### Task 1.2.2: Add Feasibility Verification Category
- **Why:** Implements Plan 1.2 - defines what to verify in feasibility section
- **Depends on:** 1.2.1
- **Blocks:** 1.2.3
- **Files:** `plugins/iflow-dev/agents/spec-skeptic.md`
- **Do:**
  1. Find review categories section
  2. Add "### Feasibility Verification" category with checklist:
     - Feasibility assessment exists
     - Uses evidence (code refs, docs, first principles)
     - No unverified "Likely" on critical paths
     - Assumptions are testable
- **Test:** Read agent file, confirm Feasibility Verification category present
- **Done when:** Category has 4 checklist items
- **Estimated:** 5 min

#### Task 1.2.3: Add Independent Verification Instruction
- **Why:** Implements Plan 1.2 - mandates actual tool usage, not just access
- **Depends on:** 1.2.2
- **Blocks:** 1.3.1
- **Files:** `plugins/iflow-dev/agents/spec-skeptic.md`
- **Do:**
  1. Add "**Independent Verification:**" section after Feasibility Verification
  2. Add explicit instruction: "MUST use Context7 to verify at least one library/API claim OR WebSearch for external claims."
  3. Add output requirement: "Include verification result: 'Verified: {claim} via {source}' or 'Unable to verify independently - flagged for human review'"
- **Test:** Read agent file, confirm MUST instruction present
- **Done when:** Agent has explicit verification mandate with output format
- **Estimated:** 5 min

---

### Plan Item 1.3: Specify Command Auto-Commit and Push

#### Task 1.3.1: Add Auto-Commit Step to Specify Command
- **Why:** Implements Plan 1.3 / Design Component 12 - auto-saves approved spec
- **Depends on:** 1.1.2, 1.2.3
- **Blocks:** 2.1.1
- **Files:** `plugins/iflow-dev/commands/specify.md`
- **Do:**
  1. Read current specify.md to find step structure
  2. Insert "### 4b. Auto-Commit Phase Artifact" after Step 4 (phase-reviewer) and before Step 5 (state update)
  3. Add git commands:
     ```
     git add docs/features/{id}-{slug}/spec.md docs/features/{id}-{slug}/.meta.json docs/features/{id}-{slug}/.review-history.md
     git commit -m "phase(specify): {slug} - approved"
     git push
     ```
  4. Add error handling: commit failure blocks, push failure warns but continues
- **Test:** Read specify.md, confirm step 4b exists with git commands
- **Done when:** Auto-commit step present with error handling per Interface 6
- **Estimated:** 10 min

---

## Phase 2: Design Phase Enhancements

### Plan Item 2.1: Designing Skill Enhancement

#### Task 2.1.1: Add Prior Art Research Section Template
- **Why:** Implements Plan 2.1 / Design Component 3 - defines research output format
- **Depends on:** 1.3.1
- **Blocks:** 2.1.2
- **Files:** `plugins/iflow-dev/skills/designing/SKILL.md`
- **Do:**
  1. Read current SKILL.md Output Format section
  2. Add "## Prior Art Research" section at TOP of output (before Architecture)
  3. Include: Research Conducted table (Question, Source, Finding)
  4. Include: Existing Solutions Evaluated table
  5. Include: Novel Work Justified section
- **Test:** Read SKILL.md, confirm Prior Art section at top of output
- **Done when:** Prior Art section matches Interface 2 from design.md
- **Estimated:** 10 min

#### Task 2.1.2: Enhance Technical Decisions Format
- **Why:** Implements Plan 2.1 - adds evidence grounding to decisions
- **Depends on:** 2.1.1
- **Blocks:** 2.1.3
- **Files:** `plugins/iflow-dev/skills/designing/SKILL.md`
- **Do:**
  1. Find Technical Decisions section in Output Format
  2. Update decision template to include:
     - Choice
     - Alternatives Considered (with rejection reasons)
     - Trade-offs (Pros/Cons)
     - Rationale
     - Engineering Principle (KISS/YAGNI/DRY/etc.)
     - Evidence (Codebase: file:line | Documentation: URL | First Principles)
- **Test:** Read Technical Decisions format, confirm all 6 fields present
- **Done when:** Decision format matches Interface 3 from design.md
- **Estimated:** 10 min

#### Task 2.1.3: Add Design Self-Check Items
- **Why:** Implements Plan 2.1 - ensures skill author validates evidence
- **Depends on:** 2.1.2
- **Blocks:** 2.3.1
- **Files:** `plugins/iflow-dev/skills/designing/SKILL.md`
- **Do:**
  1. Find Self-Check section
  2. Add: "- [ ] Prior Art Research section completed?"
  3. Add: "- [ ] Each Technical Decision has evidence citation?"
- **Test:** Read Self-Check section, confirm 2 new items
- **Done when:** Self-Check has design-related items
- **Estimated:** 5 min

---

### Plan Item 2.2: Design-Reviewer Agent Enhancement

#### Task 2.2.1: Add Research Tools to Design-Reviewer Agent
- **Why:** Implements Plan 2.2 / Design Component 4 - enables verification
- **Depends on:** 1.3.1 (parallel with 2.1.1)
- **Blocks:** 2.2.2
- **Files:** `plugins/iflow-dev/agents/design-reviewer.md`
- **Do:**
  1. Read current design-reviewer.md frontmatter
  2. Update tools array to: `[Read, Glob, Grep, WebSearch, mcp__context7__resolve-library-id, mcp__context7__query-docs]`
- **Test:** Read frontmatter, confirm tools array includes WebSearch and Context7
- **Done when:** Tools array has 6 items
- **Estimated:** 5 min

#### Task 2.2.2: Add Prior Art and Evidence Categories
- **Why:** Implements Plan 2.2 - defines what to verify in design
- **Depends on:** 2.2.1
- **Blocks:** 2.2.3
- **Files:** `plugins/iflow-dev/agents/design-reviewer.md`
- **Do:**
  1. Find review categories section
  2. Add "### Prior Art Verification" category:
     - Research section exists
     - Library claims verified
     - Codebase claims verified
     - "Novel work" is truly novel
  3. Add "### Evidence Grounding" category:
     - Every decision has evidence
     - Evidence sources verifiable
     - Trade-offs explicit
     - Engineering principles named
- **Test:** Read agent file, confirm both categories present
- **Done when:** Two new categories with checklist items
- **Estimated:** 10 min

#### Task 2.2.3: Add Independent Verification Instruction
- **Why:** Implements Plan 2.2 - mandates verification of 2+ claims
- **Depends on:** 2.2.2
- **Blocks:** 2.3.1
- **Files:** `plugins/iflow-dev/agents/design-reviewer.md`
- **Do:**
  1. Add "**Independent Verification:**" section
  2. Add: "MUST independently verify at least 2 claims using Context7/WebSearch/Grep."
  3. Add: "Include verification evidence in review output."
- **Test:** Read agent file, confirm MUST instruction with "2 claims"
- **Done when:** Agent mandates 2+ claim verification
- **Estimated:** 5 min

---

### Plan Item 2.3: Design Command Enhancement

#### Task 2.3.1: Add Stage 0 Research to Design Command
- **Why:** Implements Plan 2.3 / Design Component 5 - adds research before architecture
- **Depends on:** 2.1.3, 2.2.3
- **Blocks:** 2.3.2
- **Files:** `plugins/iflow-dev/commands/design.md`
- **Do:**
  1. Read current design.md workflow stages
  2. Insert "#### Stage 0: Research" BEFORE Stage 1 (Architecture)
  3. Add: Mark stage started in .meta.json as `stages.research`
  4. Add: Dispatch codebase-explorer and internet-researcher agents in parallel
  5. Add: Present findings via AskUserQuestion with options: "Review findings | Proceed | Skip (domain expert)"
  6. Add: Record results in design.md Prior Art section
  7. Add: Mark stage completed
- **Test:** Read design.md, confirm Stage 0 before Stage 1
- **Done when:** Stage 0 with agent dispatch and user decision present
- **Estimated:** 15 min

#### Task 2.3.2: Add Stage 0 Failure Handling
- **Why:** Implements Plan 2.3 - graceful degradation if research agents fail
- **Depends on:** 2.3.1
- **Blocks:** 2.3.3
- **Files:** `plugins/iflow-dev/commands/design.md`
- **Do:**
  1. Add failure handling to Stage 0:
     - If codebase-explorer fails: Note "codebase search unavailable" in Prior Art
     - If internet-researcher fails: Note "no external solutions found" in Prior Art
     - Both fail: Proceed with empty Prior Art section
  2. Add partial recovery: if `stages.research.started` but not `completed`, offer resume/restart
- **Test:** Read Stage 0, confirm failure handling and recovery present
- **Done when:** Stage 0 handles all failure cases
- **Estimated:** 10 min

#### Task 2.3.3: Add Auto-Commit Step to Design Command
- **Why:** Implements Plan 2.3 - auto-saves approved design
- **Depends on:** 2.3.2
- **Blocks:** 3.1.1
- **Files:** `plugins/iflow-dev/commands/design.md`
- **Do:**
  1. Find handoff review stage (Stage 4)
  2. Insert "### 4c. Auto-Commit Phase Artifact" after handoff approval
  3. Add git commands per Interface 6 (add, commit, push with error handling)
- **Test:** Read design.md, confirm step 4c with git commands
- **Done when:** Auto-commit step present after handoff review
- **Estimated:** 10 min

---

## Phase 3: Plan Phase Enhancements

### Plan Item 3.1: Planning Skill Enhancement

#### Task 3.1.1: Update Plan Item Format with Why Fields
- **Why:** Implements Plan 3.1 / Design Component 6 - adds reasoning to plan items
- **Depends on:** 2.3.3
- **Blocks:** 3.1.2
- **Files:** `plugins/iflow-dev/skills/planning/SKILL.md`
- **Do:**
  1. Read current plan item format in Output section
  2. Update format to include:
     - Why this item (rationale referencing design/requirement)
     - Why this order (rationale referencing dependencies)
     - Deliverable (concrete output, NOT LOC)
     - Complexity (Simple/Medium/Complex)
     - Files
     - Verification (how to confirm complete)
- **Test:** Read plan item format, confirm all 6 fields present
- **Done when:** Plan item format matches Interface 4 from design.md
- **Estimated:** 10 min

#### Task 3.1.2: Add Estimation Approach Section
- **Why:** Implements Plan 3.1 - prohibits LOC estimates
- **Depends on:** 3.1.1
- **Blocks:** 3.3.1
- **Files:** `plugins/iflow-dev/skills/planning/SKILL.md`
- **Do:**
  1. Add "## Estimation Approach" section
  2. Add guidance: "Use deliverables, not LOC or time"
  3. Add anti-patterns: "BAD: ~50 lines of code", "BAD: ~2 hours"
  4. Add: "Complexity = decisions, not size"
- **Test:** Read Estimation Approach section, confirm anti-patterns present
- **Done when:** Section explicitly prohibits LOC with examples
- **Estimated:** 5 min

---

### Plan Item 3.2: Plan-Reviewer Agent Enhancement

#### Task 3.2.1: Add Reasoning Verification Category
- **Why:** Implements Plan 3.2 / Design Component 7 - validates Why fields
- **Depends on:** 2.3.3 (parallel with 3.1.1)
- **Blocks:** 3.2.2
- **Files:** `plugins/iflow-dev/agents/plan-reviewer.md`
- **Do:**
  1. Find review categories section
  2. Add "### Reasoning Verification" category:
     - Every item has "Why this item"
     - Every item has "Why this order"
     - Rationales reference design/dependencies
     - No LOC estimates (deliverables only)
     - Deliverables concrete and verifiable
- **Test:** Read agent file, confirm Reasoning Verification category
- **Done when:** Category has 5 checklist items
- **Estimated:** 5 min

#### Task 3.2.2: Add Challenge Patterns for LOC and Missing Why
- **Why:** Implements Plan 3.2 - teaches reviewer how to flag issues
- **Depends on:** 3.2.1
- **Blocks:** 3.3.1
- **Files:** `plugins/iflow-dev/agents/plan-reviewer.md`
- **Do:**
  1. Add "**Challenges:**" section after Reasoning Verification
  2. Add: if LOC found → "Replace with deliverable - what artifact proves completion?"
  3. Add: if Why missing → "Why needed? Which design requirement?"
  4. Add: if vague deliverable → "What artifact proves completion?"
- **Test:** Read agent file, confirm 3 challenge patterns
- **Done when:** Challenge patterns cover LOC, missing Why, vague deliverable
- **Estimated:** 5 min

---

### Plan Item 3.3: Create-Plan Command Auto-Commit and Push

#### Task 3.3.1: Add Auto-Commit Step to Create-Plan Command
- **Why:** Implements Plan 3.3 / Design Component 8 - auto-saves approved plan
- **Depends on:** 3.1.2, 3.2.2
- **Blocks:** 4.1.1
- **Files:** `plugins/iflow-dev/commands/create-plan.md`
- **Do:**
  1. Read current create-plan.md step structure
  2. Insert "### 5b. Auto-Commit Phase Artifact" after chain-reviewer approval
  3. Add git commands per Interface 6
- **Test:** Read create-plan.md, confirm step 5b with git commands
- **Done when:** Auto-commit step present with error handling
- **Estimated:** 10 min

---

## Phase 4: Task Phase Enhancements

### Plan Item 4.1: Breaking-Down-Tasks Skill Enhancement

#### Task 4.1.1: Add Why Field to Task Template
- **Why:** Implements Plan 4.1 / Design Component 9 - adds traceability
- **Depends on:** 3.3.1
- **Blocks:** 4.3.1
- **Files:** `plugins/iflow-dev/skills/breaking-down-tasks/SKILL.md`
- **Do:**
  1. Read current task template format
  2. Add "- **Why:** Implements Plan {X.Y} / Design Component {Name}" field
  3. Position after task title, before Depends on
- **Test:** Read task template, confirm Why field present
- **Done when:** Why field matches Interface 5 from design.md
- **Estimated:** 5 min

---

### Plan Item 4.2: Task-Reviewer Agent Enhancement

#### Task 4.2.1: Add Reasoning Traceability Category
- **Why:** Implements Plan 4.2 / Design Component 10 - validates Why fields
- **Depends on:** 3.3.1 (parallel with 4.1.1)
- **Blocks:** 4.2.2
- **Files:** `plugins/iflow-dev/agents/task-reviewer.md`
- **Do:**
  1. Find review categories section
  2. Add "### Reasoning Traceability" category:
     - Every task has "Why" field
     - "Why" traces to plan item or design component
     - No orphan tasks (without backing)
- **Test:** Read agent file, confirm Reasoning Traceability category
- **Done when:** Category has 3 checklist items
- **Estimated:** 5 min

#### Task 4.2.2: Add Challenge Patterns for Missing Why
- **Why:** Implements Plan 4.2 - teaches reviewer to flag scope creep
- **Depends on:** 4.2.1
- **Blocks:** 4.3.1
- **Files:** `plugins/iflow-dev/agents/task-reviewer.md`
- **Do:**
  1. Add "**Challenges:**" section
  2. Add: if Why missing → "What plan item does this implement?"
  3. Add: if can't trace → "Doesn't map to plan - scope creep?"
- **Test:** Read agent file, confirm 2 challenge patterns
- **Done when:** Challenge patterns cover missing Why and untraceable tasks
- **Estimated:** 5 min

---

### Plan Item 4.3: Create-Tasks Command Auto-Commit and Push

#### Task 4.3.1: Add Auto-Commit Step to Create-Tasks Command
- **Why:** Implements Plan 4.3 / Design Component 11 - auto-saves approved tasks
- **Depends on:** 4.1.1, 4.2.2
- **Blocks:** 5.1.1
- **Files:** `plugins/iflow-dev/commands/create-tasks.md`
- **Do:**
  1. Read current create-tasks.md step structure
  2. Insert "### 6b. Auto-Commit Phase Artifact" after chain-reviewer approval
  3. Add git commands per Interface 6
- **Test:** Read create-tasks.md, confirm step 6b with git commands
- **Done when:** Auto-commit step present with error handling
- **Estimated:** 10 min

---

## Phase 5: Integration Validation

### Plan Item 5.1: Run Validation Script

#### Task 5.1.1: Run validate.sh
- **Why:** Implements Plan 5.1 - ensures plugin integrity after changes
- **Depends on:** 4.3.1
- **Blocks:** 5.2.1
- **Files:** None (validation only)
- **Do:**
  1. Run `./validate.sh`
  2. If errors: fix issues in affected files
  3. Re-run until clean
- **Test:** `./validate.sh` exits with status 0
- **Done when:** No validation errors
- **Estimated:** 5 min

---

### Plan Item 5.2: End-to-End Test

#### Task 5.2.1: Create Test Feature
- **Why:** Implements Plan 5.2 - validates complete workflow
- **Depends on:** 5.1.1
- **Blocks:** 5.2.2
- **Files:** `docs/dev_artifacts/workitems/999-test-evidence-grounded/`
- **Do:**
  1. Run `/iflow-dev:create-feature test evidence grounded workflow`
  2. Use ID 999 to distinguish from real features
- **Test:** Feature folder created with .meta.json
- **Done when:** `docs/dev_artifacts/workitems/999-test-evidence-grounded/.meta.json` exists
- **Estimated:** 5 min

#### Task 5.2.2: Run Through Spec Phase
- **Why:** Implements Plan 5.2 - validates spec enhancements
- **Depends on:** 5.2.1
- **Blocks:** 5.2.3
- **Files:** `docs/dev_artifacts/workitems/999-test-evidence-grounded/spec.md`
- **Do:**
  1. Run `/iflow-dev:specify`
  2. Verify spec.md contains Feasibility Assessment section
  3. Verify git log shows `phase(specify): test-evidence-grounded - approved`
- **Test:** Grep spec.md for "Feasibility Assessment"
- **Done when:** Feasibility section present and commit exists
- **Estimated:** 10 min

#### Task 5.2.3: Run Through Design Phase
- **Why:** Implements Plan 5.2 - validates design enhancements
- **Depends on:** 5.2.2
- **Blocks:** 5.2.4
- **Files:** `docs/dev_artifacts/workitems/999-test-evidence-grounded/design.md`
- **Do:**
  1. Run `/iflow-dev:design`
  2. Verify Stage 0 Research executed (or skip offered)
  3. Verify design.md contains Prior Art Research section
  4. Verify git log shows `phase(design): test-evidence-grounded - approved`
- **Test:** Grep design.md for "Prior Art Research"
- **Done when:** Prior Art section present and commit exists
- **Estimated:** 15 min

#### Task 5.2.4: Run Through Plan Phase
- **Why:** Implements Plan 5.2 - validates plan enhancements
- **Depends on:** 5.2.3
- **Blocks:** 5.2.5
- **Files:** `docs/dev_artifacts/workitems/999-test-evidence-grounded/plan.md`
- **Do:**
  1. Run `/iflow-dev:create-plan`
  2. Verify plan.md contains "Why this item" and "Why this order" fields
  3. Verify NO LOC estimates in plan
  4. Verify git log shows `phase(plan): test-evidence-grounded - approved`
- **Test:** Grep plan.md for "Why this item"; grep -v for "lines of code"
- **Done when:** Why fields present, no LOC, commit exists
- **Estimated:** 10 min

#### Task 5.2.5: Run Through Tasks Phase
- **Why:** Implements Plan 5.2 - validates task enhancements
- **Depends on:** 5.2.4
- **Blocks:** 5.2.6
- **Files:** `docs/dev_artifacts/workitems/999-test-evidence-grounded/tasks.md`
- **Do:**
  1. Run `/iflow-dev:create-tasks`
  2. Verify tasks.md contains "Why:" field on each task
  3. Verify git log shows `phase(tasks): test-evidence-grounded - approved`
- **Test:** Grep tasks.md for "**Why:**"
- **Done when:** Why fields present and commit exists
- **Estimated:** 10 min

#### Task 5.2.6: Cleanup Test Feature
- **Why:** Implements Plan 5.2 - removes test artifact
- **Depends on:** 5.2.5
- **Blocks:** None
- **Files:** `docs/dev_artifacts/workitems/999-test-evidence-grounded/`
- **Do:**
  1. Run `rm -rf docs/features/999-test-evidence-grounded`
  2. Commit cleanup: `git add -A && git commit -m "test: cleanup 999-test-evidence-grounded"`
- **Test:** `ls docs/features/999-test-evidence-grounded` returns error
- **Done when:** Test feature folder deleted
- **Estimated:** 2 min

---

## Summary

| Phase | Plan Items | Tasks | Parallel Groups |
|-------|------------|-------|-----------------|
| 1. Spec | 3 | 6 | 2 (1.1.x, 1.2.x can parallel) |
| 2. Design | 3 | 9 | 2 (2.1.x, 2.2.x can parallel) |
| 3. Plan | 3 | 5 | 2 (3.1.x, 3.2.x can parallel) |
| 4. Tasks | 3 | 4 | 2 (4.1.x, 4.2.x can parallel) |
| 5. Validation | 2 | 7 | 1 (sequential) |
| **Total** | **14** | **31** | **9** |

## Parallel Execution Groups

```
Group 1: 1.1.1, 1.2.1 (Spec skill + agent, parallel)
Group 2: 2.1.1, 2.2.1 (Design skill + agent, parallel)
Group 3: 3.1.1, 3.2.1 (Plan skill + agent, parallel)
Group 4: 4.1.1, 4.2.1 (Task skill + agent, parallel)
```
