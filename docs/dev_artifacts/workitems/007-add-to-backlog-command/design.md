# Design: Add-to-Backlog Command

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User Invocation                         │
│                  /add-to-backlog <desc>                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│               Command: add-to-backlog.md                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Validate  │→ │  Read/Init  │→ │  Append & Confirm   │  │
│  │    Input    │  │   Backlog   │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   docs/backlog.md                           │
│                  (Persistent Storage)                       │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. Command File

**Location:** `commands/add-to-backlog.md`

**Frontmatter:**
```yaml
---
description: Add an item to the backlog. Use for capturing ad-hoc ideas, todos, or fixes during any workflow.
argument-hint: <description>
---
```

**Responsibilities:**
- Parse user input (description text)
- Validate required argument present
- Orchestrate read/write to backlog file
- Output confirmation message

### 2. Backlog Storage

**Location:** `docs/backlog.md`

**Initial State (when created):**
```markdown
# Backlog

| ID | Timestamp | Description |
|----|-----------|-------------|
```

## Processing Logic

### Step 1: Input Validation

```
IF arguments empty:
  OUTPUT "Usage: /add-to-backlog <description>"
  STOP
```

### Step 2: Read or Initialize Backlog

```
IF docs/backlog.md exists:
  READ file content
  PARSE existing entries to find max ID
  SET next_id = max_id + 1
ELSE:
  SET next_id = 1
  CREATE file with header template
```

### Step 3: Generate Entry

```
SET id = zero-pad(next_id, 5)         # "00001"
SET timestamp = current_time_iso8601() # "2026-01-30T14:23:00Z"
SET description = user_input
SET row = "| {id} | {timestamp} | {description} |"
```

### Step 4: Append and Confirm

```
APPEND row to docs/backlog.md
OUTPUT "Added to backlog: #{id} - {description}"
```

## ID Generation Algorithm

```
function getNextId(fileContent):
  if fileContent is empty or no table rows:
    return 1

  ids = extract all IDs from table rows (regex: /^\| (\d{5}) \|/)
  maxId = max(ids) or 0
  return maxId + 1

function formatId(num):
  return String(num).padStart(5, '0')
```

**Edge Cases:**
- Empty file → ID 00001
- Gap in IDs (00001, 00003) → Next is 00004 (max + 1, not gap-fill)
- Corrupted rows (no valid ID) → Skip, use max of valid IDs

## File Operations

| Operation | Tool | Error Handling |
|-----------|------|----------------|
| Check file exists | Read | Handle "file not found" |
| Read content | Read | Parse failure → treat as empty |
| Create file | Write | Permission error → report to user |
| Append entry | Edit | Permission error → report to user |

## Interface Contract

### Input

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| description | string | Yes | Free-form text for backlog item |

### Output

| Scenario | Output |
|----------|--------|
| Success | `Added to backlog: #00001 - {description}` |
| Missing arg | `Usage: /add-to-backlog <description>` |
| Write error | `Error: Cannot write to docs/backlog.md` |

## CLAUDE.md Integration

**Addition to Quick Reference section:**
```markdown
**Backlog:** Capture ad-hoc ideas with `/add-to-backlog <description>`. Review at [docs/backlog.md](docs/backlog.md).
```

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Read tool | Claude Code built-in | For reading backlog file |
| Write tool | Claude Code built-in | For creating backlog file |
| Edit tool | Claude Code built-in | For appending entries |

No external dependencies.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| File corruption from malformed append | Low | Medium | Use Edit tool with precise targeting |
| Race condition on concurrent writes | Very Low | Low | Single-user CLI; defer handling |
| ID overflow at 99999 | Very Low | Low | Would require 100K entries; accept |

## Testing Considerations

1. **Empty backlog** - First entry gets ID 00001
2. **Existing entries** - Next ID is max + 1
3. **No argument** - Shows usage message
4. **File doesn't exist** - Creates with header
5. **Special characters in description** - Preserved in markdown (pipes escaped if present)
