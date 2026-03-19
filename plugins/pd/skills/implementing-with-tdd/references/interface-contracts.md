# Interface-Leading TDD

Define contracts before implementation. Test the interface, not the internals.

## Core Principle

**Design the API before writing the code.**

When you write a test first, you're designing the interface. This is deliberate: the test shows how the code will be used before the code exists.

## The Pattern

```
1. Define what the interface should look like (signatures, contracts)
2. Write test that uses the interface as a consumer would
3. Watch it fail (interface doesn't exist)
4. Implement minimal interface to pass
5. Refactor internals without changing interface
```

## Why Interface First?

**Bad (implementation-driven):**
```typescript
// Start with internals, API emerges accidentally
class UserService {
  private db: Database;
  private cache: Cache;

  async getUserById(id: string) {
    // ... implementation details leak into API
    return this._fetchUserWithCacheAndRetry(id, 3, true);
  }
}
```

**Good (interface-driven):**
```typescript
// Start with how consumer uses it
test('returns user by id', async () => {
  const service = new UserService();
  const user = await service.getUser('123');
  expect(user.name).toBe('Alice');
});

// Interface is clean because test designed it
```

## Writing Interface-First Tests

### Step 1: Write the Call You Want to Make

```typescript
test('creates new user', async () => {
  // This IS the interface design
  const user = await createUser({
    name: 'Alice',
    email: 'alice@example.com'
  });

  expect(user.id).toBeDefined();
  expect(user.name).toBe('Alice');
});
```

### Step 2: Let the Test Tell You the Contract

The test above defines:
- Function name: `createUser`
- Input: object with `name` and `email`
- Output: object with `id` and `name`
- Async: returns Promise

### Step 3: Implement to the Contract

```typescript
async function createUser(input: { name: string; email: string }): Promise<User> {
  // Implementation comes AFTER interface is defined by test
}
```

## Contract Documentation

Tests serve as executable documentation of contracts:

```typescript
describe('UserService contract', () => {
  // Input validation
  test('rejects empty name', async () => {
    await expect(createUser({ name: '', email: 'a@b.com' }))
      .rejects.toThrow('name required');
  });

  // Success case
  test('creates user with valid input', async () => {
    const user = await createUser({ name: 'Alice', email: 'a@b.com' });
    expect(user.id).toBeDefined();
  });

  // Error handling
  test('throws on duplicate email', async () => {
    await createUser({ name: 'Alice', email: 'a@b.com' });
    await expect(createUser({ name: 'Bob', email: 'a@b.com' }))
      .rejects.toThrow('email exists');
  });
});
```

## Interface Design Principles

### 1. Test Consumer Perspective

```typescript
// BAD: Tests internal state
test('user added to internal list', () => {
  service.createUser({ name: 'Alice' });
  expect(service._users.length).toBe(1); // Internal!
});

// GOOD: Tests observable behavior
test('created user can be retrieved', () => {
  const created = service.createUser({ name: 'Alice' });
  const found = service.getUser(created.id);
  expect(found.name).toBe('Alice');
});
```

### 2. Design for Change

```typescript
// BAD: Leaky abstraction - test knows too much
test('uses redis for caching', () => {
  service.getUser('123');
  expect(redisClient.get).toHaveBeenCalled(); // Tests implementation
});

// GOOD: Tests behavior, not mechanism
test('second call is faster', async () => {
  await service.getUser('123'); // Cold
  const start = Date.now();
  await service.getUser('123'); // Cached
  expect(Date.now() - start).toBeLessThan(10);
});
```

### 3. Explicit Contracts

```typescript
// BAD: Implicit behavior
function getUser(id) {
  if (!id) return null; // Undocumented
}

// GOOD: Contract made explicit by test
test('throws on missing id', () => {
  expect(() => getUser()).toThrow('id required');
});

test('returns null for unknown id', () => {
  expect(getUser('nonexistent')).toBeNull();
});
```

## When Interface Changes

If you need to change the interface:

1. **Write new test** for new interface
2. **Watch it fail** (old interface doesn't match)
3. **Update implementation** to new interface
4. **Update or remove** old tests

```typescript
// Before: single user
test('returns user', () => {
  expect(getUser('123').name).toBe('Alice');
});

// After: with relationships
test('returns user with friends', () => {
  const user = getUser('123', { include: 'friends' });
  expect(user.friends).toHaveLength(2);
});
```

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Test internals | Couples test to implementation | Test observable behavior |
| Leaky abstraction | Tests know too much | Mock at boundaries |
| Implicit contracts | Behavior undocumented | Write explicit tests |
| Implementation-first | API is afterthought | Write test call first |

## Checklist

Before implementing:
- [ ] Test shows how consumer will call the code
- [ ] Input/output types are clear from test
- [ ] Error cases are explicit tests
- [ ] Test doesn't reference internals
- [ ] Contract is documented by test assertions
