# PRD: Evidence-Grounded Workflow Phases

## Problem Statement

The iflow workflow phases (spec, design, plan, tasks) produce artifacts without capturing the reasoning, evidence, and trade-offs behind decisions. Reviewers validate format and completeness but don't independently verify claims. Phase artifacts aren't auto-committed, risking loss and creating silos.

## Goals

1. **Feasibility assessment in Spec** - Evaluate possibility (not difficulty) using first principles, codebase evidence, and external research when needed
2. **Evidence-grounded Design** - Every technical decision backed by reasoning, trade-offs, references, and engineering principles; mandatory "don't reinvent the wheel" research
3. **Reasoning-rich Plans** - Every plan item explains WHY (no LOC estimates, deliverable-based units only); concurrent planning for well-defined modules
4. **Traced Tasks** - Every task links to its plan/design origin
5. **Auto-commit after approval** - Phase artifacts committed and pushed when phase-reviewer approves (not optional)
6. **Independent verification** - Reviewers verify claims using same + different sources, not just trust author

## Scope

### In Scope
- Spec phase: Feasibility assessment section, spec-skeptic gets research tools
- Design phase: Prior art research stage, reasoning/evidence sections, design-reviewer gets Context7/WebSearch
- Plan phase: Reasoning fields, concurrent planning option, no LOC estimates
- Task phase: Reasoning/traceability field
- All phases: Auto-commit + push after approval

### Out of Scope
- Changing the overall phase order
- Adding new phases
- Modifying finish/release workflow

---

## Implementation Plan

### Files to Modify

| Phase | Files | Changes |
|-------|-------|---------|
| Spec | `skills/specifying/SKILL.md` | Add Feasibility Assessment section |
| Spec | `agents/spec-skeptic.md` | Add Context7/WebSearch tools, feasibility verification |
| Spec | `commands/specify.md` | Add auto-commit after approval |
| Design | `skills/designing/SKILL.md` | Add Prior Art Research section, reasoning/evidence to Technical Decisions |
| Design | `agents/design-reviewer.md` | Add Context7/WebSearch tools, prior-art verification |
| Design | `commands/design.md` | Add Stage 0 Research, parallel planning flag, auto-commit |
| Plan | `skills/planning/SKILL.md` | Add reasoning fields, confirm no LOC, deliverable-based |
| Plan | `agents/plan-reviewer.md` | Add reasoning verification |
| Plan | `commands/create-plan.md` | Add concurrent planning option, auto-commit |
| Tasks | `skills/breaking-down-tasks/SKILL.md` | Add reasoning/traceability field |
| Tasks | `agents/task-reviewer.md` | Add reasoning validation |
| Tasks | `commands/create-tasks.md` | Add auto-commit |

---

## Detailed Changes

### 1. SPEC PHASE

#### 1.1 `plugins/iflow-dev/skills/specifying/SKILL.md`

Add new "Feasibility Assessment" section after Acceptance Criteria:

```markdown
## Feasibility Assessment

Evaluate whether requirements are achievable. Focus on POSSIBILITY, not difficulty.

### Assessment Approach
1. **First Principles** - What fundamental constraints apply?
2. **Codebase Evidence** - Existing patterns that support this? Location: {file:line}
3. **External Evidence** (if needed) - Documentation confirming approach? Source: {URL}

### Feasibility Scale
| Level | Meaning | Evidence Required |
|-------|---------|-------------------|
| Confirmed | Verified working approach | Code reference or documentation |
| Likely | No blockers, standard patterns | First principles reasoning |
| Uncertain | Assumptions need validation | List assumptions to verify |
| Unlikely | Significant obstacles | Document obstacles |
| Impossible | Violates constraints | State the constraint |

### Assessment
**Overall:** {Confirmed | Likely | Uncertain | Unlikely | Impossible}
**Reasoning:** {WHY, based on evidence}
**Key Assumptions:**
- {Assumption} — Status: {Verified at {location} | Needs verification}
**Open Risks:** {Risks if assumptions wrong}
```

Add to Self-Check:
```markdown
- [ ] Feasibility assessment uses evidence, not opinion?
- [ ] Assumptions explicitly listed?
```

#### 1.2 `plugins/iflow-dev/agents/spec-skeptic.md`

Change tools from `[Read, Glob, Grep]` to:
```yaml
tools: [Read, Glob, Grep, WebSearch, mcp__context7__resolve-library-id, mcp__context7__query-docs]
```

