# Superpowers Patterns Integration - Design

## Overview

Incorporate battle-tested patterns from [obra/superpowers](https://github.com/obra/superpowers) into our skill/agent collection, focusing on subagent orchestration, verification discipline, and foundational development practices.

## Source Analysis

Superpowers provides proven patterns for:
- **Subagent orchestration** - 3-agent workflow per task (implementer → spec reviewer → quality reviewer)
- **Verification discipline** - Evidence before claims, no false completion
- **TDD enforcement** - Rigorous test-driven development with rationalization prevention
- **Systematic debugging** - Root cause investigation before fixes
- **Skill authoring** - TDD approach applied to documentation

## Changes

### New Skills (9)

| Skill | Purpose | Dependencies |
|-------|---------|--------------|
| `test-driven-development` | Core TDD discipline with RED-GREEN-REFACTOR | None (foundational) |
| `systematic-debugging` | Root cause investigation methodology | TDD |
| `verification-before-completion` | Evidence before claims discipline | None (foundational) |
| `subagent-driven-development` | 3-agent workflow per task | TDD, verification, agents |
| `dispatching-parallel-agents` | Parallel investigation pattern | None |
| `writing-skills` | TDD for skill authoring | TDD |
| `using-git-worktrees` | Isolated workspace creation | None |
| `finishing-branch` | Branch completion (merge/PR/discard) | verification, worktrees |

### Enhanced Skills (2)

| Skill | Enhancement |
|-------|-------------|
| `brainstorming` | Add incremental presentation, YAGNI emphasis |
| `implementing` | Reference subagent-driven-development |

### New Agents (3)

| Agent | Purpose |
|-------|---------|
| `implementer.md` | Task implementation with self-review |
| `spec-reviewer.md` | Verify implementation matches spec |
| `code-quality-reviewer.md` | Verify implementation quality |

### Agent Restructure

Flatten `agents/` directory - remove `workers/` and `specialists/` subdirectories:

**Before:**
```
agents/
├── workers/
│   ├── generic-worker.md
│   └── investigation-agent.md
└── specialists/
    └── quality-reviewer.md
```

**After:**
```
agents/
├── generic-worker.md
├── investigation-agent.md
├── quality-reviewer.md
├── implementer.md          (new)
├── spec-reviewer.md        (new)
└── code-quality-reviewer.md (new)
```

## Skill Specifications

### test-driven-development/SKILL.md

**Description:** Use when implementing any feature or bugfix, before writing implementation code

**Core content:**
- Iron Law: No production code without failing test first
- RED-GREEN-REFACTOR cycle with flowchart
- Rationalization prevention table
- Red flags list
- Verification checklist

### systematic-debugging/SKILL.md

**Description:** Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes

**Core content:**
- Four phases: Root Cause → Pattern Analysis → Hypothesis → Implementation
- Iron Law: No fixes without root cause investigation
- 3-fix limit before questioning architecture
- Rationalization prevention table

### verification-before-completion/SKILL.md

**Description:** Use when about to claim work is complete, fixed, or passing

**Core content:**
- Iron Law: No completion claims without fresh verification evidence
- Gate function (identify → run → read → verify → claim)
- Red flags list
- Rationalization prevention table

### subagent-driven-development/SKILL.md

**Description:** Use when executing implementation plans with independent tasks in the current session

**Core content:**
- 3-subagent workflow flowchart
- References to agents: implementer, spec-reviewer, code-quality-reviewer
- Two-stage review gate (spec compliance THEN quality)
- Red flags and integration points

### dispatching-parallel-agents/SKILL.md

**Description:** Use when facing 2+ independent tasks that can be worked on without shared state

**Core content:**
- When to use flowchart
- Agent prompt structure template
- Common mistakes
- Verification after agents return

### writing-skills/SKILL.md

**Description:** Use when creating new skills, editing existing skills, or verifying skills work

**Core content:**
- TDD mapping for skills
- Skill types (technique, pattern, reference)
- SKILL.md structure
- CSO (Claude Search Optimization)
- Testing methodology

### using-git-worktrees/SKILL.md

**Description:** Use when starting feature work that needs isolation from current workspace

**Core content:**
- Worktree creation commands
- Directory selection
- Safety verification
- Integration with finishing-branch

### finishing-branch/SKILL.md

**Description:** Use when implementation is complete and you need to decide how to integrate

**Core content:**
- Verify tests first
- Present 4 options (merge/PR/keep/discard)
- Execute choice with specific commands
- Worktree cleanup

## Agent Specifications

### implementer.md

**Description:** Implementation agent for task execution with self-review

**Core content:**
- Ask questions before starting
- Implement → Test → Verify → Commit → Self-review
- Self-review checklist (completeness, quality, discipline, testing)
- Report format

### spec-reviewer.md

**Description:** Verify implementation matches specification exactly

**Core content:**
- Do NOT trust implementer report
- Check for missing requirements
- Check for extra/unneeded work
- Check for misunderstandings
- Output: Spec compliant or issues list with file:line

### code-quality-reviewer.md

**Description:** Verify implementation quality after spec compliance passes

**Core content:**
- Code quality assessment
- Architecture and design review
- Issue categorization (Critical/Important/Minor)
- Strengths and recommendations

## Implementation Order

1. **Foundational skills first** (no dependencies):
   - test-driven-development
   - verification-before-completion
   - systematic-debugging

2. **Agents** (needed by orchestration skills):
   - Restructure agents directory (flatten)
   - implementer.md
   - spec-reviewer.md
   - code-quality-reviewer.md

3. **Orchestration skills** (depend on agents):
   - subagent-driven-development
   - dispatching-parallel-agents

4. **Workflow skills**:
   - using-git-worktrees
   - finishing-branch
   - writing-skills

5. **Enhancements**:
   - brainstorming (enhance)
   - implementing (update refs)

## Validation

After implementation:
1. Run `./validate.sh` - all skills pass validation
2. Each skill has proper frontmatter (name, description)
3. Descriptions follow "Use when..." pattern
4. No broken cross-references
