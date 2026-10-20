# Design: Backlog to Feature Link

## Overview

Extend `/iflow:create-feature` command to detect when a feature originates from a backlog item and automatically remove that item from the backlog while preserving traceability.

## Architecture

### Component: create-feature.md

Single file modification to the existing command at:
```
plugins/iflow/commands/create-feature.md
```

No new files needed. The change adds a new section to the existing command workflow.

## Data Flow

```
brainstorm.md (with *Source: Backlog #XXXXX*)
       │
       ▼
┌─────────────────────────────┐
│   /iflow:create-feature     │
│                             │
│  1. Read brainstorm content │
│  2. Parse backlog source    │
│  3. Create .meta.json       │◄── includes backlog_source
│  4. Remove from backlog.md  │
└─────────────────────────────┘
       │
       ▼
docs/backlog.md (row removed)
```

## Interface Specification

### Input: Brainstorm Header Pattern

**Location:** Brainstorm file content (passed to create-feature or read from `brainstorm_source` path)

**Format:**
```markdown
*Source: Backlog #XXXXX*
```

**Regex:** `\*Source: Backlog #(\d{5})\*`

**Capture group:** 5-digit backlog ID (e.g., "00001")

### Output: Meta JSON Field

**File:** `docs/dev_artifacts/workitems/{id}-{slug}/.meta.json`

**New field:**
```json
{
  "backlog_source": "00001"
}
```

**Placement:** Top-level field, added only when backlog source detected.

### Backlog Table Format

**File:** `docs/backlog.md`

**Structure:**
```markdown
# Backlog

| ID | Timestamp | Description |
|----|-----------|-------------|
| 00001 | 2026-01-31T10:45:00Z | description here |
```

**Row pattern to match:** `| {ID} |` where ID matches extracted backlog source

**Removal:** Delete entire table row including the leading `|` and trailing `|`

## Algorithm

### Step 1: Parse Backlog Source

```
FUNCTION parseBacklogSource(brainstormContent):
    pattern = /\*Source: Backlog #(\d{5})\*/
    match = pattern.match(brainstormContent)
    IF match:
        RETURN match.group(1)  # e.g., "00001"
    ELSE:
        RETURN null
```

### Step 2: Store in Meta

```
FUNCTION addBacklogSourceToMeta(metaJson, backlogId):
    IF backlogId is not null:
        metaJson["backlog_source"] = backlogId
    RETURN metaJson
```

### Step 3: Remove from Backlog

```
FUNCTION removeFromBacklog(backlogId):
    IF backlogId is null:
        RETURN  # No action needed

    content = READ "docs/backlog.md"
    rowPattern = /^\| {backlogId} \|.*$/m

    IF rowPattern.match(content):
        newContent = content.replace(rowPattern, "")
        # Also remove any resulting blank lines
        WRITE newContent to "docs/backlog.md"
        PRINT "Removed backlog item #{backlogId}"
    ELSE:
        PRINT "Warning: Backlog item #{backlogId} not found in docs/backlog.md"
```

## Integration Points

### Where to Insert in create-feature.md

After "Create Metadata File" section, before "State Tracking" section:

```markdown
## Handle Backlog Source

If feature was promoted from a brainstorm that originated from a backlog item:

1. **Read brainstorm content** from `brainstorm_source` path in context
2. **Parse for backlog source** using pattern `\*Source: Backlog #(\d{5})\*`
3. **If found:**
   - Add `"backlog_source": "{id}"` to `.meta.json`
   - Read `docs/backlog.md`
   - Find row matching `| {id} |`
   - Remove that row
   - Write updated backlog
   - Display: `Linked from backlog item #{id} (removed from backlog)`
4. **If pattern not found:** No action, continue normally
5. **If ID found but row missing:** Display warning, continue with feature creation
```

### Accessing Brainstorm Content

The create-feature command receives context including `brainstorm_source` path when invoked from the brainstorming promotion flow. Read this file to check for backlog source.

When invoked directly (not from brainstorm), `brainstorm_source` may not exist - skip backlog handling entirely.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| No brainstorm_source in context | Skip backlog handling, continue normally |
| Brainstorm file doesn't exist | Skip backlog handling, continue normally |
| No backlog pattern in brainstorm | Skip backlog handling, continue normally |
| Backlog ID found but row missing | Display warning, store ID in meta, continue |
| backlog.md doesn't exist | Display warning, store ID in meta, continue |

## Risks

| Risk | Mitigation |
|------|------------|
| Accidentally removing wrong row | Exact ID match on first column only |
| Partial file write corruption | Write complete content atomically |
| Brainstorm format changes | Pattern is well-defined, backward compatible |

## Testing Considerations

1. **Happy path:** Brainstorm with backlog source → feature created → backlog row removed
2. **No source:** Brainstorm without backlog source → no changes to backlog
3. **Missing row:** Backlog ID in brainstorm but row doesn't exist → warning shown
4. **Direct invocation:** /iflow:create-feature without brainstorm context → unchanged behavior
