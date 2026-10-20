# Specification: Enhanced Brainstorm-to-PRD Workflow

## Problem Statement

The brainstorm phase produces loose notes and jumps directly to specification, missing a formalization step that resolves ambiguities, verifies technical claims, and produces evidence-backed PRDs.

## Success Criteria

- [ ] Brainstorm command produces a PRD file (not brainstorm.md)
- [ ] PRD includes research findings from subagents (internet, codebase, skills)
- [ ] PRD includes critical review feedback and corrections
- [ ] All technical claims in PRD cite evidence or are flagged as assumptions
- [ ] User can choose to refine, promote to feature, or abandon after review

## Scope

### In Scope

- Modify brainstorming skill to implement 6-stage flow (clarify → research → draft → review → correct → decide)
- Create 4 new agents with corresponding skills:
  - `iflow:internet-researcher` — web research
  - `iflow:codebase-explorer` — codebase analysis
  - `iflow:skill-searcher` — find existing skills
  - `iflow:prd-reviewer` — critical review
- Define PRD document format with evidence requirements
- Define PRD quality criteria checklist

### Out of Scope

- Reworking/revising existing PRDs (future enhancement)
- Maximum review cycle limits (use single pass for now)

## Acceptance Criteria

### AC-1: Clarification Stage
- Given a user invokes `/iflow:brainstorm`
- When the topic is provided
- Then the system asks probing questions to resolve ambiguities before research

### AC-2: Research Stage
- Given clarification is complete
- When research subagents are invoked
- Then each returns findings with sources/references (or explicit "no findings")

### AC-3: PRD Draft
- Given research is complete
- When PRD is drafted
- Then each claim cites evidence type (research, codebase, user input, or "assumption")

### AC-4: Critical Review
- Given PRD draft is complete
- When reviewer agent is invoked
- Then it returns issues with severity, evidence, and suggested fixes

### AC-5: Auto-Correction
- Given review issues are returned
- When actionable issues exist
- Then corrections are applied with change notes before presenting to user

### AC-6: User Decision
- Given corrected PRD is presented
- When user is prompted
- Then options are: Refine further, Turn into feature, Abandon

### AC-7: Evidence Standards
- Given any technical capability claim in PRD
- When the claim is made
- Then it must include verification reference (file:line) or be marked "Assumption: needs verification"

## Dependencies

- Existing brainstorming skill at `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- Task tool for spawning subagents
- WebSearch/WebFetch tools for internet research
- Glob/Grep/Read tools for codebase exploration

## Open Questions

- None blocking — all resolved during brainstorm
