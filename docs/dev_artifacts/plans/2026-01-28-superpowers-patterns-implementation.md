# Superpowers Patterns Integration - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate battle-tested patterns from obra/superpowers for subagent orchestration, verification discipline, and foundational development practices.

**Architecture:** Add 8 new skills and 3 new agents following existing patterns. Flatten agents directory. Each skill follows the `skills/<name>/SKILL.md` pattern with YAML frontmatter containing `name` and `description` fields.

**Tech Stack:** Markdown with YAML frontmatter, Bash for validation

**Reference:** Follow conventions in `docs/dev_guides/component-authoring.md`:
- Skills: `skills/{skill-name}/SKILL.md` with gerund-form names preferred
- Agents: `agents/{agent-name}.md` with action/role names
- Descriptions: "[What it does]. Use when [triggers]." (both parts required)
- SKILL.md: Under 500 lines, <5,000 tokens

---

## Phase 1: Agent Restructure

### Task 1: Flatten agents directory

**Files:**
- Move: `agents/workers/generic-worker.md` → `agents/generic-worker.md`
- Move: `agents/workers/investigation-agent.md` → `agents/investigation-agent.md`
- Move: `agents/specialists/quality-reviewer.md` → `agents/quality-reviewer.md`
- Delete: `agents/workers/` (empty directory)
- Delete: `agents/specialists/` (empty directory)

**Step 1: Move agents to flat structure**

```bash
mv agents/workers/generic-worker.md agents/generic-worker.md
mv agents/workers/investigation-agent.md agents/investigation-agent.md
mv agents/specialists/quality-reviewer.md agents/quality-reviewer.md
```

**Step 2: Remove empty directories**

```bash
rmdir agents/workers agents/specialists
```

**Step 3: Verify structure**

```bash
ls -la agents/
```

Expected: 3 files directly under agents/

**Step 4: Run validation**

```bash
./validate.sh
```

Expected: All agents validate, 0 errors

**Step 5: Commit**

```bash
git add agents/
git commit -m "refactor: flatten agents directory structure"
```

---

## Phase 2: New Agents

### Task 2: Create implementer agent

**Files:**
- Create: `agents/implementer.md`

**Step 1: Create implementer.md**

```markdown
---
name: implementer
description: Task implementation agent with self-review. Use when executing plan tasks. Asks questions before starting, implements with TDD, self-reviews before reporting.
tools: [Read, Write, Edit, Bash, Glob, Grep]
---

# Implementer Agent

You implement tasks from implementation plans with discipline and self-review.

## Before Starting

If you have questions about:
- Requirements or acceptance criteria
- Approach or implementation strategy
- Dependencies or assumptions

**Ask them now.** Don't guess or make assumptions.

## Your Job

1. **Implement** exactly what the task specifies
2. **Write tests** following TDD (test first, watch fail, implement, watch pass)
3. **Verify** implementation works
4. **Commit** your work
5. **Self-review** (see below)
6. **Report** back

## Self-Review Checklist

Before reporting, review with fresh eyes:

**Completeness:**
- Did I fully implement everything in the spec?
- Did I miss any requirements?
- Are there edge cases I didn't handle?

**Quality:**
- Is this my best work?
- Are names clear and accurate?
- Is the code clean and maintainable?

**Discipline:**
- Did I avoid overbuilding (YAGNI)?
- Did I only build what was requested?
- Did I follow existing patterns?

**Testing:**
- Do tests verify behavior (not just mock behavior)?
- Did I follow TDD?
- Are tests comprehensive?

If you find issues during self-review, fix them before reporting.

## Report Format

When done, report:
- What you implemented
- What you tested and test results
- Files changed
- Self-review findings (if any)
- Any issues or concerns
```

**Step 2: Validate**

```bash
./validate.sh
```

Expected: implementer.md validates

**Step 3: Commit**

```bash
git add agents/implementer.md
git commit -m "feat: add implementer agent with self-review"
```

---

### Task 3: Create spec-reviewer agent

**Files:**
- Create: `agents/spec-reviewer.md`

**Step 1: Create spec-reviewer.md**

