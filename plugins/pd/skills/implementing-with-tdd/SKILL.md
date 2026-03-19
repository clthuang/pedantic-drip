---
name: implementing-with-tdd
description: Enforces RED-GREEN-REFACTOR cycle with rationalization prevention. Use when the user says 'use TDD', 'write tests first', 'red-green-refactor', or 'test-driven'.
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

## Reference Materials

**Advanced Techniques:**
- [Interface Contracts](references/interface-contracts.md) - Design APIs before implementation
- [Testing Anti-Patterns](references/testing-anti-patterns.md) - Common mistakes with mocks and test methods

## Interface-Leading TDD

Beyond basic TDD: design the interface BEFORE writing tests.

1. **Define what the interface should look like** (signatures, contracts)
2. **Write test that uses the interface** as a consumer would
3. **Watch it fail** (interface doesn't exist)
4. **Implement minimal interface** to pass
5. **Refactor internals** without changing interface

See [Interface Contracts](references/interface-contracts.md) for full guide.
