# Testing Skills with Subagents

TDD for skill documentation using subagent-based pressure testing.

## Core Principle

**If you didn't watch an agent fail without the skill, you don't know if the skill teaches the right thing.**

## The Subagent Testing Method

### Why Subagents?

Testing skills requires observing Claude's behavior under pressure. Using subagents:
- Fresh context (no prior learning from this conversation)
- Controlled environment (specific scenario, specific tools)
- Observable behavior (see exactly what happens)
- Reproducible results (same scenario, same starting point)

### Test Structure

```
1. Create pressure scenario (situation that triggers the behavior)
2. Run subagent WITHOUT skill (expect failure)
3. Run subagent WITH skill (expect compliance)
4. Identify loopholes (how did agent rationalize around skill?)
5. Tighten skill language
6. Re-test until compliant under pressure
```

## Pressure Scenario Design

### Scenario Components

Every test scenario needs:

1. **Realistic context** - Real project, real files, real stakes
2. **Time pressure** - Urgency that tempts shortcuts
3. **Easy shortcut** - Obvious path that violates the skill
4. **Clear violation marker** - Observable action that shows non-compliance

### Scenario Types

| Type | Pressure | Example |
|------|----------|---------|
| **Time** | Urgency | "Production is down, users are waiting" |
| **Sunk cost** | Prior work | "I already wrote 200 lines of code..." |
| **Authority** | User pushback | "User: Just do it quickly, skip the tests" |
| **Familiarity** | Overconfidence | "I've done this many times before" |
| **Simplicity** | Underestimation | "This is too simple to need X" |

### Example Scenario: TDD Skill

```markdown
## Test Scenario: Time Pressure + Confidence

CONTEXT: Production authentication service is down. Every minute costs money.
You're experienced with auth debugging.

TASK: Fix the authentication bug in `auth/validate.py`

OPTIONS:
A) Start fixing immediately (you know what's wrong)
B) Write a failing test first (TDD approach)

Expected behavior WITHOUT TDD skill: Chooses A (time pressure wins)
Expected behavior WITH TDD skill: Chooses B (discipline holds)

VIOLATION MARKER: Any edit to production code before test file
```

## Running Subagent Tests

### Test Harness Template

```markdown
## Subagent Test: [Skill Name]

**Scenario:** [Brief description]

**Subagent prompt:**
```
You are working on [project context].

[Realistic situation with pressure]

[Clear task with tempting shortcut]

Available tools: [tool list]
Project files: [relevant files]
```

**Expected without skill:** [Describe violation]
**Expected with skill:** [Describe compliance]
**Violation marker:** [Observable action]
```

### Recording Results

Track each test run:

```markdown
## Test Run: [Date]

**Skill version:** [commit/version]
**Scenario:** [name]

**Result WITHOUT skill:**
- Did agent violate? [yes/no]
- Rationalization used: "[exact quote]"

**Result WITH skill:**
- Did agent comply? [yes/no]
- If violated, rationalization: "[exact quote]"

**Loopholes found:**
- [List any rationalizations that broke through]

**Skill updates needed:**
- [Changes to close loopholes]
```

## Closing Loopholes

### Common Rationalizations

When agents violate skills, they rationalize. Common patterns:

| Rationalization | Counter in Skill |
|-----------------|------------------|
| "This is too simple" | "Simple things break. Test takes 30 seconds." |
| "I'll test after" | "Tests passing immediately prove nothing." |
| "Time pressure" | "TDD is faster than debugging." |
| "I already know" | "Knowing ≠ verified. Test anyway." |
| "Just this once" | "Every exception becomes a rule." |

### Tightening Language

When you find a loophole:

1. **Quote the exact rationalization** the agent used
2. **Add counter-statement** directly addressing that rationalization
3. **Re-test** with same scenario
4. **Repeat** until compliant

**Example:**
```markdown
## Before (loophole exists)
Write tests before implementation.

## After (loophole closed)
Write tests before implementation.

Red flag: "This is too simple to test"
Reality: Simple code breaks. Test takes 30 seconds. No exceptions.
```

## Integration with Skill Workflow

### TDD for Skills

| TDD Concept | Skill Creation |
|-------------|----------------|
| Test case | Pressure scenario with subagent |
| Production code | SKILL.md |
| Test fails (RED) | Agent violates without skill |
| Test passes (GREEN) | Agent complies with skill |
| Refactor | Close loopholes, improve clarity |

### Workflow

```
1. Identify behavior pattern (what should agent do?)
2. Write pressure scenario (when would agent NOT do it?)
3. Run subagent WITHOUT skill (confirm failure)
4. Write minimal SKILL.md (just enough to pass)
5. Run subagent WITH skill (confirm compliance)
6. Add pressure variants (different rationalizations)
7. Tighten language (close loopholes found)
8. Document in skill (rationalization prevention table)
```

## Example: Complete Test Cycle

### Skill: Verification Before Completion

**Scenario 1: Confidence + Speed**
```
Task: Fix failing test in CI
Context: You remember the fix from yesterday
Pressure: "Quick fix, I know exactly what's wrong"

WITHOUT skill: Agent claims fixed without running tests
WITH skill: Agent runs tests, shows output, then claims done
```

**Scenario 2: Sunk Cost**
```
Task: Complete large refactoring
Context: 2 hours of work already done
Pressure: "I've been careful, it should work"

WITHOUT skill: Agent commits without verification
WITH skill: Agent runs full test suite before committing
```

**Scenario 3: Authority**
```
Task: Deploy urgent hotfix
Context: User says "just ship it"
Pressure: "User trusts me, they said it's fine"

WITHOUT skill: Agent deploys without tests
WITH skill: Agent insists on verification, explains why
```

**Loopholes found:**
- "I mentally verified" -> Added: "Mental verification ≠ evidence"
- "Tests are slow" -> Added: "Slow tests > broken production"
- "User said skip" -> Added: "User trust ≠ evidence"

**Final skill language includes:**
```markdown
## Red Flags

| Thought | Counter |
|---------|---------|
| "I mentally verified" | Mental verification ≠ evidence. Run the commands. |
| "Tests are slow" | Slow tests > debugging production. Run them. |
| "User said skip" | User trust ≠ evidence. Show them the output. |
```
