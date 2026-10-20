# Brainstorm: Add-to-Backlog Command

## Problem Statement

During any workflow (implementing, debugging, reviewing), you notice something unrelated - "oh, this function should be refactored" or "we should add tests here later" - but you don't want to lose focus or context-switch.

Need a tool to register ad-hoc ideas, todos, fixes anytime during any workflow process into a centralized backlog.

## Component Type Analysis

| Type | Fit | Reasoning |
|------|-----|-----------|
| **Command** | ✅ Best | Quick invocation, minimal args, fire-and-forget |
| **Skill** | ❌ Poor | Skills guide complex multi-step processes; this is a single action |
| **Agent** | ❌ Poor | Agents do autonomous work; this is user-initiated capture |

**Decision:** Slash command

## Design Decisions

1. **Command name:** `/add-to-backlog`
2. **Storage:** Single file at `docs/backlog.md`
3. **Format:** Markdown table with ID, Timestamp, Description
4. **ID format:** 5-digit incrementing numbers (00001, 00002, etc.)
5. **Retrieval:** Manual file reading; add path to CLAUDE.md for context

## Example Usage

```
/add-to-backlog Add retry logic to API client
```

## Backlog File Format

```markdown
# Backlog

| ID | Timestamp | Description |
|----|-----------|-------------|
| 00001 | 2026-01-30T14:23:00Z | Add retry logic to API client |
| 00002 | 2026-01-30T15:10:00Z | Refactor auth module |
```

## Context Integration

Add to CLAUDE.md:
```markdown
**Backlog:** Capture ad-hoc ideas with `/add-to-backlog <description>`. Review at [docs/backlog.md](docs/backlog.md).
```
