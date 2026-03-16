---
name: planning
description: Produces plan.md with dependencies and ordering. Use when the user says 'create a plan', 'plan the implementation', 'sequence the work', or 'determine build order'.
---

# Planning Phase

## Config Variables
Use these values from session context (injected at session start):
- `{iflow_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Create an ordered implementation plan.

## Prerequisites

- Read `design.md` for architecture (guaranteed present — hard prerequisite at command level)

## Read Feature Context

1. Find active feature folder in `{iflow_artifacts_root}/features/`
2. Read `.meta.json` for mode and context
3. Adjust behavior based on mode:
   - Standard: Full process with optional verification
   - Full: Full process with required verification

## Process

### 1. Identify Work Items

From design, list everything that needs building:
- Components
- Interfaces
- Tests
- Documentation

### 2. Map Dependencies

For each item:
- What must exist before this can start?
- What depends on this?

### 3. Determine Order

Build dependency graph, then sequence:
1. Independent items (can start immediately)
2. Items with resolved dependencies
3. Items waiting on others

### 4. Estimate Complexity

Not time estimates. Complexity indicators:
- Simple: Straightforward implementation
- Medium: Some decisions needed
- Complex: Significant work or risk

## Estimation Approach

**Use deliverables, not LOC or time:**
- GOOD: "Create UserService with login method"
- GOOD: "Add validation to signup form"
- BAD: "~50 lines of code"
- BAD: "~2 hours"

**Complexity = decisions, not size:**
- Simple: Follow established pattern, no new decisions
- Medium: Some decisions needed, pattern exists
- Complex: Significant decisions, may need research

## Output: plan.md

Write to `{iflow_artifacts_root}/features/{id}-{slug}/plan.md`:

```markdown
# Plan: {Feature Name}

## Implementation Order

### Stage 1: Foundation
Items with no dependencies.

1. **{Item}** — {brief description}
   - **Why this item:** {rationale referencing design/requirement}
   - **Why this order:** {rationale referencing dependencies}
   - **Deliverable:** {concrete output, NOT LOC}
   - **Complexity:** Simple/Medium/Complex
   - **Files:** {files to create/modify}
   - **Verification:** {how to confirm complete}

2. **{Item}** — {brief description}
   ...

### Stage 2: Core Implementation
Items depending on Stage 1.

1. **{Item}** — {brief description}
   - **Why this item:** {rationale referencing design/requirement}
   - **Why this order:** {rationale - depends on Stage 1 items}
   - **Deliverable:** {concrete output, NOT LOC}
   - **Complexity:** Simple/Medium/Complex
   - **Files:** {files to create/modify}
   - **Verification:** {how to confirm complete}

### Stage 3: Integration
Items depending on Stage 2.

...

## Dependency Graph

```
{Item A} ──→ {Item B} ──→ {Item D}
                    ↘
{Item C} ──────────→ {Item E}
```

## Risk Areas

- {Complex item}: {why it's risky}

## Testing Strategy

- Unit tests for: {components}
- Integration tests for: {interactions}

## Definition of Done

- [ ] All items implemented
- [ ] Tests passing
- [ ] Code reviewed
```

## Completion

"Plan complete. Saved to plan.md."
"Run /iflow:show-status to check, or /iflow:create-tasks to break into actionable items."