Add new verification category:
```markdown
### Feasibility Verification
- [ ] Feasibility assessment exists
- [ ] Uses evidence (code refs, docs, first principles)
- [ ] No unverified "Likely" on critical paths
- [ ] Assumptions are testable

**Independent Verification:**
- Library claims → Use Context7 to verify
- API claims → Use WebSearch for docs
- Codebase claims → Use Grep/Read to verify
```

#### 1.3 `plugins/iflow-dev/commands/specify.md`

Add after spec-skeptic approval (before step 5):

```markdown
### 4b. Auto-Commit Phase Artifact

After approval:
```bash
git add docs/features/{id}-{slug}/spec.md docs/features/{id}-{slug}/.meta.json
git commit -m "phase(specify): {slug} - approved"
git push
```
If push fails: Note in `.meta.json`, don't block.
```

---

### 2. DESIGN PHASE

#### 2.1 `plugins/iflow-dev/skills/designing/SKILL.md`

Add "Prior Art Research" section at top of output:

```markdown
## Prior Art Research

### Research Conducted
| Question | Source | Finding |
|----------|--------|---------|
| Similar pattern in codebase? | Grep/Read | {Yes at {location} / No} |
| Library support? | Context7 | {Yes: {method} / No} |
| Industry standard? | WebSearch | {Yes: {reference} / No} |

### Existing Solutions Evaluated
| Solution | Source | Why Used/Not Used |
|----------|--------|-------------------|
| {pattern} | {location} | {Adopted/Rejected because...} |

### Novel Work Justified
If building new: Why existing doesn't fit, what we're reusing.
```

Enhance Technical Decisions format:

```markdown
### {Decision}
- **Choice:** {what decided}
- **Alternatives Considered:**
  1. {Alt A} — Rejected: {reason}
  2. {Alt B} — Rejected: {reason}
- **Trade-offs:** Pros: {benefits} | Cons: {accepted drawbacks}
- **Rationale:** {why, based on trade-off analysis}
- **Engineering Principle:** {KISS | YAGNI | DRY | etc.}
- **Evidence:** {Codebase: file:line | Documentation: URL | First Principles: reasoning}
```

#### 2.2 `plugins/iflow-dev/agents/design-reviewer.md`

Change tools from `[Read, Glob, Grep]` to:
```yaml
tools: [Read, Glob, Grep, WebSearch, mcp__context7__resolve-library-id, mcp__context7__query-docs]
```

Add verification sections:

```markdown
### Prior Art Verification
- [ ] Research section exists
- [ ] Library claims verified (use Context7)
- [ ] Codebase claims verified (use Grep/Read)
- [ ] "Novel work" is truly novel

### Evidence Grounding
- [ ] Every decision has evidence
- [ ] Evidence sources verifiable
- [ ] Trade-offs explicit
- [ ] Engineering principles named

**Independent Verification:**
Pick 2-3 key claims, verify using YOUR tools. Don't trust without checking.
```

#### 2.3 `plugins/iflow-dev/commands/design.md`

Add Stage 0 before Stage 1:

```markdown
### 4. Execute 5-Stage Workflow

```
Stage 0: RESEARCH ("Don't Reinvent the Wheel")
    ↓
Stage 1: ARCHITECTURE DESIGN
    ↓
Stage 2: INTERFACE DESIGN
    ↓
Stage 3: DESIGN REVIEW LOOP
    ↓
Stage 4: HANDOFF REVIEW
```

#### Stage 0: Research

a. Mark stage started in `.meta.json`

b. Dispatch parallel research agents:
   ```
   Task 1: iflow-dev:codebase-explorer
     "Find existing patterns related to: {feature}"

   Task 2: iflow-dev:internet-researcher
     "Research existing solutions for: {feature}"
   ```

c. Present findings:
   ```
   AskUserQuestion: "Research found {n} patterns. Review before designing?"
   Options: Review findings | Proceed | Skip (domain expert)
   ```

d. Record in design.md Prior Art section

e. Mark stage completed
```

After Stage 3, add parallel planning assessment:

```markdown
e. **Assess parallel planning eligibility:**
   Check design.md for:
   - 3+ components with distinct responsibilities
   - All interfaces defined (Input/Output/Errors)
   - No circular dependencies
   - Components map to distinct files

   If met: `.meta.json` → `"parallelPlanning": true`
```

Add auto-commit after Stage 4:

```markdown
### 4c. Auto-Commit Phase Artifact

```bash
git add docs/features/{id}-{slug}/design.md docs/features/{id}-{slug}/.meta.json
git commit -m "phase(design): {slug} - approved"
git push
```
```

