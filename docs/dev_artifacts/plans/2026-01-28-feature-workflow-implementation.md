# Feature Development Workflow - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the feature development workflow system with skills, commands, agents, and knowledge bank.

**Architecture:** Composable skills and commands that guide Claude through feature development phases (brainstorm → spec → design → plan → tasks → implement). Files store artifacts, Vibe-Kanban/TodoWrite tracks execution. Git worktrees provide feature isolation.

**Tech Stack:** Markdown skills/commands, YAML frontmatter, Bash validation, Git worktrees

---

## Task 0: README.md - Design Principles & Quick Start

**Files:**
- Modify: `README.md`

**Step 1: Write the comprehensive README**

```markdown
# My AI Setup

> A structured feature development workflow for Claude Code.

**What this is:** Skills, commands, and agents that guide Claude through methodical feature development—from ideation to implementation—with verification gates and knowledge accumulation.

---

## Design Principles

| Principle | Meaning |
|-----------|---------|
| **Everything is prompts** | Skills and agents are just instructions Claude follows |
| **Files are truth** | Artifacts persist in files; any session can resume |
| **Humans unblock** | When stuck, Claude asks—never spins endlessly |
| **Use > Test** | Real usage is the only test; refine through use |
| **Composable > Rigid** | Phases work independently; combine as needed |
| **Suggest > Enforce** | Verification suggested, human decides |

---

## Quick Start

### 1. Start a Feature

```bash
/feature "add user authentication"
```

Claude will:
- Suggest a workflow mode (Hotfix/Quick/Standard/Full)
- Create feature folder at `docs/dev_artifacts/workitems/{id}-{name}/`
- Create git worktree (for Standard/Full modes)

### 2. Work Through Phases

```bash
/brainstorm    # Ideation, options exploration
/spec          # Requirements, acceptance criteria
/design        # Architecture, interfaces
/plan          # Implementation approach
/tasks         # Break into actionable items
/implement     # Execute the work
```

**Each phase:**
- Produces an artifact (brainstorm.md, spec.md, etc.)
- Suggests verification (`/verify`)
- Suggests next phase

**Loop back anytime:** Phases are composable, not rigid.

### 3. Verify Work

```bash
/verify        # Run phase-appropriate verification
```

Verifiers check with fresh perspective:
- 🔴 Blockers must be fixed
- 🟡 Warnings should be addressed
- 🟢 Notes are suggestions

### 4. Check Status

```bash
/status        # Current feature state
/features      # All active features
```

### 5. Complete Feature

```bash
/finish        # Merge, cleanup worktree, suggest retro
/retro         # Capture learnings (optional)
```

---

## Workflow Modes

| Mode | Phases | Verification | Use When |
|------|--------|--------------|----------|
| **Hotfix** | implement only | None | Single file fix |
| **Quick** | spec → tasks → implement | After implement | Small feature |
| **Standard** | All phases | Suggested | Normal feature |
| **Full** | All phases | Required | Large/risky change |

---

## File Structure

```
project/
├── docs/
│   ├── features/
│   │   └── {id}-{name}/
│   │       ├── brainstorm.md    # Ideas, options
│   │       ├── spec.md          # Requirements
│   │       ├── design.md        # Architecture
│   │       ├── plan.md          # Approach
│   │       ├── tasks.md         # Task list
│   │       └── retro.md         # Learnings
│   │
│   └── knowledge-bank/
│       ├── constitution.md      # Core principles
│       ├── patterns.md          # What works
│       ├── anti-patterns.md     # What to avoid
│       └── heuristics.md        # Decision guides
```

---

## Commands Reference

| Command | Purpose | Output |
|---------|---------|--------|
| `/feature` | Start new feature | Folder, worktree, mode selection |
| `/brainstorm` | Ideation phase | brainstorm.md |
| `/spec` | Specification | spec.md |
| `/design` | Architecture | design.md |
| `/plan` | Planning | plan.md |
| `/tasks` | Task breakdown | tasks.md |
| `/implement` | Execute work | Code changes |
| `/verify` | Quality check | Issue report |
| `/status` | Current state | Status summary |
| `/features` | List all features | Feature list |
| `/finish` | Complete feature | Merge, cleanup |
| `/retro` | Capture learnings | retro.md, knowledge-bank updates |

---

## Agents

**Implementation:**
- `investigation-agent` — Read-only research
- `frontend-specialist` — React, CSS, components
- `api-specialist` — API implementation
- `database-specialist` — Migrations, queries
- `generic-worker` — General implementation

**Verification:**
- `phase-verifiers` — Check artifact quality
- `quality-reviewer` — Code quality, cleanup

---

## Knowledge Bank

Learnings accumulate in `docs/dev_artifacts/knowledge-bank/`:

- **constitution.md** — Core principles (KISS, YAGNI, etc.)
- **patterns.md** — Approaches that worked
- **anti-patterns.md** — Things to avoid
- **heuristics.md** — Decision guides

Updated via `/retro` after feature completion.

---

## Error Recovery

When something fails:

1. **Auto-retry** for transient issues
2. **Fresh approach** if retry fails
3. **Ask human** with clear options

**Principle:** Never spin endlessly. Never fail silently. Ask.

---

## For Developers

### Creating Components

See [Component Authoring Guide](docs/dev_guides/component-authoring.md).

**Skills:** `skills/{name}/SKILL.md` — Instructions Claude follows
**Agents:** `agents/{name}.md` — Isolated workers with specific focus
**Commands:** `commands/{name}.md` — User-invocable entry points

### Validation

```bash
./validate.sh    # Check all components
```

### Contributing

1. Fork the repository
2. Create feature branch
3. Run `./validate.sh`
4. Submit PR

---

## Architecture

```
User → /command → Claude reads skill → Follows instructions
                                    → Spawns agents if needed
                                    → Updates files
                                    → Uses Vibe-Kanban/TodoWrite for tracking
```

No routing layer. No orchestration. Just well-written prompts.

---

## References

- [Feature Workflow Design](docs/plans/2026-01-28-feature-workflow-design.md)
- [Component Authoring Guide](docs/dev_guides/component-authoring.md)
- [Superpowers](https://github.com/obra/superpowers)
- [Spec-kit](https://github.com/github/spec-kit)
```

**Step 2: Verify README renders correctly**