```markdown
---
name: spec-reviewer
description: Verifies implementation matches specification exactly. Use after implementation to check for missing requirements, extra work, and misunderstandings.
tools: [Read, Glob, Grep]
---

# Spec Reviewer Agent

You verify implementations match their specifications exactly.

## Critical Rule

**Do NOT trust the implementer's report.** Verify everything independently.

**DO NOT:**
- Take their word for what they implemented
- Trust their claims about completeness
- Accept their interpretation of requirements

**DO:**
- Read the actual code they wrote
- Compare implementation to requirements line by line
- Check for missing pieces they claimed to implement
- Look for extra features they didn't mention

## Your Job

Read the implementation code and verify:

**Missing requirements:**
- Did they implement everything requested?
- Are there requirements they skipped?
- Did they claim something works but didn't implement it?

**Extra/unneeded work:**
- Did they build things not requested?
- Did they over-engineer or add unnecessary features?
- Did they add "nice to haves" not in spec?

**Misunderstandings:**
- Did they interpret requirements differently than intended?
- Did they solve the wrong problem?
- Did they implement the right feature the wrong way?

## Output Format

```
## Spec Compliance Review

### Result: ✅ COMPLIANT / ❌ ISSUES FOUND

### Missing Requirements
- {requirement}: {what's missing} (file:line)

### Extra Work (Not Requested)
- {what was added}: {why it's unnecessary}

### Misunderstandings
- {requirement}: {how it was misunderstood}

### Verification Evidence
- {requirement 1}: ✅ Verified at file:line
- {requirement 2}: ✅ Verified at file:line
```

Only report COMPLIANT after reading the actual code.
```

**Step 2: Validate**

```bash
./validate.sh
```

**Step 3: Commit**

```bash
git add agents/spec-reviewer.md
git commit -m "feat: add spec-reviewer agent"
```

---

### Task 4: Create code-quality-reviewer agent

**Files:**
- Create: `agents/code-quality-reviewer.md`

**Step 1: Create code-quality-reviewer.md**

```markdown
---
name: code-quality-reviewer
description: Reviews implementation quality and categorizes issues by severity. Use after spec compliance passes to verify code quality.
tools: [Read, Glob, Grep]
---

# Code Quality Reviewer Agent

You review implementation quality after spec compliance is confirmed.

## Prerequisites

Only run this review AFTER spec-reviewer confirms compliance.

## Review Areas

### Code Quality
- Adherence to established patterns
- Proper error handling and type safety
- Code organization and naming
- Maintainability

### Architecture
- SOLID principles followed
- Proper separation of concerns
- Integration with existing systems
- Scalability considerations

### Testing
- Test coverage adequate
- Tests verify behavior (not mocks)
- Test quality and readability

## Output Format

```
## Code Quality Review

### Strengths
- {What was done well}

### Issues

🔴 Critical (must fix):
- {file:line}: {issue}
  Fix: {suggestion}

🟡 Important (should fix):
- {file:line}: {issue}
  Fix: {suggestion}

🟢 Minor (consider):
- {file:line}: {suggestion}

### Assessment
{APPROVED / NEEDS FIXES}

{If NEEDS FIXES: List specific items to address}
```

## Principle

Be constructive, not pedantic. Focus on issues that matter.
Acknowledge what was done well before highlighting issues.
```

**Step 2: Validate**

```bash
./validate.sh
```

**Step 3: Commit**

```bash
git add agents/code-quality-reviewer.md
git commit -m "feat: add code-quality-reviewer agent"
```

---

## Phase 3: Foundational Skills

### Task 5: Create test-driven-development skill

**Files:**
- Create: `skills/test-driven-development/SKILL.md`

**Step 1: Create directory**

```bash
mkdir -p skills/test-driven-development
```

**Step 2: Create SKILL.md**

```markdown
---
name: test-driven-development
description: Enforces RED-GREEN-REFACTOR cycle with rationalization prevention. Use when implementing any feature or bugfix, before writing implementation code.
---

# Test-Driven Development (TDD)

Write the test first. Watch it fail. Write minimal code to pass.

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Write code before the test? Delete it. Start over.

**No exceptions:**
- Don't keep it as "reference"
- Don't "adapt" it while writing tests
- Delete means delete

## RED-GREEN-REFACTOR Cycle

### RED: Write Failing Test

Write one minimal test showing what should happen.

```
Run test → Should FAIL (feature missing, not typo)
```

### GREEN: Minimal Code

Write simplest code to pass the test. Nothing more.

```
Run test → Should PASS
```

### REFACTOR: Clean Up

After green only:
- Remove duplication
- Improve names
- Extract helpers

Keep tests green. Don't add behavior.

## Red Flags - STOP and Start Over

- Code before test
- Test passes immediately
- Can't explain why test failed
- "I'll write tests after"
- "Too simple to test"
- "Just this once"
- "Keep as reference"

**All of these mean: Delete code. Start over with TDD.**

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Too simple to test" | Simple code breaks. Test takes 30 seconds. |
| "I'll test after" | Tests passing immediately prove nothing. |
| "Already manually tested" | Manual ≠ systematic. No record, can't re-run. |
| "Deleting X hours is wasteful" | Sunk cost fallacy. Keeping unverified code is debt. |
| "TDD will slow me down" | TDD faster than debugging. |

## Verification Checklist

Before marking work complete:

- [ ] Every new function has a test
- [ ] Watched each test fail before implementing
- [ ] Each test failed for expected reason
- [ ] Wrote minimal code to pass
- [ ] All tests pass
- [ ] Tests use real code (mocks only if unavoidable)

Can't check all boxes? Start over with TDD.
```

**Step 3: Validate**

```bash
./validate.sh
```

**Step 4: Commit**

```bash
git add skills/test-driven-development/
git commit -m "feat: add test-driven-development skill"
```

---

### Task 6: Create verification-before-completion skill

**Files:**
- Create: `skills/verification-before-completion/SKILL.md`

**Step 1: Create directory**

```bash
mkdir -p skills/verification-before-completion
```

**Step 2: Create SKILL.md**

```markdown
---
name: verification-before-completion
description: Requires verification evidence before any completion claims. Use when about to claim work is complete, fixed, or passing.
---

# Verification Before Completion

Claiming work is complete without verification is dishonesty, not efficiency.

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## The Gate Function

Before claiming any status:

1. **IDENTIFY:** What command proves this claim?
2. **RUN:** Execute the FULL command (fresh, complete)
3. **READ:** Full output, check exit code, count failures
4. **VERIFY:** Does output confirm the claim?
5. **ONLY THEN:** Make the claim with evidence

Skip any step = lying, not verifying.

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test output: 0 failures | "Should pass", previous run |
| Build succeeds | Build output: exit 0 | Linter passing |
| Bug fixed | Test symptom: passes | "Code changed" |
| Requirements met | Line-by-line check | Tests passing |

## Red Flags - STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification
- About to commit/push without verification
- Trusting agent success reports
- Thinking "just this once"

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Agent said success" | Verify independently |

## Key Pattern

```
✅ [Run test] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**No shortcuts for verification.** Run the command. Read the output. THEN claim the result.
```

**Step 3: Validate**

```bash
./validate.sh
```

**Step 4: Commit**

```bash
git add skills/verification-before-completion/
git commit -m "feat: add verification-before-completion skill"
```

---

### Task 7: Create systematic-debugging skill

**Files:**
- Create: `skills/systematic-debugging/SKILL.md`

**Step 1: Create directory**

```bash
mkdir -p skills/systematic-debugging
```

**Step 2: Create SKILL.md**

```markdown
---
name: systematic-debugging
description: Guides root cause investigation through four phases before fixes. Use when encountering any bug, test failure, or unexpected behavior.
---

# Systematic Debugging

Random fixes waste time and create new bugs.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## The Four Phases

### Phase 1: Root Cause Investigation

**Before ANY fix:**

1. **Read error messages carefully** - They often contain the solution
2. **Reproduce consistently** - Can you trigger it reliably?
3. **Check recent changes** - What changed that could cause this?
4. **Trace data flow** - Where does the bad value originate?

### Phase 2: Pattern Analysis

1. **Find working examples** - Similar working code in same codebase
2. **Compare against references** - Read reference implementation completely
3. **Identify differences** - What's different between working and broken?

### Phase 3: Hypothesis and Testing

1. **Form single hypothesis** - "I think X is the root cause because Y"
2. **Test minimally** - Make SMALLEST possible change
3. **Verify before continuing** - Did it work? If not, new hypothesis

### Phase 4: Implementation

1. **Create failing test** - Reproduce the bug in a test
2. **Implement single fix** - Address root cause, ONE change
3. **Verify fix** - Test passes? Other tests still pass?
4. **If 3+ fixes failed** - STOP. Question the architecture.

## Red Flags - STOP

- "Quick fix for now"
- "Just try changing X"
- Proposing solutions before investigation
- "One more fix attempt" (after 2+ failures)

**ALL mean: Return to Phase 1.**

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple" | Simple issues have root causes too |
| "Emergency, no time" | Systematic is FASTER than thrashing |
| "I see the problem" | Seeing symptoms ≠ understanding root cause |
| "One more try" (after 2+) | 3+ failures = architectural problem |

## 3-Fix Rule

If you've tried 3 fixes without success:
- STOP attempting more fixes
- Question the architecture
- Discuss with user before continuing

This indicates an architectural problem, not a bug.
```

**Step 3: Validate**

```bash
./validate.sh
```

**Step 4: Commit**

```bash
git add skills/systematic-debugging/
git commit -m "feat: add systematic-debugging skill"
```

---

## Phase 4: Orchestration Skills

### Task 8: Create subagent-driven-development skill

**Files:**
- Create: `skills/subagent-driven-development/SKILL.md`

**Step 1: Create directory**

```bash
mkdir -p skills/subagent-driven-development
```

**Step 2: Create SKILL.md**

```markdown
---
name: subagent-driven-development
description: Orchestrates task execution with fresh subagent per task and two-stage review. Use when executing implementation plans with independent tasks in the current session.
---

# Subagent-Driven Development

Execute plan by dispatching fresh subagent per task, with two-stage review after each.

## Core Principle

Fresh subagent per task + two-stage review (spec then quality) = high quality, fast iteration.

## The Process

For each task in the plan:

### 1. Dispatch Implementer

Use `agents/implementer.md` with:
- Full task text (don't make subagent read plan file)
- Scene-setting context (where this fits, dependencies)
- Working directory

### 2. Answer Questions

If implementer asks questions:
- Answer clearly and completely
- Provide additional context if needed
- Don't rush them into implementation

### 3. Spec Compliance Review

After implementer commits, dispatch `agents/spec-reviewer.md`:
- Provide task requirements
- Provide implementer's report
- **Do NOT proceed until spec review passes**

If issues found → implementer fixes → re-review

### 4. Code Quality Review

**Only after spec compliance passes**, dispatch `agents/code-quality-reviewer.md`:
- Provide what was implemented
- Provide git SHAs (base and head)

If issues found → implementer fixes → re-review

### 5. Mark Complete

Only mark task complete when both reviews pass.

## Red Flags - Never

- Skip reviews (spec OR quality)
- Proceed with unfixed issues
- Start quality review before spec compliance passes
- Trust implementer report without verification
- Move to next task while review has open issues

## Integration

**Required skills:**
- `test-driven-development` - Subagents follow TDD
- `verification-before-completion` - Verify before claiming done

**When complete:**
- Use `finishing-branch` skill to handle merge/PR/cleanup
```

**Step 3: Validate**

```bash
./validate.sh
```

**Step 4: Commit**

```bash
git add skills/subagent-driven-development/
git commit -m "feat: add subagent-driven-development skill"
```

---

### Task 9: Create dispatching-parallel-agents skill

**Files:**
- Create: `skills/dispatching-parallel-agents/SKILL.md`

**Step 1: Create directory**

```bash
mkdir -p skills/dispatching-parallel-agents
```

**Step 2: Create SKILL.md**

```markdown
---
name: dispatching-parallel-agents
description: Dispatches one agent per independent problem domain for concurrent investigation. Use when facing 2+ independent tasks without shared state or dependencies.
---

# Dispatching Parallel Agents

When you have multiple unrelated problems, investigating them sequentially wastes time.

## Core Principle

Dispatch one agent per independent problem domain. Let them work concurrently.

## When to Use

**Use when:**
- 3+ failures with different root causes
- Multiple subsystems broken independently
- Each problem can be understood without context from others
- No shared state between investigations

**Don't use when:**
- Failures are related (fix one might fix others)
- Need to understand full system state
- Agents would interfere (editing same files)

## The Pattern

### 1. Identify Independent Domains

Group by what's broken:
- File A tests: one domain
- File B tests: different domain
- Each domain is independent

### 2. Create Focused Agent Tasks

Each agent gets:
- **Specific scope:** One test file or subsystem
- **Clear goal:** Make these tests pass
- **Constraints:** Don't change other code
- **Expected output:** Summary of findings and fixes

### 3. Dispatch in Parallel

```
Task("Fix file-a.test.ts failures")
Task("Fix file-b.test.ts failures")
// Both run concurrently
```

### 4. Review and Integrate

When agents return:
- Read each summary
- Verify fixes don't conflict
- Run full test suite
- Integrate all changes

## Agent Prompt Structure

Good prompts are:
- **Focused:** One clear problem domain
- **Self-contained:** All context needed
- **Specific about output:** What should agent return?

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| "Fix all the tests" | Specify exact file/subsystem |
| No context | Paste error messages and test names |
| No constraints | "Do NOT change production code" |
| Vague output | "Return summary of root cause and changes" |
```

**Step 3: Validate**

```bash
./validate.sh
```

**Step 4: Commit**

```bash
git add skills/dispatching-parallel-agents/
git commit -m "feat: add dispatching-parallel-agents skill"
```

---

## Phase 5: Workflow Skills

### Task 10: Create using-git-worktrees skill

**Files:**
- Create: `skills/using-git-worktrees/SKILL.md`

**Step 1: Create directory**

```bash
mkdir -p skills/using-git-worktrees
```

**Step 2: Create SKILL.md**

```markdown
---
name: using-git-worktrees
description: Creates isolated git worktrees with smart directory selection and safety verification. Use when starting feature work that needs isolation from current workspace.
---

# Using Git Worktrees

Git worktrees create isolated workspaces sharing the same repository.

## Directory Selection Priority

### 1. Check Existing Directories

```bash
ls -d .worktrees 2>/dev/null   # Preferred (hidden)
ls -d worktrees 2>/dev/null    # Alternative
```

If found, use that directory. If both exist, `.worktrees` wins.

### 2. Check CLAUDE.md

```bash
grep -i "worktree.*director" CLAUDE.md 2>/dev/null
```

If preference specified, use it.

### 3. Ask User

```
No worktree directory found. Where should I create worktrees?

1. .worktrees/ (project-local, hidden)
2. ~/worktrees/<project-name>/ (global location)
```

## Safety Verification

For project-local directories, verify ignored before creating:

```bash
git check-ignore -q .worktrees 2>/dev/null
```

**If NOT ignored:**
1. Add to .gitignore
2. Commit the change
3. Proceed with worktree creation

## Creation Steps

### 1. Detect Project Name

```bash
project=$(basename "$(git rev-parse --show-toplevel)")
```

### 2. Create Worktree

```bash
git worktree add "$path" -b "$BRANCH_NAME"
cd "$path"
```

### 3. Run Project Setup

```bash
# Auto-detect
[ -f package.json ] && npm install
[ -f Cargo.toml ] && cargo build
[ -f requirements.txt ] && pip install -r requirements.txt
[ -f go.mod ] && go mod download
```

### 4. Verify Clean Baseline

Run tests to ensure worktree starts clean.

**If tests fail:** Report failures, ask whether to proceed.
**If tests pass:** Report ready.

### 5. Report Location

```
Worktree ready at <full-path>
Tests passing (<N> tests, 0 failures)
Ready to implement <feature-name>
```

## Red Flags - Never

- Create worktree without verifying it's ignored
- Skip baseline test verification
- Proceed with failing tests without asking
- Assume directory location when ambiguous

## Integration

**Pairs with:**
- `finishing-branch` - Cleanup after work complete
```

**Step 3: Validate**

```bash
./validate.sh
```

**Step 4: Commit**

```bash
git add skills/using-git-worktrees/
git commit -m "feat: add using-git-worktrees skill"
```

---

### Task 11: Create finishing-branch skill

**Files:**
- Create: `skills/finishing-branch/SKILL.md`

**Step 1: Create directory**

```bash
mkdir -p skills/finishing-branch
```

**Step 2: Create SKILL.md**

```markdown
---
name: finishing-branch
description: Guides branch completion with structured options for merge, PR, keep, or discard. Use when implementation is complete and ready to integrate.
---

# Finishing a Development Branch

Guide completion of development work with clear options.

## Core Principle

Verify tests → Present options → Execute choice → Clean up.

## The Process

### Step 1: Verify Tests

```bash
# Run project's test suite
npm test / cargo test / pytest / go test ./...
```

**If tests fail:** Stop. Cannot proceed until tests pass.

**If tests pass:** Continue to Step 2.

### Step 2: Present Options

Present exactly these 4 options:

```
Implementation complete. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```

### Step 3: Execute Choice

**Option 1: Merge Locally**
```bash
git checkout <base-branch>
git pull
git merge <feature-branch>
# Verify tests on merged result
git branch -d <feature-branch>
```
Then: Cleanup worktree

**Option 2: Push and Create PR**
```bash
git push -u origin <feature-branch>
gh pr create --title "<title>" --body "..."
```
Then: Cleanup worktree

**Option 3: Keep As-Is**
Report: "Keeping branch. Worktree preserved."
Don't cleanup worktree.

**Option 4: Discard**
Confirm first:
```
This will permanently delete branch and all commits.
Type 'discard' to confirm.
```
If confirmed:
```bash
git checkout <base-branch>
git branch -D <feature-branch>
```
Then: Cleanup worktree

### Step 4: Cleanup Worktree

For Options 1, 2, 4:
```bash
git worktree remove <worktree-path>
```

For Option 3: Keep worktree.

## Quick Reference

| Option | Merge | Push | Keep Worktree |
|--------|-------|------|---------------|
| 1. Merge locally | ✓ | - | - |
| 2. Create PR | - | ✓ | - |
| 3. Keep as-is | - | - | ✓ |
| 4. Discard | - | - | - |

## Red Flags - Never

- Proceed with failing tests
- Merge without verifying tests on result
- Delete work without confirmation
- Force-push without explicit request
```

**Step 3: Validate**

```bash
./validate.sh
```

**Step 4: Commit**

```bash
git add skills/finishing-branch/
git commit -m "feat: add finishing-branch skill"
```

---

### Task 12: Create writing-skills skill

**Files:**
- Create: `skills/writing-skills/SKILL.md`

**Step 1: Create directory**

```bash
mkdir -p skills/writing-skills
```

**Step 2: Create SKILL.md**

```markdown
---
name: writing-skills
description: Applies TDD approach to skill documentation with pressure testing. Use when creating new skills, editing existing skills, or verifying skills work.
---

# Writing Skills

**Writing skills IS Test-Driven Development applied to process documentation.**

## Core Principle

If you didn't watch an agent fail without the skill, you don't know if the skill teaches the right thing.

## TDD Mapping

| TDD Concept | Skill Creation |
|-------------|----------------|
| Test case | Pressure scenario with subagent |
| Production code | Skill document (SKILL.md) |
| Test fails (RED) | Agent violates rule without skill |
| Test passes (GREEN) | Agent complies with skill present |
| Refactor | Close loopholes while maintaining compliance |

## When to Create

**Create when:**
- Technique wasn't intuitively obvious
- You'd reference this again across projects
- Pattern applies broadly
- Others would benefit

**Don't create for:**
- One-off solutions
- Standard practices documented elsewhere
- Project-specific conventions (put in CLAUDE.md)

## SKILL.md Structure

```markdown
---
name: skill-name-with-hyphens
description: [What it does]. Use when [specific triggering conditions].
---

# Skill Name

## Overview
Core principle in 1-2 sentences.

## When to Use
Bullet list with symptoms and use cases.

## Core Pattern
Before/after or step-by-step.

## Common Mistakes
What goes wrong + fixes.
```

## Description Best Practices

- Format: "[What it does]. Use when [triggers]."
- Include specific triggers/symptoms
- Do NOT summarize the skill's workflow
- Written in third person
- Under 500 characters

**Bad:** "Use for TDD - write test first, watch it fail..."
**Good:** "Use when implementing any feature or bugfix, before writing implementation code"

## The Iron Law

```
NO SKILL WITHOUT A FAILING TEST FIRST
```

Write skill before testing? Delete it. Start over.

## Validation Checklist

- [ ] Name uses lowercase and hyphens only
- [ ] Description starts with "Use when..."
- [ ] Description doesn't summarize workflow
- [ ] Under 500 lines
- [ ] Tested with pressure scenario
- [ ] `./validate.sh` passes
```

**Step 3: Validate**

```bash
./validate.sh
```

**Step 4: Commit**

```bash
git add skills/writing-skills/
git commit -m "feat: add writing-skills skill"
```

---

## Phase 6: Enhancements

### Task 13: Enhance brainstorming skill

**Files:**
- Modify: `skills/brainstorming/SKILL.md`

**Step 1: Read current file**

```bash
cat skills/brainstorming/SKILL.md
```

**Step 2: Update SKILL.md**

Add these sections after "### 3. Identify Constraints":

```markdown
### 4. Present Design Incrementally

When presenting a design or direction:
- Break into sections of 200-300 words
- After each section: "Does this look right so far?"
- Be ready to go back and clarify

### 5. Apply YAGNI Ruthlessly

Before finalizing:
- Review each proposed feature
- Ask: "Is this strictly necessary for the core goal?"
- Remove anything that's "nice to have"
- Simpler is better
```

Update description to:
```yaml
description: Guides ideation and exploration with incremental presentation and YAGNI discipline. Use when starting a feature, exploring options, or generating ideas.
```

**Step 3: Validate**

```bash
./validate.sh
```

**Step 4: Commit**

```bash
git add skills/brainstorming/
git commit -m "enhance: add incremental presentation and YAGNI to brainstorming"
```

---

### Task 14: Update implementing skill references

**Files:**
- Modify: `skills/implementing/SKILL.md`

**Step 1: Read current file**

```bash
cat skills/implementing/SKILL.md
```

**Step 2: Add skill references**

Add after "## Prerequisites" section:

```markdown
## Related Skills

For complex implementations:
- `subagent-driven-development` - Fresh subagent per task with two-stage review
- `test-driven-development` - RED-GREEN-REFACTOR discipline
- `verification-before-completion` - Evidence before claims
```

Update "## Agent Delegation" section to reference new agents:

```markdown
## Agent Delegation

For complex tasks, dispatch specialized agents:

- `agents/implementer.md` - Task implementation with self-review
- `agents/spec-reviewer.md` - Verify implementation matches spec
- `agents/code-quality-reviewer.md` - Verify implementation quality

See `subagent-driven-development` skill for orchestration pattern.
```

**Step 3: Validate**

```bash
./validate.sh
```

**Step 4: Commit**

```bash
git add skills/implementing/
git commit -m "enhance: add skill and agent references to implementing"
```

---

## Phase 7: Final Validation

### Task 15: Full validation and summary

**Step 1: Run full validation**

```bash
./validate.sh
```

Expected: 0 errors

**Step 2: Verify structure**

```bash
echo "=== Skills ===" && ls skills/
echo "=== Agents ===" && ls agents/
```

Expected:
- Skills: 17 directories (9 existing + 8 new)
- Agents: 6 files (3 existing + 3 new)

**Step 3: Git status**

```bash
git log --oneline -15
```

Expected: 14 commits for this implementation

**Step 4: Final commit (if any unstaged changes)**

```bash
git status
```

If clean: Done!

---

## Summary

**New Skills (8):**
1. test-driven-development
2. verification-before-completion
3. systematic-debugging
4. subagent-driven-development
5. dispatching-parallel-agents
6. using-git-worktrees
7. finishing-branch
8. writing-skills

**New Agents (3):**
1. implementer.md
2. spec-reviewer.md
3. code-quality-reviewer.md

**Enhanced (2):**
1. brainstorming - incremental presentation, YAGNI
2. implementing - skill/agent references

**Restructured:**
- agents/ flattened (removed workers/ and specialists/)