---

### 3. PLAN PHASE

#### 3.1 `plugins/iflow-dev/skills/planning/SKILL.md`

Change plan item format from simple to:

```markdown
1. **{Item}** — {description}
   - **Why this item:** {rationale for including}
   - **Why this order:** {rationale for sequencing}
   - **Deliverable:** {concrete output, NOT LOC}
   - **Complexity:** Simple/Medium/Complex
   - **Files:** {files to modify}
   - **Verification:** {how to confirm complete}
```

Add explicit guidance:

```markdown
## Estimation Approach

**Use deliverables, not LOC or time:**
- GOOD: "Create UserService with login method"
- BAD: "~50 lines of code"
- BAD: "~2 hours"

**Complexity = decisions, not size:**
- Simple: Follow established pattern
- Medium: Some decisions, pattern exists
- Complex: Significant decisions, may need research
```

#### 3.2 `plugins/iflow-dev/agents/plan-reviewer.md`

Add reasoning verification:

```markdown
### Reasoning Verification
- [ ] Every item has "Why this item"
- [ ] Every item has "Why this order"
- [ ] Rationales reference design/dependencies
- [ ] No LOC estimates (deliverables only)
- [ ] Deliverables concrete and verifiable

**Challenges:**
- Missing "Why" → "Why needed? Which design requirement?"
- LOC found → "Replace with deliverable"
- Vague deliverable → "What artifact proves completion?"
```

#### 3.3 `plugins/iflow-dev/commands/create-plan.md`

Add after step 3:

```markdown
### 3b. Check Parallel Planning

Read `.meta.json` for `parallelPlanning` flag.

If true:
```
AskUserQuestion: "Design has independent modules. Plan concurrently?"
Options: Yes - Parallel | No - Sequential
```

If Parallel:
- Read design.md for component groups
- Dispatch parallel Task calls per component
- Merge into single plan.md
```

Add auto-commit after step 5:

```markdown
### 5b. Auto-Commit Phase Artifact

```bash
git add docs/features/{id}-{slug}/plan.md docs/features/{id}-{slug}/.meta.json
git commit -m "phase(plan): {slug} - approved"
git push
```
```

---

### 4. TASK PHASE

#### 4.1 `plugins/iflow-dev/skills/breaking-down-tasks/SKILL.md`

Add reasoning field to task template:

```markdown
#### Task 1.1: {Verb + Object + Context}
- **Why:** {trace to plan item or design component}
- **Depends on:** ...
- **Blocks:** ...
- **Files:** ...
- **Do:** ...
- **Test:** ...
- **Done when:** ...
```

#### 4.2 `plugins/iflow-dev/agents/task-reviewer.md`

Add reasoning validation:

```markdown
### Reasoning Traceability
- [ ] Every task has "Why" field
- [ ] "Why" traces to plan item or design component
- [ ] No orphan tasks (without backing)

**Challenges:**
- Missing "Why" → "What plan item does this implement?"
- Can't trace → "Doesn't map to plan - scope creep?"
```

#### 4.3 `plugins/iflow-dev/commands/create-tasks.md`

Add auto-commit after step 6:

```markdown
### 6b. Auto-Commit Phase Artifact

```bash
git add docs/features/{id}-{slug}/tasks.md docs/features/{id}-{slug}/.meta.json
git commit -m "phase(tasks): {slug} - approved"
git push
```
```

---

## Commit Message Convention

All phase commits use format:
```
phase({phase}): {slug} - approved
```

Examples:
- `phase(specify): auth-refresh - approved`
- `phase(design): auth-refresh - approved`
- `phase(plan): auth-refresh - approved`
- `phase(tasks): auth-refresh - approved`

---

## Implementation Sequence

1. **Spec phase** (foundation) - specifying skill, spec-skeptic, specify command
2. **Design phase** (builds on spec) - designing skill, design-reviewer, design command
3. **Plan phase** (builds on design) - planning skill, plan-reviewer, create-plan command
4. **Task phase** (final) - breaking-down-tasks skill, task-reviewer, create-tasks command
5. **Validation** - Run validate.sh, test each phase end-to-end

---

## Verification

1. Run `./validate.sh` after all changes
2. Create test feature and run through spec → design → plan → tasks
3. Verify:
   - Feasibility section appears in spec.md
   - Prior art research runs before design
   - Reviewers use Context7/WebSearch for verification
   - Auto-commits happen after each phase approval
   - Reasoning fields present in plan and tasks
