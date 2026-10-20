# Brainstorm: Harden the E2E Brainstorm Workflow

*Source: Backlog #00001*
*Started: 2026-01-31*

## Problem Statement

The brainstorm workflow (and downstream phases) lacks strict enforcement. Steps can be arbitrarily skipped by the agent, especially when starting from brainstorm through the full workflow. This unpredictability reduces trust in the plugin—users can't rely on consistent behavior.

**Core issues:**
1. **Reliability** — Steps get skipped or executed out of order
2. **Completeness** — Not all required steps are enforced
3. **User experience** — Inconsistent behavior is confusing

**Observed failure:** Agent went straight from brainstorming to implementation, skipping:
- Promotion question
- Mode selection
- Specify phase
- Design phase
- Planning phase
- Task creation phase

User had no choice—complete loss of control over the workflow.

## Goals

1. **Entry gate (HARD):** Brainstorm cannot lead to implementation directly—must go through feature creation first
2. **Exit gate (HARD):** Every feature must complete via `/finish` (cleanup, merge, retro)
3. **Middle phases (FLEXIBLE):** After feature creation, phases (specify, design, plan, tasks, implement, verify) can be skipped if sensible

This mirrors how teams manage resources: a feature request must be established before work begins, and work must be properly closed out.

## Approaches Considered

### The Core Problem

Brainstorm skill must have exactly TWO exit paths:
1. **Promote** → User chooses "yes" → invoke `/iflow:create-feature`
2. **Save** → User chooses "no" → save file, END session

The agent bypassed this by jumping to implementation. The enforcement must be ON the brainstorm skill itself.

### Approach A: Stronger Skill Language

Rewrite the skill with explicit "MUST" and "MUST NOT" language:
- "You MUST ask the promotion question using AskUserQuestion"
- "You MUST NOT proceed to any phase other than /create-feature"
- "You MUST NOT write code or implement anything"

**Pros:** Simple, no tooling changes
**Cons:** LLM can still ignore instructions

### Approach B: Forced AskUserQuestion Gate

Restructure skill to REQUIRE using the AskUserQuestion tool at the end:
- Skill explicitly says: "Use AskUserQuestion with exactly these options"
- Options: "Create feature" or "Save for later"
- No other path is described in the skill

**Pros:** Creates a hard interaction point, user always gets the choice
**Cons:** LLM might still skip the tool call

### Approach C: Completion Marker + State Check

1. Brainstorm writes a status marker: `## Status: AWAITING_DECISION`
2. When user responds, update to: `## Status: SAVED` or `## Status: PROMOTED`
3. Other skills (implement) check for active feature before proceeding

**Pros:** Creates audit trail, other skills can validate
**Cons:** Adds complexity, relies on other skills checking

## Chosen Direction

**Approach B: Forced AskUserQuestion Gate** with explicit prohibitions + **subagent verification**.

### Verification Step (REQUIRED)

Before the promotion question, invoke a `brainstorm-reviewer` subagent:
- Fresh perspective (no context from creating the brainstorm)
- Uses generic reviewer pattern for now
- Reports issues by severity (blocker, warning, note)
- Only proceed to promotion question if no blockers

### Closing Behavior (REQUIRED)

Content is automatically saved to the scratch file throughout the session.

After completing the brainstorm content, the agent MUST:

1. Use `AskUserQuestion` with EXACTLY these options:
   - **"Yes"** — Promote to feature and continue workflow
   - **"No"** — End session

   Question: "Turn this into a feature?"

2. Based on response:
   - **"Yes"** → Invoke `/iflow:create-feature` with the brainstorm content
   - **"No"** → Output "Brainstorm saved to {filepath}." and STOP

### PROHIBITED Actions

- Do NOT proceed to specify, design, plan, or implement
- Do NOT write any code
- Do NOT create feature folders directly
- Do NOT continue after user says "No"

## Open Questions

1. Should `/finish` enforcement be part of this feature, or a separate hardening effort?

## Next Steps

Implementation requires:
1. Create `brainstorm-reviewer` agent ✓ (done: `plugins/iflow/agents/brainstorm-reviewer.md`)
2. Update `brainstorming` skill to:
   - Add verification step using `brainstorm-reviewer` subagent
   - Add hardened closing behavior with explicit prohibitions
   - Use `AskUserQuestion` for promotion decision

Ready for `/iflow:create-feature` to define requirements and implement.
