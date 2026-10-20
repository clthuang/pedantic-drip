# Specification: Harden Brainstorm Workflow

## Problem Statement

The brainstorming skill allows the agent to skip the promotion question and jump directly to implementation, removing user control over the workflow.

## Success Criteria

- [ ] Brainstorm always ends with a promotion question via `AskUserQuestion`
- [ ] Brainstorm invokes `brainstorm-reviewer` subagent before promotion question
- [ ] Brainstorm has exactly two exit paths: promote to feature OR save and stop
- [ ] Agent cannot proceed to implement/design/specify from brainstorm directly

## Scope

### In Scope

- Update `brainstorming` skill with hardened closing behavior
- Create `brainstorm-reviewer` agent (already done)
- Add explicit PROHIBITED section to skill

### Out of Scope

- `/finish` enforcement (separate hardening effort)
- Hardening other phase transitions
- Changes to reviewer agent behavior

## Acceptance Criteria

### Verification Before Promotion

- Given a completed brainstorm
- When the brainstorm content is finalized
- Then the agent invokes `brainstorm-reviewer` subagent to review the content

### Promotion Question Gate

- Given the reviewer returns no blockers
- When the agent completes brainstorming
- Then the agent MUST use `AskUserQuestion` with options "Yes" and "No" for "Turn this into a feature?"

### Promote Path

- Given the user answers "Yes" to promotion
- When the response is received
- Then the agent invokes `/iflow:create-feature` and stops brainstorming

### Save Path

- Given the user answers "No" to promotion
- When the response is received
- Then the agent outputs "Brainstorm saved to {filepath}." and STOPS (no further action)

### Prohibited Actions

- Given an active brainstorm session
- When the brainstorm skill is executing
- Then the agent MUST NOT: proceed to specify/design/plan/implement, write code, create feature folders directly, or continue after user says "No"

## Dependencies

- `brainstorm-reviewer` agent must exist (done: `plugins/iflow/agents/brainstorm-reviewer.md`)

## Open Questions

- None (deferred `/finish` enforcement to separate feature)
