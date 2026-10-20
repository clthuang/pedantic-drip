# Brainstorm: Workflow Orchestration & Iterative Review

## Original Issues

User tested the e2e workflow and observed:
1. **Stage-to-stage transitions not enforced** - design suggested create-tasks instead of create-plan
2. **Reviewer subagent not providing iterative feedback** - wanted executor-reviewer cycles before presenting to human
3. **Worktrees not properly managed** - not being respected during workflow
4. **Completed features not tracked** - no clear status management

## Decisions Made

### Gap 1: Orchestrator Implementation
**Decision:** Skill + Hook hybrid approach
- `workflow-state` skill defines state schema, validation, and update patterns
- SessionStart hook shows context and warns about issues
- Commands follow skill instructions inline
- No agent spawn overhead
- Can evolve to agent later if needed

### Gap 2: Reviewer-Executor Loop Mechanics
**Decision:** Subagent review approach
- Spawn a dedicated reviewer agent each iteration
- Reviewer is read-only, provides structured feedback
- Main agent revises based on feedback
- Repeat until approved or max iterations
- Genuine fresh perspective worth the overhead

### Gap 3: Max Iterations
**Decision:** Mode-based iterations
| Mode | Max Iterations |
|------|----------------|
| Hotfix | 1 |
| Quick | 2 |
| Standard | 3 |
| Full | 5 |

At max iterations: present result with remaining concerns, let user decide

### Gap 4: Worktree Checks
**Decision:**
- Warn once per session when outside worktree, don't nag repeatedly
- Each phase command checks cwd against worktree
- No checks when `worktree: null` (Hotfix mode)

### Gap 5: Transition Strictness
**Decision:** Hard + soft prerequisites
- **Hard (blocked):** spec.md required before /implement, plan.md required before /create-tasks
- **Soft (warn):** Other transitions warn but allow with acknowledgment

### Gap 6: Status State Machine
**Decision:**
- States: `active`, `completed`, `abandoned`
- Transitions: create → active → completed/abandoned
- Reopen allowed (completed/abandoned → active) via explicit command
- No `paused` for v1

### Gap 7: Artifact Versioning
**Decision:** Rely on git for artifact versioning. No explicit versioning system.

### Gap 8: Reviewer Context
**Decision:** Chain validation principle

**Brainstorm Reviewer:**
- Most holistic - original request + all exploration
- Question: "Did we capture the user's true intent?"

**Chain Reviewers (specify → implement):**
- Context: Previous stage output + current output + next stage expectations
- Question: "Is current output self-sufficient for next stage?"
- Principle: Each phase output must contain everything the next phase needs

**Final Feature Reviewer:**
- Context: Original spec + final implementation
- Question: "Does implementation deliver what was specified?"
- Completes the circle back to requirements

### Gap 9: Review History Storage
**Decision:** Tiered storage with cleanup
- **Access:** Natural language query
- **Storage:**
  - `.meta.json`: Summary only (iteration count, final notes)
  - `.review-history.md`: Full iteration details during active development
- **Cleanup:** `/finish` deletes `.review-history.md`

### Gap 10: Testing Strategy
**Decision:** Test scenarios become acceptance criteria

## Reviewer Agent Persona (Hardened)

The reviewer's job is to **ensure quality of what's specified**, NOT to expand scope.

### What the Reviewer SHOULD Do
- Check for completeness within stated scope
- Identify ambiguities and unclear requirements
- Flag missing error handling for described features
- Point out inconsistencies between sections
- Verify acceptance criteria are testable

### What the Reviewer MUST NOT Do
- Suggest new features ("you should also add OAuth")
- Expand requirements ("consider adding rate limiting")
- Add nice-to-haves ("what about dark mode?")
- Question product decisions
- Recommend architecture changes outside scope

### Reviewer Mantra
"Is this artifact clear and complete FOR WHAT IT CLAIMS TO DO?"
NOT "What else could this artifact include?"

## Architecture Sketch

```
┌──────────────────────────────────────────────────────────────────┐
│                    Workflow State Skill                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ workflow.yaml: brainstorm→specify→design→plan→tasks→impl   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ .meta.json: status, currentPhase, phases{}, worktree        │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│                        Phase Command                              │
│  1. Query workflow-state skill: Can I run? → Advisory warnings    │
│  2. Check for partial: Ask user (continue/fresh/review)           │
│  3. Execute with reviewer loop (max iterations per mode)          │
│  4. Report completion, update state                               │
└───────────────────────────────────────────────────────────────────┘

Validation Chain:
brainstorm → [spec sufficient?] → specify → [design sufficient?] → design
    → [plan sufficient?] → plan → [tasks sufficient?] → tasks → implement
                                                                    │
    ┌───────────────────────────────────────────────────────────────┘
    │
    └──→ FINAL: Does implementation match original spec? (closes loop)
```

## Test Scenarios (Acceptance Criteria)

### Happy Path
1. Full workflow in order - all phases complete correctly
2. Hotfix mode - minimal verification, no worktree
3. Full mode - 5 iterations, all verifications

### Transitions
4. /design without /specify - soft warning, can proceed
5. /implement without spec.md - hard block
6. /create-tasks without plan.md - hard block
7. Skip phases intentionally - warnings acknowledged

### Iterations
8. Reviewer approves iteration 1 - completes immediately
9. Reviewer never approves - presents with warnings at max
10. Reviewer scope creep attempt - hardened persona prevents

### Worktree
11. Session in wrong directory - SessionStart warns once
12. Command outside worktree - warns, proceeds after ack
13. Hotfix (no worktree) - no checks

### State
14. Interrupt mid-phase, resume - detects partial, asks
15. /finish with merge - status → completed
16. /finish with discard - status → abandoned
17. Reopen completed - status → active

### Chain Validation
18. Spec missing info for design - reviewer catches
19. Design missing info for plan - reviewer catches
20. Implementation misses spec requirement - final reviewer catches
