---
name: systematic-debugging
description: Guides four-phase root cause investigation. Use when the user says 'debug this', 'find root cause', 'investigate failure', or 'why is this broken'.
---

# Systematic Debugging

Random fixes waste time and create new bugs.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Stage 1, you cannot propose fixes.

## The Four Phases

### Stage 1: Root Cause Investigation

**Before ANY fix:**

1. **Read error messages carefully** - They often contain the solution
2. **Reproduce consistently** - Can you trigger it reliably?
3. **Check recent changes** - What changed that could cause this?
4. **Trace data flow** - Where does the bad value originate?

### Stage 2: Pattern Analysis

1. **Find working examples** - Similar working code in same codebase
2. **Compare against references** - Read reference implementation completely
3. **Identify differences** - What's different between working and broken?

### Stage 3: Hypothesis and Testing

1. **Form single hypothesis** - "I think X is the root cause because Y"
2. **Test minimally** - Make SMALLEST possible change
3. **Verify before continuing** - Did it work? If not, new hypothesis

### Stage 4: Implementation

1. **Create failing test** - Reproduce the bug in a test
2. **Implement single fix** - Address root cause, ONE change
3. **Verify fix** - Test passes? Other tests still pass?
4. **If 3+ fixes failed** - STOP. Question the architecture.

## Red Flags - STOP

- "Quick fix for now"
- "Just try changing X"
- Proposing solutions before investigation
- "One more fix attempt" (after 2+ failures)

**ALL mean: Return to Stage 1.**

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

## Reference Materials

**Deep Dive Techniques:**
- [Root Cause Tracing](references/root-cause-tracing.md) - Trace backward through call chains
- [Defense in Depth](references/defense-in-depth.md) - Multi-layer validation
- [Condition-Based Waiting](references/condition-based-waiting.md) - Fix flaky tests

**Scripts:**
- [find-polluter.sh](scripts/find-polluter.sh) - Find which test creates pollution

## Quick Reference: Tracing Techniques

| Technique | When to Use |
|-----------|-------------|
| Stack trace logging | Bug deep in execution |
| `console.error()` | Tests suppress logger |
| `new Error().stack` | See complete call chain |
| Bisection script | Unknown test pollution |

## Quick Reference: Defense Layers

| Layer | Purpose |
|-------|---------|
| Entry validation | Reject invalid at API boundary |
| Business logic | Ensure data makes sense for operation |
| Environment guards | Prevent dangerous ops in test/prod |
| Debug instrumentation | Capture context for forensics |

## Tooling Friction Escape Hatches

| Symptom | Escape Hatch |
|---------|-------------|
| Edit `old_string` fails on text containing non-ASCII characters that visually match ASCII (e.g. fullwidth digits `０１２` vs `012`, NEL U+0085 vs space, NBSP U+00A0 vs space) | Switch immediately to Python read-modify-write with byte-anchor assertions on adjacent line numbers. Generate non-ASCII chars at runtime via `chr(0x85)` etc. — do **not** embed them in the script source, since Write/Edit may strip them. |
| Write/Edit silently strips control bytes from script source | Generate the byte at runtime: `NEL = chr(0x85)`, then concatenate. Verify post-write via `count` or `ord()` assertion before trusting the file. |
| Edit retried 2-3 times with variant strings | Stop iterating. The mismatch is byte-level, not visible. Switch to Python RMW. |

## Related Skills

- [root-cause-analysis](../root-cause-analysis/SKILL.md) - Formal 6-phase RCA with 3+ hypotheses, verification scripts, and causal DAG. Use when 3+ fix attempts have failed.
