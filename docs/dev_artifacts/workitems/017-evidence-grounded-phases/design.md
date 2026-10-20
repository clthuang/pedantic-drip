# Design: Evidence-Grounded Workflow Phases

## Architecture Overview

This feature enhances 4 workflow phases (spec, design, plan, tasks) with reasoning, evidence, and auto-commit capabilities. Changes are primarily additive - extending existing templates, adding tools to agents, and inserting new stages/steps into commands.

```
┌─────────────────────────────────────────────────────────────┐
│                    PHASE ENHANCEMENTS                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  SPEC PHASE                                                 │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────┐     │
│  │ specifying  │──▶│ spec-skeptic │──▶│  specify    │     │
│  │   skill     │   │    agent     │   │   command   │     │
│  │ +Feasibility│   │ +WebSearch   │   │ +AutoCommit │     │
│  │  section    │   │ +Context7    │   │             │     │
│  └─────────────┘   └──────────────┘   └─────────────┘     │
│                                                             │
│  DESIGN PHASE                                               │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────┐     │
│  │ designing   │──▶│design-reviewer──▶│   design    │     │
│  │   skill     │   │    agent     │   │   command   │     │
│  │ +PriorArt   │   │ +WebSearch   │   │ +Stage0     │     │
│  │ +Evidence   │   │ +Context7    │   │ +AutoCommit │     │
│  └─────────────┘   └──────────────┘   └─────────────┘     │
│                                                             │
│  PLAN PHASE                                                 │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────┐     │
│  │  planning   │──▶│plan-reviewer │──▶│ create-plan │     │
│  │   skill     │   │    agent     │   │   command   │     │
│  │ +WhyFields  │   │ +WhyCheck    │   │ +AutoCommit │     │
│  │             │   │              │   │             │     │
│  └─────────────┘   └──────────────┘   └─────────────┘     │
│                                                             │
│  TASK PHASE                                                 │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────┐     │
│  │breaking-down│──▶│task-reviewer │──▶│create-tasks │     │
│  │   skill     │   │    agent     │   │   command   │     │
│  │ +WhyField   │   │ +WhyCheck    │   │ +AutoCommit │     │
│  └─────────────┘   └──────────────┘   └─────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Components

### Component 1: Specifying Skill Enhancement
- **Purpose:** Add Feasibility Assessment section to spec.md output template
- **Location:** `plugins/iflow-dev/skills/specifying/SKILL.md`
- **Changes:**
  - Add Feasibility Assessment section template after Acceptance Criteria
  - Add 2 new self-check items for feasibility
- **Inputs:** PRD content, user requirements
- **Outputs:** spec.md with new Feasibility Assessment section

### Component 2: Spec-Skeptic Agent Enhancement
- **Purpose:** Enable independent verification of feasibility claims
- **Location:** `plugins/iflow-dev/agents/spec-skeptic.md`
- **Changes:**
  - Add WebSearch, Context7 MCP tools to frontmatter
  - Add "Feasibility Verification" category to review checklist
  - Add "Independent Verification" instructions
- **Inputs:** spec.md content
- **Outputs:** Review JSON with feasibility verification results

### Component 3: Designing Skill Enhancement
- **Purpose:** Add Prior Art Research and evidence-grounded Technical Decisions
- **Location:** `plugins/iflow-dev/skills/designing/SKILL.md`
- **Changes:**
  - Add Prior Art Research section template at top of output
  - Enhance Technical Decisions format with alternatives, trade-offs, principles, evidence
  - Add new self-check items
- **Inputs:** spec.md, codebase patterns, external research
- **Outputs:** design.md with Prior Art and evidence-grounded decisions

### Component 4: Design-Reviewer Agent Enhancement
- **Purpose:** Enable independent verification of design claims
- **Location:** `plugins/iflow-dev/agents/design-reviewer.md`
- **Changes:**
  - Add WebSearch, Context7 MCP tools to frontmatter
  - Add "Prior Art Verification" and "Evidence Grounding" categories
  - Add "Independent Verification" instructions (verify 2+ claims)
- **Inputs:** design.md content
- **Outputs:** Review JSON with verification results

### Component 5: Design Command Enhancement
- **Purpose:** Add Stage 0 Research, parallel planning flag, auto-commit
- **Location:** `plugins/iflow-dev/commands/design.md`
- **Changes:**
  - Insert Stage 0 (Research) before Stage 1 (Architecture)
  - Add auto-commit step after Stage 4 (Handoff Review)
- **Inputs:** Feature context, spec.md
- **Outputs:** design.md
- **Stage 0 Failure Handling:**
  - If codebase-explorer fails/timeouts: Note "codebase search unavailable" in Prior Art section
  - If internet-researcher fails/returns empty: Note "no external solutions found" in Prior Art section
  - Both failures: Proceed to architecture with empty Prior Art section (user can skip)
  - User always has "Skip (domain expert)" option to bypass research entirely

### Component 6: Planning Skill Enhancement
- **Purpose:** Add reasoning fields to plan items
- **Location:** `plugins/iflow-dev/skills/planning/SKILL.md`
- **Changes:**
  - Update plan item format to include "Why this item", "Why this order", "Verification"
  - Add Estimation Approach section (deliverables, not LOC)
- **Inputs:** design.md
- **Outputs:** plan.md with reasoning fields

### Component 7: Plan-Reviewer Agent Enhancement
- **Purpose:** Verify reasoning fields and no LOC estimates
- **Location:** `plugins/iflow-dev/agents/plan-reviewer.md`
- **Changes:**
  - Add "Reasoning Verification" category
  - Add challenge patterns for missing "Why" and LOC estimates
- **Inputs:** plan.md content
- **Outputs:** Review JSON with reasoning verification

### Component 8: Create-Plan Command Enhancement
- **Purpose:** Add auto-commit (concurrent planning deferred)
- **Location:** `plugins/iflow-dev/commands/create-plan.md`
- **Changes:**
  - Add step 5b: Auto-Commit Phase Artifact
- **Inputs:** design.md
- **Outputs:** plan.md, git commit/push
- **Note:** Concurrent planning (AC-9) is deferred to a future iteration. The spec marks it as "Optional" and the dispatch/merge mechanism is complex. For now, plan sequentially.

### Component 9: Breaking-Down-Tasks Skill Enhancement
- **Purpose:** Add traceability "Why" field to task template
- **Location:** `plugins/iflow-dev/skills/breaking-down-tasks/SKILL.md`
- **Changes:**
  - Add "Why" field to task template (traces to plan item)
- **Inputs:** plan.md
- **Outputs:** tasks.md with Why fields

### Component 10: Task-Reviewer Agent Enhancement
- **Purpose:** Verify task traceability
- **Location:** `plugins/iflow-dev/agents/task-reviewer.md`
- **Changes:**
  - Add "Reasoning Traceability" category
  - Add challenge patterns for missing/invalid Why fields
- **Inputs:** tasks.md content
- **Outputs:** Review JSON with traceability verification

### Component 11: Create-Tasks Command Enhancement
- **Purpose:** Add auto-commit after approval
- **Location:** `plugins/iflow-dev/commands/create-tasks.md`
- **Changes:**
  - Add step 6b: Auto-Commit Phase Artifact
- **Inputs:** tasks.md, .meta.json
- **Outputs:** git commit/push

### Component 12: Specify Command Enhancement
- **Purpose:** Add auto-commit after phase-reviewer approval
- **Location:** `plugins/iflow-dev/commands/specify.md`
- **Changes:**
  - Add step after phase-reviewer (Stage 2): Auto-Commit Phase Artifact
- **Inputs:** spec.md, .meta.json, .review-history.md
- **Outputs:** git commit/push

## Interfaces

### Interface 1: Feasibility Assessment Section (spec.md)
```markdown
## Feasibility Assessment

