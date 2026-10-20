# Tasks: Add-to-Backlog Command

## Task Overview

| ID | Task | Status | Blocked By |
|----|------|--------|------------|
| T1 | Create command file with frontmatter | done | - |
| T2 | Add input validation logic | done | T1 |
| T3 | Add backlog read/initialize logic | done | T2 |
| T4 | Add entry append and confirm logic | done | T3 |
| T5 | Update CLAUDE.md with backlog reference | done | T4 |
| T6 | Test: first entry creates file | pending | T5 |
| T7 | Test: subsequent entry increments ID | pending | T6 |
| T8 | Test: no argument shows usage | pending | T5 |
| T9 | Test: special characters preserved | pending | T7 |

---

## Task Details

### T1: Create command file with frontmatter

**File:** `commands/add-to-backlog.md`

**Action:** Create file with YAML frontmatter:
```yaml
---
description: Add an item to the backlog. Use for capturing ad-hoc ideas, todos, or fixes during any workflow.
argument-hint: <description>
---
```

**Done when:** File exists with valid frontmatter, no syntax errors.

---

### T2: Add input validation logic

**File:** `commands/add-to-backlog.md`

**Action:** Add instruction block that checks for empty arguments:
- If no description provided: output "Usage: /add-to-backlog <description>" and stop

**Done when:** Command with no args shows usage message.

---

### T3: Add backlog read/initialize logic

**File:** `commands/add-to-backlog.md`

**Action:** Add logic to:
1. Try to read `docs/backlog.md`
2. If file exists: parse to find max ID
3. If file doesn't exist: prepare to create with header template

**Done when:** Logic handles both existing and missing backlog file.

---

### T4: Add entry append and confirm logic

**File:** `commands/add-to-backlog.md`

**Action:** Add logic to:
1. Generate 5-digit ID (max + 1, zero-padded)
2. Generate ISO 8601 timestamp
3. Create table row: `| {id} | {timestamp} | {description} |`
4. If new file: write header + row; else append row
5. Output: `Added to backlog: #{id} - {description}`

**Done when:** Full command logic complete.

---

### T5: Update CLAUDE.md with backlog reference

**File:** `CLAUDE.md`

**Action:** Add to Quick Reference section:
```markdown
**Backlog:** Capture ad-hoc ideas with `/add-to-backlog <description>`. Review at [docs/backlog.md](docs/backlog.md).
```

**Done when:** CLAUDE.md contains backlog reference.

---

### T6: Test: first entry creates file

**Action:** Run `/add-to-backlog Test item one`

**Expected:**
- `docs/backlog.md` created with header
- Entry `00001 | {timestamp} | Test item one` present
- Output: `Added to backlog: #00001 - Test item one`

**Done when:** All conditions met.

---

### T7: Test: subsequent entry increments ID

**Action:** Run `/add-to-backlog Test item two`

**Expected:**
- Entry `00002 | {timestamp} | Test item two` appended
- Previous entry preserved
- Output: `Added to backlog: #00002 - Test item two`

**Done when:** ID incremented correctly, no data loss.

---

### T8: Test: no argument shows usage

**Action:** Run `/add-to-backlog` (no argument)

**Expected:**
- Output: `Usage: /add-to-backlog <description>`
- `docs/backlog.md` not modified

**Done when:** Usage shown, no side effects.

---

### T9: Test: special characters preserved

**Action:** Run `/add-to-backlog Fix the | pipe issue`

**Expected:**
- Entry contains the pipe character (escaped if needed for table)
- No table corruption

**Done when:** Special chars handled gracefully.

---

## Dependency Graph

```
T1 → T2 → T3 → T4 → T5 → T6 → T7 → T9
                      ↘
                       T8
```

## Acceptance Criteria Mapping

| AC | Covered By |
|----|------------|
| AC-1 | T4, T6 |
| AC-2 | T2, T8 |
| AC-3 | T3, T6 |
| AC-4 | T3, T4, T7 |
| AC-5 | T5 |
