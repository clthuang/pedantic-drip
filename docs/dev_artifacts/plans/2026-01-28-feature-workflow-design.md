# Feature Development Workflow Design

A structured workflow for Claude Code combining spec-kit's methodical documentation with superpowers' interactive approach.

---

## Philosophy

```
Everything is prompts.     Skills and agents are instructions Claude follows.
Files are truth.           Artifacts persist in files, not memory.
Claude is the engine.      Claude's judgment executes the workflow.
Humans unblock.            When automation fails, ask the human.
Use it to test it.         No test suites for prompts. Use → refine.
```

**Clarification on state:**
- *Artifacts* (specs, designs, plans) → Always in files
- *Execution tracking* (task progress) → Vibe-Kanban if available, else TodoWrite
- Files are source of truth for what was decided. Kanban/TodoWrite tracks what's in progress.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User                                      │
│                          │                                       │
│                    /command                                      │
│                          ↓                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     Claude                                 │  │
│  │  • Reads skill instructions                                │  │
│  │  • Reads feature state (files)                             │  │
│  │  • Follows guidelines                                      │  │
│  │  • Spawns agents when appropriate                          │  │
│  │  • Updates files to track progress                         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          │                                       │
│              ┌───────────┼───────────┐                          │
│              ↓           ↓           ↓                          │
│         [Files]     [Agents]     [MCP]                          │
│         state &     isolated     Vibe-Kanban                    │
│         docs        workers      (optional)                     │
└─────────────────────────────────────────────────────────────────┘
```

No routing layer. No orchestration service. Just Claude following well-written instructions.

---

## Workflow Phases

```
┌─────────────────────────────────────────────────────────────────┐
│                    SUGGESTED WORKFLOW                            │
│                                                                  │
│  brainstorm ──→ spec ──→ design ──→ plan ──→ tasks ──→ implement│
│       ↑          ↑         ↑          ↑         ↑                │
│       └──────────┴─────────┴──────────┴─────────┘                │
│                     (loop back anytime)                          │
└─────────────────────────────────────────────────────────────────┘
```

**Composable, not rigid.** Each phase is independent. Workflow suggests order, doesn't enforce. Loop back when needed.

### Phase Dependencies

When a phase is invoked without prerequisites:

```
/design without spec.md:
  → "No spec.md found. Options:"
  → "1. Run /spec first (recommended)"
  → "2. Describe requirements now and proceed"
  → User decides. Skill handles gracefully.

Principle: Never fail silently. Offer paths forward.
```

### Phase Specialists

| Phase | Focus | Cognitive Mode |
|-------|-------|----------------|
| brainstorm | Divergent thinking, options | Creative |
| spec | Precise requirements | Precision |
| design | Architecture, interfaces | Systems |
| plan | Dependencies, ordering | Sequencing |
| tasks | Actionable breakdown | Execution |
| implement | Code, tests | Craft |

Separation prevents: vague specs, premature implementation, missing dependencies.

---

## Workflow Modes

Adapt overhead to task size:

| Mode | Phases | Verification | Worktree | Use When |
|------|--------|--------------|----------|----------|
| Hotfix | implement only | None | No | Single file, obvious fix |
| Quick | spec → tasks → implement | After implement only | Optional | Small, clear requirements |
| Standard | All phases | Suggested after each | Recommended | Normal features |
| Full | All phases | Required before proceeding | Required | Large, risky changes |

**Auto-triage:** Claude suggests mode based on described scope. User confirms or overrides.

---

## File Structure

```
project/
├── docs/
│   ├── features/
│   │   └── {id}-{name}/
│   │       ├── brainstorm.md    # Ideation output
│   │       ├── spec.md          # Requirements & acceptance criteria
│   │       ├── design.md        # Architecture & interfaces
│   │       ├── plan.md          # Implementation approach
│   │       ├── tasks.md         # Task definitions (what to do)
│   │       └── retro.md         # Retrospective learnings
│   │
│   └── knowledge-bank/
│       ├── constitution.md      # Core principles
│       ├── patterns.md          # What works
│       ├── anti-patterns.md     # What to avoid
│       └── heuristics.md        # Decision guides
│
└── .claude/
    └── skills/                  # Project-specific skill overrides
