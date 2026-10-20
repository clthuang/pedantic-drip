# Brainstorm: Executor-Reviewer Loop Implementation

**Date:** 2026-01-30
**Trigger:** Investigation found feature 003's executor-reviewer cycle is specified but not implemented

## The Gap

Feature 003 (workflow-orchestration) defined:
- Architecture for executor-reviewer iteration cycle
- Chain reviewer and final reviewer agents
- Iteration limits per mode (Hotfix:1, Quick:2, Standard:3, Full:5)
- State tracking via `.meta.json` and `.review-history.md`

**But commands only have pseudocode, not execution mechanics.**

## What Needs Implementation

### 1. Subagent Dispatch Mechanism

Commands say "spawn chain-reviewer" but don't specify:
- Which tool to use (Task tool with subagent_type?)
- How to pass context (previous artifact, current artifact, expectations)
- How to parse reviewer output (approved/needs-revision)

### 2. Revision Loop Logic

No instructions for:
- Re-executing the phase skill with feedback
- Tracking iteration count
- Deciding when to stop (approved OR max iterations)

### 3. Feedback Integration

Missing:
- How to capture reviewer feedback
- How to pass it back to executor
- How to ensure feedback is addressed

### 4. State Updates During Loop

Not implemented:
- Appending to `.review-history.md` after each iteration
- Updating `.meta.json` iteration count
- Recording unresolved concerns if max iterations hit

## Design Questions

### Q1: How should reviewer be invoked?

**Option A: Task tool with agent type**
```
Use Task tool with subagent_type="chain-reviewer"
Pass: previous artifact content, current artifact content, expectations
```

**Option B: Inline review (no subagent)**
```
Claude reviews directly using chain-reviewer prompt as guidance
No separate agent spawn
```

**Option C: Skill-based review**
```
Create reviewing skill that wraps the review logic
Commands call /review instead of spawning agent
```

### Q2: How should the loop be structured?

**Option A: Command handles loop**
- Command file includes full loop logic
- Tracks iterations, spawns reviewer, handles revision

**Option B: Separate orchestration skill**
- Create `executing-with-review` skill
- Commands call this skill which manages the loop

**Option C: Hook-based**
- PostToolUse hook intercepts phase completion
- Triggers review automatically

### Q3: How should feedback drive revision?

**Option A: Full re-execution**
- Run entire phase skill again with feedback context
- May produce different artifact

**Option B: Targeted edits**
- Reviewer specifies what to change
- Only those parts are revised

**Option C: Diff-based**
- Reviewer marks issues inline
- Executor addresses marked issues only

## Constraints

1. Must work within Claude Code's tool system
2. Should not require external orchestration
3. Must be mode-aware (iteration limits)
4. Should be observable (track in .review-history.md)
5. Must not break existing commands if reviewer disabled

## Proposed Approach

**Minimal viable implementation:**

1. **Add execution instructions to commands**
   - Translate pseudocode to actual Task tool calls
   - Define input/output format for reviewer

2. **Create simple loop in skill**
   - `executing-with-review` skill wraps phase execution
   - Handles iteration counting and termination

3. **Use existing agents as-is**
   - chain-reviewer.md already has good prompt
   - Just need to invoke it properly

4. **State tracking via command**
   - Commands update .review-history.md
   - Commands update .meta.json iterations

## Files to Modify

| File | Change |
|------|--------|
| `commands/specify.md` | Add actual execution instructions |
| `commands/design.md` | Add actual execution instructions |
| `commands/create-plan.md` | Add actual execution instructions |
| `commands/create-tasks.md` | Add actual execution instructions |
| `commands/implement.md` | Add actual execution instructions |
| `skills/executing-with-review/SKILL.md` | **Create** - Loop orchestration |
| `agents/chain-reviewer.md` | May need input/output format clarification |

## Success Criteria

- [ ] Running `/specify` invokes chain-reviewer after producing spec.md
- [ ] If reviewer finds issues, revision happens automatically
- [ ] Iteration count respects mode limits
- [ ] `.review-history.md` captures each iteration
- [ ] Loop terminates correctly (approval or max iterations)

## Decisions Made

1. **Invocation:** Task tool with agent - spawn chain-reviewer as subagent
2. **Loop structure:** Command handles loop - each command includes full loop logic inline
3. **Skip option:** Yes with flag - allow `--no-review` to skip

## Open Questions

1. How verbose should review feedback be in `.review-history.md`?
2. Should failed reviews (max iterations) block progression or just warn?
