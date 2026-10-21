# Specification: Add-to-Backlog Command

## Overview

A slash command that captures ad-hoc ideas, todos, and fixes into a centralized backlog file during any workflow, enabling users to note items without losing focus.

## Requirements

### Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | Command `/add-to-backlog` accepts a text description as argument | Must |
| FR-2 | Appends entry to `docs/backlog.md` with auto-generated 5-digit ID | Must |
| FR-3 | Includes ISO 8601 timestamp for each entry | Must |
| FR-4 | Creates `docs/backlog.md` with header if file doesn't exist | Must |
| FR-5 | Determines next ID by reading existing entries (max ID + 1) | Must |
| FR-6 | Preserves existing backlog entries when appending | Must |

### Non-Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-1 | Command executes in under 1 second | Should |
| NFR-2 | No external dependencies beyond Claude Code | Must |
| NFR-3 | Works on macOS and Linux | Must |

## Scope

### In Scope

- `/add-to-backlog` command implementation
- Backlog file creation and management
- CLAUDE.md update with backlog reference

### Out of Scope

- Backlog viewing/listing command
- Backlog item deletion or editing
- Categories or tags
- Priority levels
- Integration with external issue trackers

## User Interaction

### Command Invocation

```
/add-to-backlog <description>
```

**Arguments:**
- `description` (required): Free-form text describing the backlog item

### Success Output

```
Added to backlog: #00001 - Add retry logic to API client
```

### Error Handling

| Condition | Response |
|-----------|----------|
| No description provided | "Usage: /add-to-backlog <description>" |
| Write permission error | "Error: Cannot write to docs/backlog.md" |

## Data Format

### Backlog File Structure

**Location:** `docs/backlog.md`

**Format:**
```markdown
# Backlog

| ID | Timestamp | Description |
|----|-----------|-------------|
| 00001 | 2026-01-30T14:23:00Z | Add retry logic to API client |
| 00002 | 2026-01-30T15:10:00Z | Refactor auth module |
```

### Entry Fields

| Field | Format | Example |
|-------|--------|---------|
| ID | 5-digit zero-padded integer | `00001` |
| Timestamp | ISO 8601 UTC | `2026-01-30T14:23:00Z` |
| Description | Free-form text | `Add retry logic to API client` |

## Acceptance Criteria

1. **AC-1:** Running `/add-to-backlog Fix the login bug` creates an entry in `docs/backlog.md` with a unique 5-digit ID, current timestamp, and the provided description.

2. **AC-2:** Running `/add-to-backlog` with no argument displays usage message without modifying backlog.

3. **AC-3:** When `docs/backlog.md` doesn't exist, command creates it with proper header before adding entry.

4. **AC-4:** When backlog has entries 00001-00005, next entry gets ID 00006.

5. **AC-5:** After implementation, CLAUDE.md contains reference to `/add-to-backlog` command and backlog file location.

## Dependencies

- None (standalone command)

## Risks

| Risk | Mitigation |
|------|------------|
| Concurrent writes could corrupt file | Low probability for single-user CLI tool; defer handling |
| Large backlog could slow ID calculation | Accept for now; optimize if needed later |