Open in preview or check formatting visually.

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README with design principles and quick start guide"
```

---

## Task 1: Create File Structure

**Files:**
- Create: `docs/dev_artifacts/workitems/.gitkeep`
- Create: `docs/dev_artifacts/knowledge-bank/constitution.md`
- Create: `docs/dev_artifacts/knowledge-bank/patterns.md`
- Create: `docs/dev_artifacts/knowledge-bank/anti-patterns.md`
- Create: `docs/dev_artifacts/knowledge-bank/heuristics.md`
- Create: `skills/.gitkeep`
- Create: `agents/.gitkeep`
- Create: `commands/.gitkeep`

**Step 1: Create directories and placeholder files**

```bash
mkdir -p docs/features docs/knowledge-bank skills/workflow skills/verification agents/specialists agents/workers commands
touch docs/features/.gitkeep skills/.gitkeep agents/.gitkeep commands/.gitkeep
```

**Step 2: Create constitution.md**

```markdown
# Engineering Constitution

Core principles governing all work. Updated through retrospectives.

---

## Immutable Principles

### 1. KISS — Keep It Simple, Stupid
The simplest solution that works is the best solution.

### 2. YAGNI — You Ain't Gonna Need It
Don't build what isn't needed. Speculation is waste.

### 3. Delete > Deprecate
Remove unused code. Don't preserve dead paths.

### 4. Tests Guarantee Compatibility
Not backwards-compat hacks. Tests verify behavior.

### 5. Evidence Before Assertion
Verify, don't assume. Run the test. Check the output.

---

## Learned Heuristics

*Added through retrospectives. Initially empty.*

<!-- Example format:
### From Feature #42: User Auth
- Session tokens over JWTs for simple auth (less complexity)
- Always validate on backend even if frontend validates
-->
```

**Step 3: Create patterns.md**

```markdown
# Patterns

Approaches that have worked well. Updated through retrospectives.

---

## Development Patterns

*Added through retrospectives. Initially empty.*

<!-- Example format:
### Pattern: Early Interface Definition
Define interfaces before implementation. Enables parallel work.
- Used in: Feature #42
- Benefit: Reduced integration issues by 50%
-->
```

**Step 4: Create anti-patterns.md**

```markdown
# Anti-Patterns

Things to avoid. Updated through retrospectives.

---

## Known Anti-Patterns

*Added through retrospectives. Initially empty.*

<!-- Example format:
### Anti-Pattern: Premature Optimization
Optimizing before measuring actual performance.
- Observed in: Feature #35
- Cost: 2 days wasted on unnecessary caching
- Instead: Measure first, optimize bottlenecks only
-->
```

**Step 5: Create heuristics.md**

```markdown
# Heuristics

Decision guides for common situations. Updated through retrospectives.

---

## Decision Heuristics

*Added through retrospectives. Initially empty.*

<!-- Example format:
### When to Create a New Service
Create a new service when:
- Functionality is used by 3+ other components
- Has distinct lifecycle from parent
- Needs independent scaling

Otherwise: Keep it as a module within existing service.
-->
```

**Step 6: Commit**

```bash
git add docs/features docs/knowledge-bank skills agents commands
git commit -m "feat: create file structure for workflow system"
```

---

## Task 2: /feature Command

**Files:**
- Create: `commands/feature.md`

**Step 1: Write the command**

```markdown
---
description: Start a new feature with folder structure and optional worktree
argument-hint: <feature-description>
---

# /feature Command

Start a new feature development workflow.

## Gather Information

1. **Get feature description** from argument or ask user
2. **Determine feature ID**: Find highest number in `docs/dev_artifacts/workitems/` and add 1
3. **Create slug** from description (lowercase, hyphens, max 30 chars)

## Suggest Workflow Mode

Based on described scope, suggest a mode:

| Scope | Suggested Mode |
|-------|----------------|
| "fix typo", "quick fix", single file | Hotfix |
| "add button", "small feature", clear scope | Quick |
| Most features | Standard |
| "rewrite", "refactor system", "breaking change" | Full |

Present to user:
```
Feature: {id}-{slug}
Suggested mode: {mode}

Modes:
1. Hotfix — implement only, no worktree
2. Quick — spec → tasks → implement, optional worktree
3. Standard — all phases, recommended worktree
4. Full — all phases, required worktree, required verification

Choose mode [1-4] or press Enter for {suggested}:
```

## Create Feature

### For Hotfix Mode
- Create folder: `docs/dev_artifacts/workitems/{id}-{slug}/`
- No worktree
- Inform: "Hotfix mode. Run /implement when ready."

### For Quick Mode
- Create folder: `docs/dev_artifacts/workitems/{id}-{slug}/`
- Ask: "Create worktree? (y/n)"
- If yes: `git worktree add ../{project}-{id}-{slug} -b feature/{id}-{slug}`
- Inform: "Quick mode. Run /spec to start."

### For Standard/Full Mode
- Create folder: `docs/dev_artifacts/workitems/{id}-{slug}/`
- Create worktree: `git worktree add ../{project}-{id}-{slug} -b feature/{id}-{slug}`
- Inform: "Created worktree at ../{project}-{id}-{slug}"
- Inform: "Standard mode. Run /brainstorm to start."

## State Tracking

If Vibe-Kanban available:
- Create card with feature name
- Set status to "New"

Otherwise:
- Use TodoWrite to track feature

## Output

```
✓ Feature {id}-{slug} created
  Mode: {mode}
  Folder: docs/features/{id}-{slug}/
  Worktree: ../{project}-{id}-{slug} (if created)

  Next: Run /{next-phase} to begin
```
```

**Step 2: Verify YAML frontmatter parses**

Check that the `---` delimited YAML is valid.

**Step 3: Commit**

```bash
git add commands/feature.md
git commit -m "feat: add /feature command"
```

---

## Task 3: /status Command

**Files:**
- Create: `commands/status.md`

**Step 1: Write the command**

```markdown
---
description: Show current feature state and progress
argument-hint: [feature-id]
---

# /status Command

Display the current state of a feature.

## Determine Feature

1. If argument provided: Use that feature ID
2. If in worktree: Extract feature ID from branch name
3. Otherwise: List recent features and ask

## Gather State

Read `docs/dev_artifacts/workitems/{id}-{slug}/`:

| File | Exists? | Phase Status |
|------|---------|--------------|
| brainstorm.md | ✓/✗ | Brainstorm complete/pending |
| spec.md | ✓/✗ | Spec complete/pending |
| design.md | ✓/✗ | Design complete/pending |
| plan.md | ✓/✗ | Plan complete/pending |
| tasks.md | ✓/✗ | Tasks complete/pending |