### Assessment Approach
1. **First Principles** - {constraints that apply}
2. **Codebase Evidence** - {pattern at file:line}
3. **External Evidence** - {URL or "N/A"}

### Feasibility Scale
| Level | Meaning | Evidence Required |
|-------|---------|-------------------|
| Confirmed | Verified working approach | Code ref or docs |
| Likely | No blockers, standard patterns | First principles |
| Uncertain | Assumptions need validation | List assumptions |
| Unlikely | Significant obstacles | Document obstacles |
| Impossible | Violates constraints | State constraint |

### Assessment
**Overall:** {Confirmed | Likely | Uncertain | Unlikely | Impossible}
**Reasoning:** {WHY}
**Key Assumptions:**
- {Assumption} — {Verified at {location} | Needs verification}
**Open Risks:** {Risks}
```

### Interface 2: Prior Art Research Section (design.md)
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
{Why existing doesn't fit, what we're reusing}
```

### Interface 3: Enhanced Technical Decision (design.md)
```markdown
### {Decision Name}
- **Choice:** {what decided}
- **Alternatives Considered:**
  1. {Alt A} — Rejected: {reason}
  2. {Alt B} — Rejected: {reason}
- **Trade-offs:** Pros: {benefits} | Cons: {accepted drawbacks}
- **Rationale:** {why, based on trade-off analysis}
- **Engineering Principle:** {KISS | YAGNI | DRY | Single Responsibility | etc.}
- **Evidence:** {Codebase: file:line | Documentation: URL | First Principles: reasoning}
```

