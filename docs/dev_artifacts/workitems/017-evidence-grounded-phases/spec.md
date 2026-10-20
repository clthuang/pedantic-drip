# Spec: Evidence-Grounded Workflow Phases

## Problem Statement

The iflow workflow phases produce artifacts without capturing reasoning, evidence, or trade-offs behind decisions, and reviewers don't independently verify claims.

## Success Criteria

- SC-1: Spec phase feasibility section includes: (a) first-principles reasoning, (b) at least one codebase reference OR external evidence, (c) verdict (Confirmed/Likely/Uncertain/Unlikely/Impossible) with cited evidence
- SC-2: Design phase includes Prior Art Research section (executed before architecture) with: solutions found, rejection reasons, adopted patterns
- SC-3: Every plan item has: "Why this item", "Why this order", deliverable (no LOC/time), verification method
- SC-4: Every task has "Why" field that references specific plan item ID or design component
- SC-5: Each phase auto-commits AND auto-pushes after phase-reviewer approval (4 commands: specify, design, create-plan, create-tasks)
- SC-6: Reviewers MUST perform independent verification of at least one author claim per artifact and include verification evidence in review output

## Scope

### In Scope

- Add feasibility assessment section to specifying skill (output template)
- Add WebSearch, Context7 tools to spec-skeptic agent
- Add Stage 0 (Prior Art Research) to design command (before architecture stage)
- Add reasoning/evidence fields to designing skill (Technical Decisions format)
- Add WebSearch, Context7 tools to design-reviewer agent
- Add reasoning fields ("Why this item", "Why this order") to planning skill
- Add concurrent planning option to create-plan command (for designs with 3+ independent modules)
- Add "Why" traceability field to breaking-down-tasks skill
- Add auto-commit AND auto-push after phase-reviewer approval (all 4 phase commands)

### Out of Scope

- Changing phase order or adding new phases
- Modifying finish/release workflow
- Changes to brainstorm phase
- Changes to implement phase
- Removing time estimates from task breakdown (kept for implementer guidance)

## Acceptance Criteria

### AC-1: Spec Feasibility Assessment
- **Given** a spec is being written
- **When** the specifying skill executes
- **Then** spec.md includes "Feasibility Assessment" section with:
  - Assessment approach (first principles, codebase evidence, external evidence)
  - Feasibility scale verdict: Confirmed | Likely | Uncertain | Unlikely | Impossible
  - At least one evidence citation (file:line OR URL OR explicit first-principle statement)
  - Key assumptions with status (Verified at {location} | Needs verification)
  - Open risks if assumptions are wrong

### AC-2: Spec Reviewer Mandatory Verification
- **Given** spec-skeptic reviews a spec
- **When** the spec contains feasibility claims or library/API assumptions
- **Then** spec-skeptic MUST:
  - Use Context7 or WebSearch to verify at least one claim independently
  - Include verification result in review output: "Verified: {claim} via {source}"
  - If verification tools unavailable, explicitly note: "Unable to verify independently - flagged for human review"

### AC-3: Design Prior Art Research
- **Given** design phase starts
- **When** design command executes
- **Then** Stage 0 (Research) runs BEFORE architecture stage:
  - Codebase-explorer agent searches for similar patterns
  - Internet-researcher agent searches external sources
  - Results recorded in design.md "Prior Art Research" section
  - User may skip with explicit "Skip (domain expert)" choice

### AC-4: Design Evidence-Grounded Decisions
- **Given** a technical decision is documented
- **When** designing skill writes to design.md
- **Then** each decision MUST include:
  - Choice made
  - Alternatives considered with rejection reason for each
  - Trade-offs: explicit pros and cons
  - Engineering principle applied (KISS | YAGNI | DRY | etc.)
  - Evidence: codebase reference (file:line) OR documentation URL OR first-principles reasoning

### AC-5: Design Reviewer Mandatory Verification
- **Given** design-reviewer reviews a design
- **When** design claims existing patterns or library capabilities
- **Then** design-reviewer MUST:
  - Use Context7/WebSearch/Grep to verify at least 2 claims independently
  - Include verification results in review output
  - If claim cannot be verified, flag as "Unverified assumption"

### AC-6: Plan Reasoning Fields
- **Given** a plan item is documented
- **When** planning skill writes to plan.md
- **Then** each item MUST include:
  - "Why this item": rationale referencing design component or requirement
  - "Why this order": rationale referencing dependencies or build sequence
  - Deliverable: concrete output description (NOT LOC, time is optional)
  - Verification: how to confirm item is complete

### AC-7: Task Traceability
- **Given** a task is created
- **When** breaking-down-tasks skill writes to tasks.md
- **Then** each task includes:
  - "Why" field with explicit reference to plan item (e.g., "Implements Plan 2.1")
  - If no plan reference exists, task-reviewer flags as potential scope creep

### AC-8: Auto-Commit and Push After Approval
- **Given** phase-reviewer approves a phase artifact (specify, design, create-plan, create-tasks)
- **When** approval is recorded in .meta.json
- **Then** the command executes:
  1. `git add docs/features/{id}-{slug}/{artifact}.md docs/features/{id}-{slug}/.meta.json`
  2. `git commit -m "phase({phase}): {slug} - approved"`
  3. `git push`
- **And** on commit failure: display error, do NOT mark phase completed, allow retry
- **And** on push failure: commit succeeds locally, warn user, provide manual push command, mark phase completed

### AC-9: Concurrent Planning (Optional)
- **Given** design has 3+ independent components (no shared file dependencies)
- **When** create-plan command detects `parallelPlanning: true` in .meta.json
- **Then** user is offered concurrent planning option:
  - Dispatch parallel plan agents per component group
  - Merge results into single plan.md in dependency order
  - If user declines, proceed with sequential planning

## Dependencies

- Context7 MCP server (plugin-context7)
- WebSearch tool (built-in)
- Existing phase commands: specify.md, design.md, create-plan.md, create-tasks.md
- Existing skills: specifying, designing, planning, breaking-down-tasks
- Existing agents: spec-skeptic, design-reviewer, plan-reviewer, task-reviewer

## Fallback Behavior

- **Context7 unavailable**: Use WebSearch only for verification
- **Both Context7 and WebSearch unavailable**: Reviewer notes "Unable to verify independently" and flags for human review
- **Push fails but commit succeeds**: Phase completes, user manually pushes later

## Open Questions

None - design decisions resolved:
1. Feasibility "Unlikely/Impossible" does NOT block spec (author discretion)
2. Prior Art Research runs in all modes (skippable via explicit user choice)
3. Commit message format: `phase({phase}): {slug} - approved`
4. Time estimates in tasks KEPT (separate from LOC concern)