```

**Feature ID format:** Sequential integer (1, 2, 3...). Next ID derived from highest existing folder number + 1. Example: `42-user-auth`.

**tasks.md contains:** Task definitions and descriptions. Execution status (in-progress, done) tracked in Vibe-Kanban or TodoWrite, not in this file.

---

## Commands

| Command | Purpose |
|---------|---------|
| /feature | Start feature (create worktree, folder, kanban card) |
| /brainstorm | Ideation phase |
| /spec | Specification phase |
| /design | Architecture phase |
| /plan | Implementation planning |
| /tasks | Task breakdown |
| /implement | Execute implementation |
| /verify | Run phase-appropriate verification |
| /status | Current feature state |
| /retro | Capture learnings |
| /finish | Complete feature (merge, cleanup) |
| /features | List all active features |

---

## Verification Gates

After each phase, verification is **suggested but not enforced** (except in Full mode).

**Purpose:**
- Measure twice, cut once
- Fresh agent = no context bias
- Catches tunnel vision
- Research-backed: repeated evaluation improves quality

**Verification by Mode:**
- Hotfix: None
- Quick: After implementation only
- Standard: Suggested after each phase (user can skip)
- Full: Required before proceeding to next phase

**Verifier Principles:**
- KISS and YAGNI prominent in every check
- Report by severity (🔴 blocker, 🟡 warning, 🟢 note)
- Propose fixes with tradeoffs
- Human decides whether to proceed or skip

**Circuit Breaker:** After 3 failures same phase, stop and surface to human for decision.

---

## Agents

### When to Spawn Agents

```
1. For investigation before implementing:
   → Spawn investigation-agent (read-only, gathers context)

2. For implementation:
   - All files in one domain? → Specialist agent
   - Mixed domains? → Handle directly
   - Unsure? → Ask user
```

### Available Agents

**Implementation Agents:**

| Agent | Purpose |
|-------|---------|
| investigation-agent | Read-only research before implementing |
| frontend-specialist | Deep UI work (React, CSS, components) |
| api-specialist | API implementation |
| database-specialist | Migrations, queries |
| generic-worker | General implementation |

**Verifier Agents:**

| Agent | Purpose | When |
|-------|---------|------|
| phase-verifiers | Check artifact quality | After brainstorm/spec/design/plan/tasks |
| quality-reviewer | Code quality, cleanup, readability, remove dead code | After implementation, before /finish |

**Note:** quality-reviewer is a verifier for code, not artifacts. Runs after implementation to ensure clean, maintainable code.

### Adapted Swarming

True parallel file editing not possible in Claude Code. Adapted strategies:

1. **Parallel Investigation** - Multiple read-only agents explore, single implementer synthesizes
2. **Partitioned Sub-Tasks** - Agents work on non-overlapping file scopes
3. **Serial Handoff** - Fresh agent takes over with context when stuck

---

## State Management

### What Goes Where

| State Type | Location | Notes |
|------------|----------|-------|
| Artifacts (spec, design, etc.) | Files in feature folder | Always. Source of truth for decisions. |
| Task definitions | tasks.md | What needs to be done |
| Execution progress | Vibe-Kanban or TodoWrite | What's in progress, what's done |
| Current phase | Derived from existing artifacts | If spec.md exists but not design.md → spec phase complete |

### Execution Tracking: Vibe-Kanban (Primary)

```yaml
when-available:
  - Visual board for progress
  - Tested agile workflow
  - Team visibility
  - WIP management
  - Real-time status
```

### Execution Tracking: TodoWrite (Fallback)

```yaml
when-not-available:
  - TodoWrite for task tracking
  - /status shows current state
  - Workflow continues normally
```

**Detection:** Check for Vibe-Kanban MCP on session start. Use if available, fallback to TodoWrite otherwise. Artifacts always written to files regardless.

---

## Feature Isolation: Git Worktrees

Each feature gets a separate working directory (for Standard/Full modes):

```bash
# Create feature
/feature "user authentication"
→ git worktree add ../project-42-auth feature/42-auth

# Work in isolation
cd ../project-42-auth

# Switch features
cd ../project-58-search

# Cleanup after merge
git worktree remove ../project-42-auth
```

**Benefits:** Clean separation, no branch detection logic, can work on multiple features.

**Worktree by Mode:**

| Mode | Worktree |
|------|----------|
| Hotfix | No - work directly in main repo |
| Quick | Optional - /feature asks user preference |
| Standard | Recommended - /feature creates by default |
| Full | Required - /feature always creates |

**Simple projects:** If worktrees feel like overkill, use Quick or Hotfix mode.

---

## Error Recovery

### Classification

| Category | Examples | Handling |
|----------|----------|----------|
| Transient | Network timeout, MCP hiccup | Auto-retry (max 3) |
| Recoverable | Verification fails, agent incomplete | Surface options to human |
| Environmental | Auth expired, disk full | Pause, explain fix, wait |
| Corruption | Partial write, state divergence | Surface, human reconciles |
| Fatal | Repo corrupted, folder deleted | Cannot auto-recover |
| Judgment | Ambiguous requirements, tradeoffs | Human decides |

### Recovery Ladder

```
Level 1: Auto-retry (transient issues)
    ↓ if fails