### Interface 4: Enhanced Plan Item (plan.md)
```markdown
1. **{Item Name}** — {description}
   - **Why this item:** {rationale referencing design or requirement}
   - **Why this order:** {rationale referencing dependencies}
   - **Deliverable:** {concrete output, NOT LOC}
   - **Complexity:** Simple/Medium/Complex
   - **Files:** {files to modify}
   - **Verification:** {how to confirm complete}
```

### Interface 5: Enhanced Task (tasks.md)
```markdown
#### Task 1.1: {Verb + Object + Context}
- **Why:** Implements Plan {X.Y} / Design Component {Name}
- **Depends on:** {task refs}
- **Blocks:** {task refs}
- **Files:** {paths}
- **Do:** {steps}
- **Test:** {command}
- **Done when:** {criteria}
- **Estimated:** {time}
```

### Interface 6: Auto-Commit Step (all 4 commands)
```markdown
### {N}b. Auto-Commit Phase Artifact

After phase-reviewer approval:
```bash
git add docs/features/{id}-{slug}/{artifact}.md docs/features/{id}-{slug}/.meta.json docs/features/{id}-{slug}/.review-history.md
git commit -m "phase({phase}): {slug} - approved"
git push
```

**Error handling:**
- On commit failure: Display error, do NOT mark phase completed, allow retry
- On push failure: Commit succeeds locally, warn user with "Run: git push" instruction, mark phase completed
```

### Interface 7: Agent Tools Enhancement (YAML frontmatter)
```yaml
# Before
tools: [Read, Glob, Grep]

# After
tools: [Read, Glob, Grep, WebSearch, mcp__context7__resolve-library-id, mcp__context7__query-docs]
```

### Interface 8: Research Agent Output Format
```markdown
## Stage 0 Research Results

**Codebase Search:**
{Output from codebase-explorer agent, or "Search unavailable/skipped"}

**External Research:**
{Output from internet-researcher agent, or "No results found/skipped"}

**User Decision:** {Review findings | Proceed | Skip (domain expert)}
```

Note: Parallel planning feature (AC-9) is deferred to future iteration.

## Technical Decisions

### TD-1: Additive Changes Only
- **Choice:** Extend existing templates and agents rather than replacing them
- **Alternatives Considered:**
  1. Create new v2 skills/agents — Rejected: Increases maintenance burden, breaks existing workflows
  2. Feature flag approach — Rejected: Unnecessary complexity for private tooling
- **Trade-offs:** Pros: Backward compatible, minimal risk | Cons: Files grow larger
- **Rationale:** CLAUDE.md says "No backward compatibility" for private tooling, but additive changes are still simpler
- **Engineering Principle:** KISS
- **Evidence:** Codebase: existing skill/agent files are already 100-200 lines, adding 20-50 lines is manageable

### TD-2: Research Tools Selection
- **Choice:** Use WebSearch + Context7 MCP tools for independent verification
- **Alternatives Considered:**
  1. WebSearch only — Rejected: Can't verify library-specific claims accurately
  2. Context7 only — Rejected: Can't verify non-library claims (standards, best practices)
  3. Custom research agent — Rejected: Reinventing existing tools
