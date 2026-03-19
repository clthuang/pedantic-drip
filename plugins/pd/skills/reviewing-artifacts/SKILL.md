---
name: reviewing-artifacts
description: Provides comprehensive quality criteria for PRD, spec, design, plan, and tasks. Use when reviewing artifact quality or validating phase transitions.
---

# Reviewing Artifacts

Quality criteria and review checklists for workflow artifacts.

## PRD Quality Criteria

### 1. Problem Definition

- [ ] Problem statement is specific and bounded
- [ ] Target user/persona identified
- [ ] Impact/value proposition clear
- [ ] Not a solution masquerading as a problem

### 2. Requirements Completeness

- [ ] Functional requirements enumerated
- [ ] Non-functional requirements stated (performance, security, etc.)
- [ ] Constraints documented (technical, business, regulatory)
- [ ] Success criteria are measurable

### 3. Evidence Standards

- [ ] Technical claims verified against codebase
- [ ] External claims have sources
- [ ] Assumptions explicitly labeled
- [ ] "Should work" replaced with "Verified at {location}" or "Assumption"

### 4. Intellectual Honesty

- [ ] Uncertainty acknowledged, not hidden
- [ ] Trade-offs stated explicitly
- [ ] Judgment calls labeled with reasoning
- [ ] No false certainty

### 5. Scope Discipline

- [ ] Clear boundaries (in scope / out of scope)
- [ ] Future possibilities deferred, not crammed in
- [ ] One coherent focus
- [ ] Out of scope items have rationale

---

## Spec Quality Criteria

### 1. Problem Precision

- [ ] Problem statement is ONE sentence
- [ ] Specific enough to test against
- [ ] No implementation details leaked
- [ ] Who is affected is explicit

### 2. Success Criteria Quality

- [ ] Each criterion is measurable
- [ ] Each criterion is independently testable
- [ ] Criteria cover all key outcomes
- [ ] No vague language ("fast", "good", "easy")

### 3. Scope Boundaries

- [ ] In Scope items are exhaustive
- [ ] Out of Scope items prevent scope creep
- [ ] No ambiguity about what's included
- [ ] Scope aligns with PRD (if exists)

### 4. Acceptance Criteria

- [ ] Given/When/Then format for each feature aspect
- [ ] Covers happy path
- [ ] Covers key error paths
- [ ] Specific enough to write tests from

### 5. Implementation Independence

- [ ] Describes WHAT, not HOW
- [ ] No technology choices embedded
- [ ] No architecture decisions
- [ ] Could be implemented multiple ways

### 6. Traceability

- [ ] Each requirement has a unique ID or clear name
- [ ] Dependencies are explicit
- [ ] Open questions are listed (not hidden)

---

## Design Quality Criteria

### 1. Architecture Clarity

- [ ] Components clearly defined with responsibilities
- [ ] Component boundaries explicit
- [ ] Data flows documented
- [ ] No circular dependencies

### 2. Interface Precision

- [ ] All interfaces have method signatures
- [ ] Input/output types specified
- [ ] Error conditions defined
- [ ] Contract invariants stated

### 3. Technical Decisions

- [ ] Key decisions documented with rationale
- [ ] Alternatives considered
- [ ] Trade-offs explicit
- [ ] No premature optimization

### 4. Risk Assessment

- [ ] Technical risks identified
- [ ] Mitigation strategies noted
- [ ] Dependencies on external systems documented
- [ ] Failure modes considered

### 5. Implementation Independence

- [ ] Design could be implemented multiple ways
- [ ] No code snippets (unless illustrative)
- [ ] Framework-agnostic where possible
- [ ] Abstractions are justified

---

## Plan Quality Criteria

### 1. Dependency Accuracy

- [ ] All dependencies explicit
- [ ] No circular dependencies
- [ ] Critical path identified
- [ ] Parallel opportunities noted

### 2. Sequencing Logic

- [ ] Order makes sense (interface → tests → implementation)
- [ ] Each step buildable
- [ ] No "magic" steps assumed
- [ ] Rollback points identified

