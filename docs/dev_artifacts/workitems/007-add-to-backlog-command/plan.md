# Implementation Plan: Add-to-Backlog Command

## Overview

Implementation of `/add-to-backlog` command with 3 deliverables:
1. Command file (`commands/add-to-backlog.md`)
2. Initial backlog file structure (created on first use)
3. CLAUDE.md context integration

## Implementation Steps

### Step 1: Create Command File

**File:** `commands/add-to-backlog.md`

**Content:**
- YAML frontmatter with description and argument-hint
- Instruction block for Claude to execute when invoked
- Input validation logic
- File read/create/append logic
- Confirmation output

**Dependencies:** None (first step)

**Acceptance Criteria:** AC-1, AC-2, AC-3, AC-4

---

### Step 2: Update CLAUDE.md

**File:** `CLAUDE.md`

**Change:** Add backlog reference to Quick Reference section

**Content:**
```markdown
**Backlog:** Capture ad-hoc ideas with `/add-to-backlog <description>`. Review at [docs/backlog.md](docs/backlog.md).
```

**Dependencies:** Step 1 (command must exist before documenting)

**Acceptance Criteria:** AC-5

---

### Step 3: Manual Testing

**Test Cases:**

| # | Scenario | Command | Expected |
|---|----------|---------|----------|
| 1 | First entry (no file) | `/add-to-backlog Test item` | Creates file, adds #00001 |
| 2 | Subsequent entry | `/add-to-backlog Second item` | Adds #00002 |
| 3 | No argument | `/add-to-backlog` | Shows usage message |
| 4 | Special chars | `/add-to-backlog Fix the \| pipe issue` | Entry preserved |

**Dependencies:** Steps 1-2

**Acceptance Criteria:** All (AC-1 through AC-5)

---

## Dependency Graph

```
Step 1: Create Command
    │
    ▼
Step 2: Update CLAUDE.md
    │
    ▼
Step 3: Manual Testing
```

## Risk Mitigation

| Risk | Mitigation in Plan |
|------|-------------------|
| Pipe chars in description | Test case #4 covers; escape if needed |
| File not found error | Command handles by creating file |

## Estimated Complexity

- Step 1: Medium (core logic)
- Step 2: Trivial (one-line addition)
- Step 3: Low (manual verification)

**Total:** ~30 lines of new code