- **Trade-offs:** Pros: Comprehensive verification | Cons: Depends on MCP availability
- **Rationale:** Both tools already available, cover different verification needs
- **Engineering Principle:** Don't reinvent the wheel
- **Evidence:** Codebase: plan-reviewer agent already uses WebSearch and Context7 (`plugins/iflow-dev/agents/plan-reviewer.md`)

### TD-3: Stage 0 Research Placement
- **Choice:** Add research stage BEFORE architecture in design command
- **Alternatives Considered:**
  1. Research as part of architecture stage — Rejected: Conflates discovery with design
  2. Research as separate command — Rejected: Adds workflow step, user friction
- **Trade-offs:** Pros: Clear separation of concerns | Cons: Adds stage to design workflow
- **Rationale:** Research should inform design decisions, not be done in parallel with them
- **Engineering Principle:** Single Responsibility
- **Evidence:** First Principles: You can't design well without knowing what already exists

### TD-4: Parallel Planning Eligibility Criteria
- **Choice:** 3+ components with defined interfaces, no circular dependencies, distinct files
- **Alternatives Considered:**
  1. Always allow parallel — Rejected: Dependent modules would conflict
  2. Never allow parallel — Rejected: Misses efficiency gains for modular designs
- **Trade-offs:** Pros: Safe parallelization | Cons: Requires analysis after design
- **Rationale:** These criteria ensure modules are truly independent
- **Engineering Principle:** Separation of Concerns
- **Evidence:** First Principles: Parallel work is safe when there are no shared resources

### TD-5: Auto-Commit Error Handling
- **Choice:** Commit failure blocks, push failure warns but continues
- **Alternatives Considered:**
  1. Both failures block — Rejected: Network issues shouldn't block local work
  2. Both failures warn — Rejected: Local commit failure may indicate real problem
- **Trade-offs:** Pros: Robust to network issues | Cons: User may forget to push
- **Rationale:** Local commit is critical (preserves work), push can be retried
- **Engineering Principle:** Fail fast for local issues, graceful degradation for network
- **Evidence:** Spec AC-8: "on push failure: commit succeeds locally, warn user, provide manual push command, mark phase completed"

### TD-6: Reviewer Verification Counts
- **Choice:** spec-skeptic verifies 1 claim, design-reviewer verifies 2 claims
- **Alternatives Considered:**
  1. Same count for all — Rejected: Design has more claims to verify
  2. No minimum — Rejected: Defeats purpose of independent verification
  3. Verify all claims — Rejected: Too slow, diminishing returns
- **Trade-offs:** Pros: Practical verification | Cons: Some claims unverified
- **Rationale:** Spot-checking is more practical than exhaustive verification
- **Engineering Principle:** Pareto principle (80/20)
- **Evidence:** First Principles: Independent verification of a sample builds trust efficiently

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Research stage slows design | Medium | User can skip with "domain expert" option |
| Context7/WebSearch unavailable | Low | Fallback: note "unable to verify" in review |
| Auto-push fails repeatedly | Low | Phase completes locally, user handles push |
| Large files after additions | Low | Changes are ~30-50 lines per file |
| Reviewer misses tool calls | Medium | Instructions explicitly require verification |
| Research agents fail/timeout | Low | Gracefully degrade: note unavailable, proceed |

## Deferred Features

### AC-9: Concurrent Planning
- **Status:** Deferred to future iteration
- **Reason:** Dispatch and merge mechanism is complex; requires defining component grouping, conflict resolution, and merge algorithm
- **Impact:** Plans are created sequentially (current behavior)
- **Future Work:** When needed, design a proper concurrent planning system with dependency analysis

## Dependencies

- **Existing**: codebase-explorer agent, internet-researcher agent (both exist per Glob results)
- **External**: Context7 MCP server (plugin-context7), WebSearch (built-in)
- **Commands**: specify.md, design.md, create-plan.md, create-tasks.md (all exist)
- **Skills**: specifying, designing, planning, breaking-down-tasks (all exist)
- **Agents**: spec-skeptic, design-reviewer, plan-reviewer, task-reviewer (all exist)