Level 2: Alternative approach (fresh agent, simplified task)
    ↓ if fails
Level 3: Surface to human with options
    ↓ always succeeds
Level 4: Human takes action or makes call
    → Unblocked
```

### Core Principle

```
When automated recovery fails, ASK THE HUMAN.

This is not failure. This is correct behavior.

Humans can:
- Make judgment calls machines can't
- Override rules when context demands
- Accept risk and proceed anyway
- Decide "good enough" vs "must fix"

Never spin endlessly. Never fail silently. Ask.
```

---

## Knowledge Bank & Retrospectives

### Constitution (constitution.md)

Core principles that govern all work:

```markdown
1. KISS - Simplest solution that works
2. YAGNI - Don't build what isn't needed
3. Delete > Deprecate - Remove unused code
4. Tests Guarantee Compatibility - Not backwards-compat hacks
5. Evidence Before Assertion - Verify, don't assume
```

### Retrospective Process

**Triggers:**
- `/finish` suggests running retro: "Feature complete. Capture learnings with /retro? (y/n)"
- `/retro` can be run anytime (not automatic, human chooses)

**Process:**
1. Gather data (verification failures, blockers, surprises)
2. Identify learnings (patterns, anti-patterns, heuristics)
3. Propose updates to knowledge bank
4. Human approves each proposed update
5. Update appropriate files (constitution.md, patterns.md, etc.)

---

## Scalability

### Organization

```
skills/
  workflow/     # Feature development phases
  practices/    # TDD, debugging, review
  domain/       # Frontend, API, etc.

agents/
  specialists/
  workers/
```

### Discovery

Claude matches user intent to skill descriptions. Investment: write excellent descriptions.

### Maintenance

- Quarterly: Human reviews, deletes unused
- On confusion: Improve descriptions
- Delete freely: Git preserves history

**No registry.yaml. No duplicate detection scripts. No deprecation workflows.**

---

## Versioning

**Skills and agents:** No version numbers. Git history is version history.

**Rollback:** `git checkout` or `git revert`.

**Project-specific versions:** Override in project's `.claude/skills/`.

**Plugins for distribution:** Use semver in plugin.json.

---

## Quality Assurance

```yaml
validate.sh:
  - Frontmatter parses
  - Required fields present
  - Run on commit

human-review:
  - Read before committing
  - "Is this clear?"

use-it:
  - The real test
  - Works? Done.
  - Doesn't work? Edit.

workflow-gates:
  - Verifiers catch bad output
  - Human reviews artifacts

no-formal-testing:
  - Can't unit test LLM instructions
  - Use the thing to test it
```

---

## Implementation Order

1. **File structure** - Create docs/features/, docs/knowledge-bank/
2. **Core commands** - /feature, /status, /finish
3. **Phase skills** - One at a time: brainstorm → spec → design → plan → tasks → implement
4. **Verification skills** - Phase verifiers + quality-reviewer
5. **Agent definitions** - Specialists + generic worker + investigation agent
6. **Retrospective** - /retro command and skill
7. **Kanban integration** - Vibe-Kanban MCP integration (optional enhancement)

---

## What This Design Does NOT Have

| Not Building | Why |
|--------------|-----|
| Routing layer | Claude's judgment + guidelines = sufficient |
| Calculated thresholds | Claude interprets, doesn't compute |
| Automatic phase transitions | Human approval at each gate |
| Inter-agent communication | Claude Code doesn't support it |
| Background orchestration | No persistent processes |
| Test suites for skills | Can't unit test prompts |
| Complex state management | Files for artifacts, Kanban/TodoWrite for execution |
| Version numbers for skills | Git is version control |
| Registry files | Skills are self-describing via frontmatter |

---

## Design Principles Summary

```
Composable > Rigid          Skills work independently, combine as needed
Files > Memory              Artifacts in files, any session can resume
Human Unblocks              When stuck, ask—don't spin
Use > Test                  Real usage is the only meaningful test
Simple > Clever             KISS, YAGNI, delete over deprecate
Verify Fresh                Fresh agent perspective catches bias
Git > Custom                Worktrees, history, rollback—already solved
Graceful Degradation        Kanban optional, workflow continues regardless
Suggest > Enforce           Verification suggested, human decides to skip or proceed
```

---

## References

- [Component Authoring Guide](../guides/component-authoring.md)
- [Superpowers](https://github.com/obra/superpowers) - Skill patterns
- [Spec-kit](https://github.com/github/spec-kit) - Documentation workflow
