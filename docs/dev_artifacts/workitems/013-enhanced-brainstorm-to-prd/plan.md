# Plan: Enhanced Brainstorm-to-PRD Workflow

## Implementation Order

### Phase 1: Foundation (Agents)
Create the 4 new agents with no dependencies.

1. **Internet Researcher Agent** — Web research subagent
   - Complexity: Simple
   - Files: `plugins/iflow-dev/agents/internet-researcher.md`

2. **Codebase Explorer Agent** — Codebase analysis subagent
   - Complexity: Simple
   - Files: `plugins/iflow-dev/agents/codebase-explorer.md`

3. **Skill Searcher Agent** — Find existing skills subagent
   - Complexity: Simple
   - Files: `plugins/iflow-dev/agents/skill-searcher.md`

4. **PRD Reviewer Agent** — Critical review subagent
   - Complexity: Medium (quality criteria checklist needs definition)
   - Files: `plugins/iflow-dev/agents/prd-reviewer.md`

### Phase 2: Core Implementation (Skill Modification)
Modify brainstorming skill to implement 6-stage flow.

1. **PRD Template** — Define the PRD document format
   - Depends on: None (can be done in parallel with Phase 1)
   - Complexity: Simple
   - Files: Embedded in brainstorming skill

2. **Quality Criteria Checklist** — Define what PRD reviewer evaluates
   - Depends on: PRD Reviewer Agent (Phase 1.4)
   - Complexity: Simple
   - Files: Embedded in PRD Reviewer Agent

3. **Brainstorming Skill - Stage 1 (Clarify)** — Probing questions stage
   - Depends on: None
   - Complexity: Simple (minor changes to existing clarification)
   - Files: `plugins/iflow-dev/skills/brainstorming/SKILL.md`

4. **Brainstorming Skill - Stage 2 (Research)** — Parallel subagent invocation
   - Depends on: All Phase 1 agents
   - Complexity: Medium (parallel Task tool invocation)
   - Files: `plugins/iflow-dev/skills/brainstorming/SKILL.md`

5. **Brainstorming Skill - Stage 3 (Draft PRD)** — Generate PRD from research
   - Depends on: PRD Template (Phase 2.1), Stage 2 (Phase 2.4)
   - Complexity: Medium (evidence citation format)
   - Files: `plugins/iflow-dev/skills/brainstorming/SKILL.md`

6. **Brainstorming Skill - Stage 4 (Review)** — Invoke PRD reviewer
   - Depends on: PRD Reviewer Agent (Phase 1.4), Stage 3 (Phase 2.5)
   - Complexity: Simple
   - Files: `plugins/iflow-dev/skills/brainstorming/SKILL.md`

7. **Brainstorming Skill - Stage 5 (Auto-Correct)** — Apply review fixes
   - Depends on: Stage 4 (Phase 2.6)
   - Complexity: Medium (parse issues, apply corrections)
   - Files: `plugins/iflow-dev/skills/brainstorming/SKILL.md`

8. **Brainstorming Skill - Stage 6 (User Decision)** — Refine/Promote/Abandon
   - Depends on: Stage 5 (Phase 2.7)
   - Complexity: Simple (existing promotion flow with modification)
   - Files: `plugins/iflow-dev/skills/brainstorming/SKILL.md`

### Phase 3: Integration
Final integration and cleanup.

1. **Output File Naming** — Change from `.md` to `.prd.md`
   - Depends on: All Phase 2 items
   - Complexity: Simple
   - Files: `plugins/iflow-dev/skills/brainstorming/SKILL.md`

2. **Error Handling** — Graceful degradation for unavailable tools/agents
   - Depends on: All Phase 2 items
   - Complexity: Simple
   - Files: `plugins/iflow-dev/skills/brainstorming/SKILL.md`

## Dependency Graph

```
Phase 1 (Parallel):
┌─────────────────────┬─────────────────────┬──────────────────┬─────────────────┐
│ internet-researcher │ codebase-explorer   │ skill-searcher   │ prd-reviewer    │
└─────────┬───────────┴──────────┬──────────┴────────┬─────────┴────────┬────────┘
          │                      │                   │                  │
          └──────────────────────┴───────────────────┴──────────────────┘
                                         │
Phase 2:                                 ▼
┌────────────────┐              ┌────────────────────┐
│ PRD Template   │──────────────│ Quality Criteria   │
└───────┬────────┘              └──────────┬─────────┘
        │                                  │
        │         ┌────────────────────────┘
        │         │
        ▼         ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│ Brainstorming Skill Stages:                                                   │
│                                                                               │
│ Stage 1 (Clarify) ──→ Stage 2 (Research) ──→ Stage 3 (Draft PRD)             │
│                                                      │                        │
│                           Stage 4 (Review) ←─────────┘                        │
│                                │                                              │
│                           Stage 5 (Auto-Correct)                              │
│                                │                                              │
│                           Stage 6 (User Decision)                             │
└───────────────────────────────────────────────────────────────────────────────┘
                                         │
Phase 3:                                 ▼
┌────────────────────┐     ┌────────────────────┐
│ Output File Naming │     │ Error Handling     │
└────────────────────┘     └────────────────────┘
```

## Risk Areas

- **Stage 2 (Research):** Parallel Task tool invocation — need to ensure all 3 subagents complete before proceeding
- **Stage 5 (Auto-Correct):** Parsing review issues and applying corrections — could be error-prone if issue format varies

## Testing Strategy

- Manual testing for each agent (invoke via Task tool, verify output format)
- End-to-end test: Run `/iflow:brainstorm` with a sample topic
- Error handling test: Disable WebSearch, verify graceful degradation

## Definition of Done

- [ ] All 4 agents created with correct interface
- [ ] Brainstorming skill modified with 6-stage flow
- [ ] PRD output format matches specification
- [ ] Evidence citations appear in PRD
- [ ] Review feedback is applied automatically
- [ ] User can choose Refine/Promote/Abandon
- [ ] Graceful degradation when tools unavailable
