# Persuasion Principles for Skill Design

Psychology of writing skills that actually get followed under pressure.

## Why Skills Get Ignored

Skills fail not because agents can't follow them, but because agents rationalize around them. Understanding persuasion principles helps write skills that resist rationalization.

## Core Principles

### 1. Authority

**Problem:** Agents question instructions when under pressure.

**Solution:** Establish clear authority in the skill.

```markdown
## Bad: Weak authority
Consider writing tests before code.

## Good: Strong authority
THE IRON LAW: No production code without a failing test first.
Write code before test? Delete it. Start over.
```

**Techniques:**
- Use definitive language ("MUST", "NEVER", "THE RULE")
- Name the principle (gives it weight)
- Remove wiggle room (no "consider" or "try to")

### 2. Commitment & Consistency

**Problem:** Agents abandon approaches when things get hard.

**Solution:** Build commitment through checklists and explicit acknowledgment.

```markdown
## Bad: No commitment
Follow TDD principles.

## Good: Explicit commitment
Copy this checklist and check off as you go:
- [ ] I wrote the test FIRST
- [ ] I watched it FAIL
- [ ] I wrote MINIMAL code to pass
- [ ] All tests pass
```

**Techniques:**
- Checklists that require explicit checking
- "Before you proceed, verify:" gates
- Self-review sections

### 3. Social Proof

**Problem:** Agents think rules don't apply to their situation.

**Solution:** Show the rule applies universally.

```markdown
## Bad: Abstract rule
Tests should be written first.

## Good: Universal application
No exceptions. Every feature. Every bugfix. Every "simple" change.
"Too simple to test" = test takes 30 seconds. Do it.
```

**Techniques:**
- List specific exceptions that ARE NOT exceptions
- Address "special cases" directly
- Show the rule applies to exactly the situation they're in

### 4. Scarcity / Loss Aversion

**Problem:** Agents underestimate cost of violations.

**Solution:** Make the cost concrete and immediate.

```markdown
## Bad: Abstract consequence
Skipping tests can cause bugs.

## Good: Concrete cost
Skip TDD = 10x debugging time.
"Quick fix" without tests = 3 hours finding where it broke.
```

**Techniques:**
- Concrete cost comparisons
- "Time saved" vs "time lost" framing
- Reference actual debugging pain

### 5. Unity / Identity

**Problem:** Agents see rules as external constraints.

**Solution:** Frame compliance as identity ("professionals do X").

```markdown
## Bad: External rule
You must write tests.

## Good: Identity framing
This is what separates debugging from engineering.
TDD practitioners don't "skip it this once."
```

**Techniques:**
- "This is how professionals work"
- "This is what quality means"
- Frame compliance as identity, not constraint

## Applying Principles to Skill Sections

### Title and Overview

Use **Authority** - establish the skill as definitive.

```markdown
# The Iron Law of TDD
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.
```

### When to Use

Use **Social Proof** - show universal application.

```markdown
## When to Use
Every feature. Every bugfix. Every refactor.
No exceptions for "simple" changes.
No exceptions for "urgent" fixes.
```

### Process Steps

Use **Commitment** - build explicit checkpoints.

```markdown
## Process
Copy this checklist:
- [ ] Test written FIRST
- [ ] Test FAILS (verify error message)
- [ ] MINIMAL code to pass
- [ ] Test PASSES (verify output)
```

### Common Mistakes / Rationalizations

Use **Loss Aversion** - make costs concrete.

```markdown
## Rationalizations and Their Costs

| Excuse | Reality |
|--------|---------|
| "Too simple" | Simple code breaks. Test: 30 sec. Debug: 3 hours. |
| "I'll test after" | Tests passing immediately prove nothing. |
| "Time pressure" | TDD is faster. Debugging is slower. |
```

### Red Flags

Use **Unity** - frame as professional identity.

```markdown
## Red Flags (Stop and Reconsider)

These thoughts mean you're rationalizing:
- "Just this once" → Professionals don't have exceptions
- "I already know" → Knowing ≠ verified
- "Too urgent" → Urgent problems need MORE discipline, not less
```

## Anti-Patterns

### Weak Language

**Bad:** "Consider", "Try to", "Should", "Generally"
**Good:** "Must", "Always", "Never", "The rule is"

### Abstract Consequences

**Bad:** "This can cause problems"
**Good:** "This costs 3 hours of debugging"

### External Framing

**Bad:** "The rule says you must"
**Good:** "This is what discipline looks like"

### Missing Escape Hatches

**Bad:** Absolute rules with no guidance for true exceptions
**Good:** Clear exceptions + how to recognize them + what to do

```markdown
## True Exceptions (Rare)

If ALL of these are true:
- Literal production emergency
- Fix is single-line
- You will add test within 1 hour

Then: Fix first, test immediately after.
Document why you broke the rule.

If any are false: TDD. No debate.
```

## Checklist: Persuasion-Optimized Skill

- [ ] Uses definitive language (not "consider" or "try")
- [ ] Names the principle (gives it weight)
- [ ] Includes explicit checkpoints/checklist
- [ ] Shows universal application (no "special cases")
- [ ] Makes costs concrete (not abstract)
- [ ] Frames as identity (not external constraint)
- [ ] Addresses common rationalizations directly
- [ ] Provides clear red flags
- [ ] Has rare, well-defined escape hatches