### 3. Design Coverage

- [ ] Every design component has plan items
- [ ] Every interface has implementation steps
- [ ] No orphaned design items
- [ ] No scope creep from design

### 4. TDD Compliance

- [ ] Interface phase before implementation
- [ ] Test phase before code phase
- [ ] Verification steps explicit
- [ ] Refactor phase included

### 5. Risk Mitigation

- [ ] High-risk items early (fail fast)
- [ ] External dependencies planned
- [ ] Blockers identified
- [ ] Contingencies noted

### 6. No Time Estimates

- [ ] No time or LOC estimates (deliverables and complexity only)

---

## Tasks Quality Criteria

### 1. Task Size

- [ ] Each task 5-15 minutes
- [ ] No time estimates (use complexity level, not minutes/hours)
- [ ] Single responsibility per task
- [ ] Clear stopping point

### 2. Executability

- [ ] Verb + object format (e.g., "Add field X to Y")
- [ ] Exact file paths specified
- [ ] No "figure out" tasks
- [ ] No ambiguous instructions

### 3. Testability

- [ ] Each task has verification method
- [ ] "Done when" is binary (yes/no)
- [ ] Test can run independently
- [ ] No "looks good" criteria

### 4. Dependency Accuracy

- [ ] Blocking relationships correct
- [ ] Parallel groups identified
- [ ] No missing dependencies
- [ ] No circular dependencies

### 5. Plan Fidelity

- [ ] Every plan item has task(s)
- [ ] No orphaned tasks
- [ ] No scope creep
- [ ] Task count between 3 and 50

---

## Severity Classification

| Issue Type | Severity | Blocks? |
|------------|----------|---------|
| Missing required section | blocker | Yes |
| Vague/untestable criterion | blocker | Yes |
| Scope ambiguity | blocker | Yes |
| Implementation detail leaked | warning | No |
| Missing edge case coverage | warning | No |
| Style/formatting issue | suggestion | No |

---

## Usage by Phase Reviewer

When phase-reviewer validates artifact transitions, apply the matching checklist:

### prd.md → spec.md (brainstorm → specify)

1. Apply "PRD Quality Criteria" checklist
2. Focus on: Problem precision, Evidence standards, Scope discipline
3. Mark issues as blocker/warning/suggestion
4. Summarize: "Can specify phase proceed with this PRD?"

### spec.md → design.md (specify → design)

1. Apply "Spec Quality Criteria" checklist
2. Focus on: Problem precision, Success criteria, Acceptance criteria
3. Mark issues as blocker/warning/suggestion
4. Summarize: "Can design phase proceed with this spec?"

### design.md → plan.md (design → create-plan)

1. Apply "Design Quality Criteria" checklist
2. Focus on: Architecture clarity, Interface precision, Risk assessment
3. Mark issues as blocker/warning/suggestion
4. Summarize: "Can plan phase proceed with this design?"

### plan.md → tasks.md (create-plan → create-tasks)

1. Apply "Plan Quality Criteria" checklist
2. Focus on: Dependency accuracy, Design coverage, TDD compliance
3. Mark issues as blocker/warning/suggestion
4. Summarize: "Can tasks phase proceed with this plan?"

### tasks.md → implementation (create-tasks → implement)

1. Apply "Tasks Quality Criteria" checklist
2. Focus on: Task size, Executability, Testability
3. Mark issues as blocker/warning/suggestion
4. Summarize: "Can implementation proceed with these tasks?"

---

## Quick Reference

**PRD must answer:** What problem? Who has it? Why solve it now? What's in/out?

**Spec must answer:** What exactly? How do we know it's done? What's the scope?

**Design must answer:** What components? How do they interact? What are the contracts?

**Plan must answer:** What order? What dependencies? How to verify each step?

**Tasks must answer:** What specific action? In which file? How to verify done?

**All must avoid:** False certainty, scope creep, implementation details (except design/tasks).