Current phase = first missing artifact (or "implement" if all exist)

## Check Execution Progress

If Vibe-Kanban available:
- Get card status
- Get task completion counts

If TodoWrite:
- Check task list status

## Display Status

```
Feature: {id}-{slug}
Mode: {mode}
Phase: {current-phase}

Artifacts:
  ✓ brainstorm.md
  ✓ spec.md
  ○ design.md (current)
  ○ plan.md
  ○ tasks.md

Progress: {completed}/{total} tasks (if in implement phase)

Next: Run /design to continue
```

## If No Feature Active

```
No active feature detected.

Recent features:
  42-user-auth (design phase)
  41-search (complete)

Run /feature to start a new feature
or /status {id} to check a specific feature
```
```

**Step 2: Commit**

```bash
git add commands/status.md
git commit -m "feat: add /status command"
```

---

## Task 4: /finish Command

**Files:**
- Create: `commands/finish.md`

**Step 1: Write the command**

```markdown
---
description: Complete a feature - merge, cleanup worktree, suggest retro
argument-hint: [feature-id]
---

# /finish Command

Complete a feature and clean up.

## Determine Feature

Same logic as /status command.

## Pre-Completion Checks

1. **Check for uncommitted changes**
   - If found: "Uncommitted changes detected. Commit or stash first."

2. **Check tasks completion** (if tasks.md exists)
   - If incomplete tasks: "Warning: {n} tasks still incomplete. Continue? (y/n)"

3. **Suggest quality review** (for Standard/Full modes)
   - "Run quality review before completing? (y/n)"
   - If yes: Spawn quality-reviewer agent

## Completion Options

```
Feature {id}-{slug} ready to complete.

How would you like to merge?
1. Create PR (recommended for team projects)
2. Merge to main locally
3. Keep branch (don't merge yet)
```

### Option 1: Create PR

```bash
git push -u origin feature/{id}-{slug}
gh pr create --title "Feature: {slug}" --body "..."
```

Inform: "PR created: {url}"

### Option 2: Merge Locally

```bash
git checkout main
git merge feature/{id}-{slug}
git push
```

### Option 3: Keep Branch

Inform: "Branch kept. Run /finish again when ready to merge."
Skip cleanup.

## Cleanup (for options 1 & 2)

If worktree exists:
```bash
cd {original-repo}
git worktree remove ../{project}-{id}-{slug}
git branch -d feature/{id}-{slug}  # after merge
```

## Update State

If Vibe-Kanban:
- Move card to "Done"

## Suggest Retrospective

```
✓ Feature {id}-{slug} completed

Capture learnings? This helps improve future work.
Run /retro to reflect on this feature.
```
```

**Step 2: Commit**

```bash
git add commands/finish.md
git commit -m "feat: add /finish command"
```

---

## Task 5: /features Command

**Files:**
- Create: `commands/features.md`

**Step 1: Write the command**

```markdown
---
description: List all active features across worktrees
---

# /features Command

List all active features.

## Gather Features

