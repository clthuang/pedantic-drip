# Condition-Based Waiting

Wait for the actual condition you care about, not a guess about how long it takes.

## Overview

Flaky tests often guess at timing with arbitrary delays. This creates race conditions where tests pass on fast machines but fail under load or in CI.

**Core principle:** Wait for the actual condition you care about, not a guess about how long it takes.

## When to Use

**Use when:**
- Tests have arbitrary delays (`setTimeout`, `sleep`, `time.sleep()`)
- Tests are flaky (pass sometimes, fail under load)
- Tests timeout when run in parallel
- Waiting for async operations to complete

**Don't use when:**
- Testing actual timing behavior (debounce, throttle intervals)
- Always document WHY if using arbitrary timeout

## Core Pattern

```typescript
// BAD: Guessing at timing
await new Promise(r => setTimeout(r, 50));
const result = getResult();
expect(result).toBeDefined();

// GOOD: Waiting for condition
await waitFor(() => getResult() !== undefined);
const result = getResult();
expect(result).toBeDefined();
```

## Quick Patterns

| Scenario | Pattern |
|----------|---------|
| Wait for event | `waitFor(() => events.find(e => e.type === 'DONE'))` |
| Wait for state | `waitFor(() => machine.state === 'ready')` |
| Wait for count | `waitFor(() => items.length >= 5)` |
| Wait for file | `waitFor(() => fs.existsSync(path))` |
| Complex condition | `waitFor(() => obj.ready && obj.value > 10)` |

## Implementation

Generic polling function:

```typescript
async function waitFor<T>(
  condition: () => T | undefined | null | false,
  description: string,
  timeoutMs = 5000
): Promise<T> {
  const startTime = Date.now();

  while (true) {
    const result = condition();
    if (result) return result;

    if (Date.now() - startTime > timeoutMs) {
      throw new Error(`Timeout waiting for ${description} after ${timeoutMs}ms`);
    }

    await new Promise(r => setTimeout(r, 10)); // Poll every 10ms
  }
}
```

**Usage:**
```typescript
const event = await waitFor(
  () => events.find(e => e.type === 'COMPLETED'),
  'COMPLETED event'
);
```

## Domain-Specific Helpers

Create helpers for common wait patterns:

```typescript
async function waitForEvent(manager, eventType, timeout = 5000) {
  return waitFor(
    () => manager.events.find(e => e.type === eventType),
    `${eventType} event`,
    timeout
  );
}

async function waitForEventCount(manager, eventType, count, timeout = 5000) {
  return waitFor(
    () => {
      const matches = manager.events.filter(e => e.type === eventType);
      return matches.length >= count ? matches : false;
    },
    `${count} ${eventType} events`,
    timeout
  );
}

async function waitForFileExists(path, timeout = 5000) {
  return waitFor(
    () => fs.existsSync(path),
    `file ${path} to exist`,
    timeout
  );
}
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Polling too fast (`setTimeout(check, 1)`) | Poll every 10ms |
| No timeout (loop forever) | Always include timeout with clear error |
| Stale data (cache before loop) | Call getter inside loop for fresh data |
| Vague error message | Include what was being waited for |

## When Arbitrary Timeout IS Correct

```typescript
// Tool ticks every 100ms - need 2 ticks to verify partial output
await waitForEvent(manager, 'TOOL_STARTED'); // First: wait for condition
await new Promise(r => setTimeout(r, 200));   // Then: wait for timed behavior
// 200ms = 2 ticks at 100ms intervals - documented and justified
```

**Requirements for arbitrary timeout:**
1. First wait for triggering condition
2. Based on known timing (not guessing)
3. Comment explaining WHY

## Checklist

When you see arbitrary delays in tests:
- [ ] Is this testing actual timing behavior?
- [ ] If yes: document why timeout value was chosen
- [ ] If no: replace with condition-based waiting
- [ ] Error message explains what was being waited for
- [ ] Timeout is reasonable (not too short, not too long)