1. **Scan docs/features/** for feature folders
2. **Scan git worktrees** for feature branches
3. **Cross-reference** to determine status

## For Each Feature

Determine:
- ID and name
- Current phase (from artifacts)
- Worktree path (if exists)
- Last activity (file modification time)

## Display

```
Active Features:

ID   Name              Phase        Worktree                    Last Activity
───  ────              ─────        ────────                    ─────────────
42   user-auth         design       ../project-42-user-auth     2 hours ago
41   search-feature    implement    ../project-41-search        30 min ago
40   hotfix-login      complete     (none)                      1 day ago

Commands:
  /status {id}     View feature details
  /feature         Start new feature
  cd {worktree}    Switch to feature
```

## If No Features

```
No active features.

Run /feature "description" to start a new feature.
```
```

**Step 2: Commit**

```bash
git add commands/features.md
git commit -m "feat: add /features command"
```

---

## Task 6: Brainstorming Skill

**Files:**
- Create: `skills/workflow/brainstorming/SKILL.md`

**Step 1: Create skill directory**

```bash
mkdir -p skills/workflow/brainstorming
```

**Step 2: Write the skill**

```markdown
---
name: brainstorming
description: Guides ideation and exploration for new features. Use when starting a feature, exploring options, or generating ideas. Produces brainstorm.md with ideas, options, and initial direction.
---

# Brainstorming Phase

Guide divergent thinking to explore the problem space.

## Prerequisites

Check for feature context:
- Look for feature folder in `docs/dev_artifacts/workitems/`
- If not found: "No active feature. Run /feature first, or describe what you want to explore."

## Process

### 1. Understand the Goal

Ask ONE question at a time:
- "What problem are you trying to solve?"
- "Who is this for?"
- "What does success look like?"

Prefer multiple choice when possible.

### 2. Explore Options

Generate 2-3 different approaches:
- Approach A: [description] — Pros, Cons
- Approach B: [description] — Pros, Cons
- Approach C: [description] — Pros, Cons

State your recommendation and why.

### 3. Identify Constraints

- Technical constraints?
- Time constraints?
- Dependencies?

### 4. Capture Ideas

As you discuss, note:
- Key ideas
- Decisions made
- Open questions

## Output: brainstorm.md

Write to `docs/dev_artifacts/workitems/{id}-{slug}/brainstorm.md`:

```markdown
# Brainstorm: {Feature Name}

## Problem Statement
{What we're solving}

## Goals
- {Goal 1}
- {Goal 2}

## Approaches Considered

### Approach A: {Name}
{Description}
- Pros: ...
- Cons: ...

### Approach B: {Name}
{Description}
- Pros: ...
- Cons: ...

## Chosen Direction
{Which approach and why}

## Open Questions
- {Question 1}
- {Question 2}

## Next Steps
Ready for /spec to define requirements.
```

## Completion

"Brainstorm complete. Saved to brainstorm.md."

For Standard/Full mode: "Run /verify to check, or /spec to continue."
For Quick mode: "Run /spec to continue."
```

**Step 3: Commit**

```bash
git add skills/workflow/brainstorming/
git commit -m "feat: add brainstorming skill"
```

---

## Task 7: Specification Skill

**Files:**
- Create: `skills/workflow/specification/SKILL.md`

**Step 1: Create skill directory**

```bash
mkdir -p skills/workflow/specification
```

**Step 2: Write the skill**

```markdown
---
name: specification
description: Creates precise feature specifications with requirements and acceptance criteria. Use after brainstorming or when requirements need documenting. Produces spec.md.
---

# Specification Phase

Create precise, testable requirements.

## Prerequisites

Check for feature context and prior work:
- If `brainstorm.md` exists: Read for context
- If not: Gather requirements directly from user

## Process

### 1. Define the Problem

From brainstorm or user input, distill:
- One-sentence problem statement
- Who it affects
- Why it matters

### 2. Define Success Criteria

Ask: "How will we know this is done?"

Each criterion must be:
- Specific (not vague)
- Measurable (can verify)
- Testable (can write test for)

### 3. Define Scope

**In scope:** What we WILL build
**Out of scope:** What we WON'T build (explicit)

Apply YAGNI: Remove anything not essential.

### 4. Define Acceptance Criteria

For each feature aspect:
- Given [context]
- When [action]
- Then [result]

## Output: spec.md

Write to `docs/dev_artifacts/workitems/{id}-{slug}/spec.md`:

```markdown
# Specification: {Feature Name}

## Problem Statement
{One sentence}

## Success Criteria
- [ ] {Criterion 1 — measurable}
- [ ] {Criterion 2 — measurable}

## Scope

### In Scope
- {What we will build}

### Out of Scope
- {What we explicitly won't build}

## Acceptance Criteria

### {Feature Aspect 1}
- Given {context}
- When {action}
- Then {result}

### {Feature Aspect 2}
- Given {context}
- When {action}
- Then {result}

## Dependencies
- {External dependency, if any}

## Open Questions
- {Resolved during spec or deferred}
```

## Self-Check Before Completing

- [ ] Each criterion is testable?
- [ ] No implementation details (what, not how)?
- [ ] No unnecessary features (YAGNI)?
- [ ] Concise (fits one screen)?

If any check fails, revise before saving.

## Completion

"Spec complete. Saved to spec.md."
"Run /verify to check, or /design to continue."
```

**Step 3: Commit**

```bash
git add skills/workflow/specification/
git commit -m "feat: add specification skill"
```

---

## Task 8: Design Skill

**Files:**
- Create: `skills/workflow/design/SKILL.md`

**Step 1: Create skill directory**

```bash
mkdir -p skills/workflow/design
```

**Step 2: Write the skill**

```markdown
---
name: design
description: Creates architecture and interface definitions. Use after specification to design the technical approach. Produces design.md with architecture, interfaces, and contracts.
---

# Design Phase

Design the technical architecture.

## Prerequisites

- If `spec.md` exists: Read for requirements
- If not: "No spec found. Run /spec first, or describe requirements now."

## Process

### 1. Architecture Overview

High-level design:
- Components involved
- How they interact
- Data flow

Keep it simple (KISS). One diagram if helpful.

### 2. Interface Definitions

For each component boundary:
- Input format
- Output format
- Error cases

Define contracts before implementation.

### 3. Technical Decisions

For significant choices:
- Decision
- Options considered
- Rationale

### 4. Risk Assessment

- What could go wrong?
- How do we mitigate?

## Output: design.md

Write to `docs/dev_artifacts/workitems/{id}-{slug}/design.md`:

```markdown
# Design: {Feature Name}

## Architecture Overview

{High-level description}

```
[Simple diagram if helpful]
```

## Components

### {Component 1}
- Purpose: {what it does}
- Inputs: {what it receives}
- Outputs: {what it produces}

### {Component 2}
...

## Interfaces

### {Interface 1}
```
Input:  {format}
Output: {format}
Errors: {error cases}
```

### {Interface 2}
...

## Technical Decisions

### {Decision 1}
- **Choice:** {what we decided}
- **Alternatives:** {what we considered}
- **Rationale:** {why this choice}

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| {Risk 1} | {Impact} | {Mitigation} |

## Dependencies

- {Technical dependency}
```

## Self-Check

- [ ] KISS: Is this the simplest design that works?
- [ ] Interfaces defined before implementation?
- [ ] No over-engineering?

## Completion

"Design complete. Saved to design.md."
"Run /verify to check, or /plan to continue."
```

**Step 3: Commit**

```bash
git add skills/workflow/design/
git commit -m "feat: add design skill"
```

---

## Task 9: Planning Skill

**Files:**
- Create: `skills/workflow/planning/SKILL.md`

**Step 1: Create skill directory**

```bash
mkdir -p skills/workflow/planning
```

**Step 2: Write the skill**

```markdown
---
name: planning
description: Creates implementation plans with dependencies and sequencing. Use after design to plan the build order. Produces plan.md with ordered steps.
---

# Planning Phase

Create an ordered implementation plan.

## Prerequisites

- If `design.md` exists: Read for architecture
- If not: "No design found. Run /design first, or describe architecture now."

## Process

### 1. Identify Work Items

From design, list everything that needs building:
- Components
- Interfaces
- Tests
- Documentation

### 2. Map Dependencies

For each item:
- What must exist before this can start?
- What depends on this?

### 3. Determine Order

Build dependency graph, then sequence:
1. Independent items (can start immediately)
2. Items with resolved dependencies
3. Items waiting on others

### 4. Estimate Complexity

Not time estimates. Complexity indicators:
- Simple: Straightforward implementation
- Medium: Some decisions needed
- Complex: Significant work or risk

## Output: plan.md

Write to `docs/dev_artifacts/workitems/{id}-{slug}/plan.md`:

```markdown
# Plan: {Feature Name}

## Implementation Order

### Phase 1: Foundation
Items with no dependencies.

1. **{Item}** — {brief description}
   - Complexity: Simple/Medium/Complex
   - Files: {files to create/modify}

2. **{Item}** — {brief description}
   ...

### Phase 2: Core Implementation
Items depending on Phase 1.

1. **{Item}** — {brief description}
   - Depends on: {Phase 1 items}
   - Complexity: ...
   - Files: ...

### Phase 3: Integration
Items depending on Phase 2.

...

## Dependency Graph

```
{Item A} ──→ {Item B} ──→ {Item D}
                    ↘
{Item C} ──────────→ {Item E}
```

## Risk Areas

- {Complex item}: {why it's risky}

## Testing Strategy

- Unit tests for: {components}
- Integration tests for: {interactions}

## Definition of Done

- [ ] All items implemented
- [ ] Tests passing
- [ ] Code reviewed
```

## Completion

"Plan complete. Saved to plan.md."
"Run /verify to check, or /tasks to break into actionable items."
```

**Step 3: Commit**

```bash
git add skills/workflow/planning/
git commit -m "feat: add planning skill"
```

---

## Task 10: Task Breakdown Skill

**Files:**
- Create: `skills/workflow/task-breakdown/SKILL.md`

**Step 1: Create skill directory**

```bash
mkdir -p skills/workflow/task-breakdown
```

**Step 2: Write the skill**

```markdown
---
name: task-breakdown
description: Breaks implementation plan into small, actionable tasks. Use after planning to create executable work items. Produces tasks.md.
---

# Task Breakdown Phase

Create small, actionable, testable tasks.

## Prerequisites

- If `plan.md` exists: Read for implementation order
- If not: "No plan found. Run /plan first."

## Process

### 1. Break Down Each Plan Item

For each item in the plan:
- What are the smallest testable pieces?
- Each task: 5-15 minutes of work
- Each task: Clear completion criteria

### 2. Apply TDD Structure

For implementation tasks:
1. Write failing test
2. Implement minimal code
3. Verify test passes
4. Refactor if needed
5. Commit

### 3. Ensure Independence

Each task should:
- Be completable on its own
- Have clear inputs/outputs
- Not require context from other tasks

## Output: tasks.md

Write to `docs/dev_artifacts/workitems/{id}-{slug}/tasks.md`:

```markdown
# Tasks: {Feature Name}

## Task List

### Phase 1: Foundation

#### Task 1.1: {Brief description}
- **Files:** `path/to/file.ts`
- **Do:** {What to do}
- **Test:** {How to verify}
- **Done when:** {Completion criteria}

#### Task 1.2: {Brief description}
...

### Phase 2: Core Implementation

#### Task 2.1: {Brief description}
- **Depends on:** Task 1.1, 1.2
- **Files:** `path/to/file.ts`
- **Do:** {What to do}
- **Test:** {How to verify}
- **Done when:** {Completion criteria}

...

## Summary

- Total tasks: {n}
- Phase 1: {n} tasks
- Phase 2: {n} tasks
- Phase 3: {n} tasks
```

## State Tracking

If Vibe-Kanban available:
- Create card for each task
- Set dependencies

If TodoWrite:
- Create todo items

## Completion

"Tasks created. {n} tasks across {m} phases."
"Run /verify to check, or /implement to start building."
```

**Step 3: Commit**

```bash
git add skills/workflow/task-breakdown/
git commit -m "feat: add task-breakdown skill"
```

---

## Task 11: Implementation Skill

**Files:**
- Create: `skills/workflow/implementing/SKILL.md`

**Step 1: Create skill directory**

```bash
mkdir -p skills/workflow/implementing
```

**Step 2: Write the skill**

```markdown
---
name: implementing
description: Guides code implementation with TDD approach. Use when ready to write code. Works through tasks.md items systematically.
---

# Implementation Phase

Execute the implementation plan.

## Prerequisites

- If `tasks.md` exists: Read for task list
- If not: "No tasks found. Run /tasks first, or describe what to implement."

## Process

### 1. Select Next Task

From tasks.md, find first incomplete task:
- Check Vibe-Kanban/TodoWrite for status
- Or ask user which task to work on

### 2. Understand the Task

Read task details:
- What files are involved?
- What's the expected outcome?
- What tests verify completion?

### 3. Implement with TDD

For each task:

**Step A: Write the test first**
```
Create test that describes expected behavior.
Run test - should FAIL (red).
```

**Step B: Write minimal implementation**
```
Write just enough code to pass the test.
Run test - should PASS (green).
```

**Step C: Refactor if needed**
```
Clean up code while keeping tests green.
```

**Step D: Commit**
```
git add {files}
git commit -m "feat: {brief description}"
```

### 4. Mark Complete

Update Vibe-Kanban/TodoWrite status.

### 5. Next Task or Done

If more tasks: "Task complete. Continue to next task?"
If all done: "All tasks complete. Run /verify for quality review, then /finish."

## Agent Delegation

For complex tasks, consider delegation:

```
All files in one domain?
  Frontend (.tsx, .css) → frontend-specialist
  API (routes, handlers) → api-specialist
  Database (migrations) → database-specialist
  Mixed → handle directly

Unsure? Ask user.
```

## Error Handling

If implementation is stuck:
1. Try a different approach
2. Break into smaller pieces
3. Ask user for guidance

Never spin endlessly. Ask when stuck.

## Completion

After all tasks:
"Implementation complete. {n} tasks done."
"Run /verify for quality review."
"Run /finish when ready to complete the feature."
```

**Step 3: Commit**

```bash
git add skills/workflow/implementing/
git commit -m "feat: add implementing skill"
```

---

## Task 12: Verification Skill

**Files:**
- Create: `skills/verification/verifying/SKILL.md`

**Step 1: Create skill directory**

```bash
mkdir -p skills/verification/verifying
```

**Step 2: Write the skill**

```markdown
---
name: verifying
description: Runs phase-appropriate verification with fresh perspective. Use after any phase to check quality. Reports issues by severity with fix suggestions.
---

# Verification

Check work quality with fresh perspective.

## Determine Current Phase

Read feature folder to determine what to verify:
- brainstorm.md exists, no spec.md → Verify brainstorm
- spec.md exists, no design.md → Verify spec
- design.md exists, no plan.md → Verify design
- plan.md exists, no tasks.md → Verify plan
- tasks.md exists, implementation incomplete → Verify tasks
- Implementation complete → Quality review

## Verification Checklists

### Brainstorm Verification
- [ ] Problem clearly stated?
- [ ] Multiple options explored?
- [ ] Decision rationale documented?
- [ ] Open questions captured?

### Spec Verification
- [ ] Each criterion testable?
- [ ] No implementation details (what, not how)?
- [ ] No unnecessary features (YAGNI)?
- [ ] Scope clearly bounded?

### Design Verification
- [ ] KISS: Simplest approach?
- [ ] Interfaces defined before implementation?
- [ ] No over-engineering?
- [ ] Dependencies identified?

### Plan Verification
- [ ] Dependencies mapped correctly?
- [ ] Order makes sense?
- [ ] All spec items covered?
- [ ] Risks identified?

### Tasks Verification
- [ ] Each task small (5-15 min)?
- [ ] Each task independently testable?
- [ ] TDD steps included?
- [ ] All plan items covered?

### Quality Review (Post-Implementation)
- [ ] Code is readable?
- [ ] No dead code?
- [ ] Tests pass?
- [ ] No obvious bugs?
- [ ] KISS and YAGNI followed?

## Report Format

```
Verification: {phase}

🔴 Blockers (must fix):
- {Issue}: {description}
  Fix: {suggestion}

🟡 Warnings (should fix):
- {Issue}: {description}
  Fix: {suggestion}

🟢 Notes (consider):
- {Observation}

Result: {PASS / NEEDS FIXES}
```

## Circuit Breaker

Track verification attempts per phase.
After 3 failures on same phase:

```
Verification has failed 3 times for {phase}.

This usually indicates:
- Requirements unclear → Loop back to brainstorm
- Approach flawed → Reconsider design
- Criteria too strict → Review expectations

What would you like to do?
1. Try fixing issues again
2. Loop back to earlier phase
3. Proceed anyway (your judgment)
4. Discuss with me
```

## Completion

If PASS: "Verification passed. Ready for next phase."
If NEEDS FIXES: "Issues found. Fix and re-run /verify, or proceed anyway."
```

**Step 3: Commit**

```bash
git add skills/verification/verifying/
git commit -m "feat: add verification skill"
```

---

## Task 13: Retrospective Skill

**Files:**
- Create: `skills/workflow/retrospecting/SKILL.md`

**Step 1: Create skill directory**

```bash
mkdir -p skills/workflow/retrospecting
```

**Step 2: Write the skill**

```markdown
---
name: retrospecting
description: Captures learnings from completed features into knowledge bank. Use after /finish or anytime to reflect. Updates constitution.md, patterns.md, etc.
---

# Retrospective

Capture and codify learnings.

## Gather Data

Read feature folder:
- What verification issues occurred?
- What blockers were encountered?
- What surprises came up?
- What went well?

Ask user:
- "What would you do differently?"
- "What worked well?"
- "Any patterns worth documenting?"

## Identify Learnings

Categorize findings:

### Patterns (What worked)
- Approach that solved a problem well
- Technique worth reusing

### Anti-Patterns (What to avoid)
- Approach that caused problems
- Mistake not to repeat

### Heuristics (Decision guides)
- Rule of thumb discovered
- When to use which approach

### Principles (If fundamental enough)
- Core principle reinforced or discovered

## Propose Updates

For each learning, propose where it goes:

```
Learning: "Defining interfaces first enabled parallel work"

Proposed update:
- File: docs/knowledge-bank/patterns.md
- Add:
  ### Pattern: Early Interface Definition
  Define interfaces before implementation to enable parallel work.
  - Observed in: Feature #{id}
  - Benefit: Reduced integration issues

Add this? (y/n)
```

## Write Updates

For approved updates:
1. Read current file
2. Add new entry
3. Save file

## Output: retro.md

Write to `docs/dev_artifacts/workitems/{id}-{slug}/retro.md`:

```markdown
# Retrospective: {Feature Name}

## What Went Well
- {Positive observation}

## What Could Improve
- {Improvement area}

## Learnings Captured
- Added to patterns.md: {pattern name}
- Added to anti-patterns.md: {anti-pattern name}

## Action Items
- {Any follow-up actions}
```

## Completion

"Retrospective complete."
"Updated: {list of knowledge-bank files updated}"
"Saved to retro.md."
```

**Step 3: Commit**

```bash
git add skills/workflow/retrospecting/
git commit -m "feat: add retrospecting skill"
```

---

## Task 14: Generic Worker Agent

**Files:**
- Create: `agents/workers/generic-worker.md`

**Step 1: Create agent file**

```markdown
---
name: generic-worker
description: General-purpose implementation agent. Use for mixed-domain tasks or when no specialist fits.
tools: [Read, Write, Edit, Bash, Glob, Grep]
---

# Generic Worker Agent

You are an implementation agent handling general development tasks.

## Your Role

- Implement code changes as specified
- Write tests before implementation (TDD)
- Make small, focused commits
- Ask for clarification when stuck

## Approach

1. **Understand the task**: Read relevant files, understand context
2. **Write test first**: Create failing test for expected behavior
3. **Implement minimally**: Just enough code to pass the test
4. **Verify**: Run tests, ensure they pass
5. **Commit**: Small, descriptive commit

## Guidelines

- KISS: Simplest solution that works
- YAGNI: Only what's needed
- DRY: But don't over-abstract
- Clear names: Code should read like prose

## When Stuck

Try:
1. Different approach
2. Break into smaller pieces
3. Read related code for patterns

If still stuck: Report back with what you tried and where you're blocked.

## Output

Return:
- What was implemented
- Files changed
- Tests added
- Any concerns or follow-ups
```

**Step 2: Commit**

```bash
git add agents/workers/generic-worker.md
git commit -m "feat: add generic-worker agent"
```

---

## Task 15: Investigation Agent

**Files:**
- Create: `agents/workers/investigation-agent.md`

**Step 1: Create agent file**

```markdown
---
name: investigation-agent
description: Read-only research agent. Use to gather context before implementation without making changes.
tools: [Read, Glob, Grep, WebFetch, WebSearch]
---

# Investigation Agent

You are a research agent. You gather information but DO NOT make changes.

## Your Role

- Explore codebase to understand patterns
- Find relevant files and code
- Document findings
- Identify potential issues

## Constraints

- READ ONLY: Never use Write, Edit, or Bash
- Gather information only
- Report findings, don't act on them

## Investigation Process

1. **Understand the question**: What are we trying to learn?
2. **Search broadly**: Find relevant files and patterns
3. **Read deeply**: Understand the code found
4. **Synthesize**: Connect findings to the question
5. **Report**: Clear summary of findings

## Output Format

```
## Investigation: {Topic}

### Question
{What we wanted to know}

### Findings

#### {Finding 1}
- Location: {file:line}
- Observation: {what we found}
- Relevance: {why it matters}

#### {Finding 2}
...

### Patterns Observed
- {Pattern 1}
- {Pattern 2}

### Recommendations
- {Suggestion based on findings}

### Open Questions
- {Things still unclear}
```
```

**Step 2: Commit**

```bash
git add agents/workers/investigation-agent.md
git commit -m "feat: add investigation-agent"
```

---

## Task 16: Quality Reviewer Agent

**Files:**
- Create: `agents/specialists/quality-reviewer.md`

**Step 1: Create agent file**

```markdown
---
name: quality-reviewer
description: Code quality verifier. Use after implementation to check code quality, find dead code, ensure readability.
tools: [Read, Glob, Grep]
---

# Quality Reviewer Agent

You review code quality after implementation.

## Your Role

- Check code readability
- Find dead/unused code
- Verify KISS and YAGNI
- Suggest improvements

## Review Checklist

### Readability
- [ ] Clear variable/function names?
- [ ] Functions are focused (single responsibility)?
- [ ] Comments explain "why" not "what"?
- [ ] Consistent formatting?

### Simplicity (KISS)
- [ ] Simplest solution that works?
- [ ] No premature optimization?
- [ ] No unnecessary abstraction?

### Necessity (YAGNI)
- [ ] No unused code?
- [ ] No unused imports?
- [ ] No feature flags for hypotheticals?
- [ ] No backwards-compat hacks?

### Cleanliness
- [ ] No dead code paths?
- [ ] No commented-out code?
- [ ] No TODO/FIXME left unaddressed?

### Tests
- [ ] Tests exist for new code?
- [ ] Tests are readable?
- [ ] No redundant tests?

## Output Format

```
## Quality Review

### Summary
{Overall assessment: Good / Needs Work}

### Issues Found

🔴 Must Fix:
- {File:line}: {Issue}

🟡 Should Fix:
- {File:line}: {Issue}

🟢 Consider:
- {Suggestion}

### Dead Code Found
- {File}: {unused function/import}

### Recommendations
- {Improvement suggestion}
```

## Principle

Be constructive, not pedantic. Focus on issues that matter.
```

**Step 2: Commit**

```bash
git add agents/specialists/quality-reviewer.md
git commit -m "feat: add quality-reviewer agent"
```

---

## Task 17: Update validate.sh

**Files:**
- Modify: `validate.sh`

**Step 1: Read current validate.sh**

Read the file to understand current structure.

**Step 2: Update to include new paths**

Ensure it validates:
- `skills/*/SKILL.md` and `skills/*/*/SKILL.md` (nested)
- `agents/*/*.md`
- `commands/*.md`

**Step 3: Commit**

```bash
git add validate.sh
git commit -m "fix: update validate.sh for new directory structure"
```

---

## Task 18: Final Validation and Test

**Step 1: Run validation**

```bash
./validate.sh
```

Expected: All components pass validation.

**Step 2: Test /feature command**

```bash
claude "/feature test-feature"
```

Verify:
- Mode selection works
- Folder created
- Appropriate next step suggested

**Step 3: Test /status command**

```bash
claude "/status"
```

Verify: Shows current state correctly.

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: address validation issues"
```

---

## Task 19: Final Commit and Push

**Step 1: Ensure clean state**

```bash
git status
```

**Step 2: Push all changes**

```bash
git push
```

**Step 3: Verify on remote**

Check GitHub that all files are present.

---

## Task 20: Phase Commands (brainstorm, spec, design, plan, tasks, implement, verify, retro)

**Files:**
- Create: `commands/brainstorm.md`
- Create: `commands/spec.md`
- Create: `commands/design.md`
- Create: `commands/plan.md`
- Create: `commands/tasks.md`
- Create: `commands/implement.md`
- Create: `commands/verify.md`
- Create: `commands/retro.md`

Each command is a thin wrapper that invokes the corresponding skill.

**Step 1: Create all phase command files**

```markdown
# commands/brainstorm.md
---
description: Start brainstorming phase for current feature
argument-hint: [topic]
---

Invoke the brainstorming skill for the current feature context.

Read docs/features/ to find active feature, then follow brainstorming skill instructions.
```

```markdown
# commands/spec.md
---
description: Create specification for current feature
---

Invoke the specification skill for the current feature context.

Read docs/features/ to find active feature, then follow specification skill instructions.
```

```markdown
# commands/design.md
---
description: Create architecture design for current feature
---

Invoke the design skill for the current feature context.

Read docs/features/ to find active feature, then follow design skill instructions.
```

```markdown
# commands/plan.md
---
description: Create implementation plan for current feature
---

Invoke the planning skill for the current feature context.

Read docs/features/ to find active feature, then follow planning skill instructions.
```

```markdown
# commands/tasks.md
---
description: Break down plan into actionable tasks
---

Invoke the task-breakdown skill for the current feature context.

Read docs/features/ to find active feature, then follow task-breakdown skill instructions.
```

```markdown
# commands/implement.md
---
description: Start or continue implementation of current feature
---

Invoke the implementing skill for the current feature context.

Read docs/features/ to find active feature, then follow implementing skill instructions.
```

```markdown
# commands/verify.md
---
description: Run verification for current phase
---

Invoke the verifying skill for the current feature context.

Read docs/features/ to find active feature and determine phase, then follow verifying skill instructions.
```

```markdown
# commands/retro.md
---
description: Run retrospective for current or completed feature
argument-hint: [feature-id]
---

Invoke the retrospecting skill for the specified or current feature.

Read docs/features/ to find feature, then follow retrospecting skill instructions.
```

**Step 2: Commit all commands**

```bash
git add commands/brainstorm.md commands/spec.md commands/design.md commands/plan.md commands/tasks.md commands/implement.md commands/verify.md commands/retro.md
git commit -m "feat: add phase commands (brainstorm, spec, design, plan, tasks, implement, verify, retro)"
```

---

## Task 21: Feature Metadata File

**Files:**
- Update: `commands/feature.md` to create `.meta.json`
- Update: All phase skills to read `.meta.json`

**Purpose:** Track feature mode (Hotfix/Quick/Standard/Full) persistently.

**Step 1: Add metadata creation to /feature command**

Add to `commands/feature.md` after folder creation:

```markdown
## Create Metadata File

Write to `docs/dev_artifacts/workitems/{id}-{slug}/.meta.json`:

```json
{
  "id": "{id}",
  "name": "{slug}",
  "mode": "{selected-mode}",
  "created": "{ISO timestamp}",
  "worktree": "{path or null}"
}
```
```

**Step 2: Update skills to read metadata**

Add to each phase skill's Prerequisites section:

```markdown
## Read Feature Context

1. Find active feature folder in `docs/dev_artifacts/workitems/`
2. Read `.meta.json` for mode and context
3. Adjust behavior based on mode:
   - Hotfix: Skip to implementation guidance
   - Quick: Streamlined process
   - Standard: Full process with optional verification
   - Full: Full process with required verification
```

**Step 3: Commit**

```bash
git add commands/feature.md skills/
git commit -m "feat: add feature metadata tracking (.meta.json)"
```

---

## Task 22: Vibe-Kanban Detection Helper

**Files:**
- Create: `skills/practices/kanban-detection/SKILL.md`

**Step 1: Create detection skill**

```markdown
---
name: kanban-detection
description: Detects Vibe-Kanban availability and provides fallback to TodoWrite. Internal skill used by other workflow components.
---

# Kanban Detection

## Check Availability

1. Look for MCP tools matching pattern `vibe-kanban` or `mcp__vibe-kanban__*`
2. If found: Vibe-Kanban is available
3. If not found: Use TodoWrite as fallback

## When Available

Use Vibe-Kanban MCP tools:
- Create cards for features/tasks
- Update card status
- Track progress visually

## When Not Available

Use TodoWrite tool:
- Create todo items for tracking
- Update status via TodoWrite
- Workflow continues normally

## Detection Code Pattern

```
Check: Are any tools available matching "vibe-kanban"?
  Yes → Use Vibe-Kanban
  No  → Use TodoWrite

Never fail if Kanban unavailable. Graceful degradation.
```
```

**Step 2: Commit**

```bash
git add skills/practices/kanban-detection/
git commit -m "feat: add kanban-detection helper skill"
```

---

## Task 23: Fix README Paths

**Files:**
- Update: README.md (from Task 0)

**Step 1: Fix relative paths**

Change:
```markdown
See [Component Authoring Guide](docs/dev_guides/component-authoring.md).
```

To:
```markdown
See [Component Authoring Guide](./docs/dev_guides/component-authoring.md).
```

And:
```markdown
- [Feature Workflow Design](docs/plans/2026-01-28-feature-workflow-design.md)
- [Component Authoring Guide](docs/dev_guides/component-authoring.md)
```

To:
```markdown
- [Feature Workflow Design](./docs/plans/2026-01-28-feature-workflow-design.md)
- [Component Authoring Guide](./docs/dev_guides/component-authoring.md)
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "fix: correct relative paths in README"
```

---

## Task 24: Update validate.sh with Specific Changes

**Files:**
- Modify: `validate.sh`

**Step 1: Update skill validation paths**

Replace the skills validation section:

```bash
# Validate skills (support nested directories)
echo "Validating Skills..."
for skill_file in $(find ./skills -name "SKILL.md" -type f 2>/dev/null); do
    log_info "Checking $skill_file"
    validate_frontmatter "$skill_file" && log_success "Frontmatter valid"
    validate_description "$skill_file"
    validate_skill_size "$skill_file"
done
echo ""
```

**Step 2: Add agent validation**

Add after skills validation:

```bash
# Validate agents
echo "Validating Agents..."
for agent_file in $(find ./agents -name "*.md" -type f 2>/dev/null); do
    log_info "Checking $agent_file"
    validate_frontmatter "$agent_file" && log_success "Frontmatter valid"
done
echo ""
```

**Step 3: Add commands validation**

Add after agents validation:

```bash
# Validate commands
echo "Validating Commands..."
for cmd_file in $(find ./commands -name "*.md" -type f 2>/dev/null); do
    log_info "Checking $cmd_file"
    # Commands need description in frontmatter
    if ! grep -q "^description:" "$cmd_file"; then
        log_error "$cmd_file: Missing 'description' field in frontmatter"
    else
        log_success "Frontmatter valid"
    fi
done
echo ""
```

**Step 4: Commit**

```bash
git add validate.sh
git commit -m "fix: update validate.sh for nested skills, agents, and commands"
```

---

## Summary

| Task | Component | Files |
|------|-----------|-------|
| 0 | README | README.md |
| 1 | File structure | docs/, skills/, agents/, commands/ |
| 2 | /feature command | commands/feature.md |
| 3 | /status command | commands/status.md |
| 4 | /finish command | commands/finish.md |
| 5 | /features command | commands/features.md |
| 6 | Brainstorming skill | skills/workflow/brainstorming/SKILL.md |
| 7 | Specification skill | skills/workflow/specification/SKILL.md |
| 8 | Design skill | skills/workflow/design/SKILL.md |
| 9 | Planning skill | skills/workflow/planning/SKILL.md |
| 10 | Task breakdown skill | skills/workflow/task-breakdown/SKILL.md |
| 11 | Implementation skill | skills/workflow/implementing/SKILL.md |
| 12 | Verification skill | skills/verification/verifying/SKILL.md |
| 13 | Retrospective skill | skills/workflow/retrospecting/SKILL.md |
| 14 | Generic worker agent | agents/workers/generic-worker.md |
| 15 | Investigation agent | agents/workers/investigation-agent.md |
| 16 | Quality reviewer agent | agents/specialists/quality-reviewer.md |
| 17 | Update validate.sh (initial) | validate.sh |
| 18 | Validation and test | - |
| 19 | Final push (first batch) | - |
| 20 | Phase commands | commands/brainstorm.md, spec.md, etc. |
| 21 | Feature metadata | .meta.json support |
| 22 | Kanban detection | skills/practices/kanban-detection/SKILL.md |
| 23 | Fix README paths | README.md |
| 24 | validate.sh specifics | validate.sh |

Total: 25 tasks

---

## Design Decisions Documented

### Why Commands + Skills (Not Just Skills)

Commands are user-invocable entry points. Skills contain the logic. This separation allows:
- Commands can be simple wrappers
- Skills can be reused by other skills
- Clear distinction between "what user types" and "what Claude does"

### Why .meta.json for Mode Tracking

- JSON is easy to read/write
- Keeps mode with feature (not global)
- Hidden file (.) keeps feature folder clean
- Can extend with more metadata later

### Why No Specialist Agents in Initial Implementation

Specialist agents (frontend-specialist, api-specialist, database-specialist) are mentioned in design but not implemented in Phase 1 because:
- Generic worker handles most cases
- Specialists can be added incrementally when patterns emerge
- YAGNI: Don't build until needed

Add specialist agents in a future iteration when specific domain patterns are identified through use.
