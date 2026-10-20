# Design: Change Workflow Ordering

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      USER ENTRY POINTS                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  /brainstorm "idea"              /create-feature "idea"         │
│  (Primary - recommended)         (Alternative - skip explore)   │
│         │                                │                      │
│         ▼                                ▼                      │
│  ┌─────────────────┐              ┌─────────────────┐          │
│  │  Standalone     │              │  Direct Feature │          │
│  │  Exploration    │              │  Creation       │          │
│  │                 │              │                 │          │
│  │  scratch file   │              │  folder+meta    │          │
│  │  created in     │              │  worktree       │          │
│  │  docs/brainstorms/             │                 │          │
│  └────────┬────────┘              └────────┬────────┘          │
│           │                                │                    │
│           ▼                                │                    │
│  ┌─────────────────┐                       │                    │
│  │ "Turn into      │                       │                    │
│  │  feature?"      │                       │                    │
│  └────────┬────────┘                       │                    │
│           │                                │                    │
│      Yes  │  No                            │                    │
│           │   │                            │                    │
│           │   └──► stays in scratch        │                    │
│           ▼                                │                    │
│  ┌─────────────────┐                       │                    │
│  │ Feature Creation│◄──────────────────────┘                    │
│  │ (internal)      │                                            │
│  │                 │                                            │
│  │ - mode select   │                                            │
│  │ - folder create │                                            │
│  │ - worktree      │                                            │
│  │ - move file     │                                            │
│  └────────┬────────┘                                            │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                            │
│  │    /specify     │◄─── if called without feature:             │
│  │                 │     "No feature. /brainstorm first?"       │
│  └─────────────────┘                                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Component Changes

### 1. commands/brainstorm.md

**Current behavior:** Requires active feature, delegates to skill

**New behavior:**
```
1. Check for active feature in docs/features/
2. IF active feature exists:
   - Ask: "Add to existing feature or start new brainstorm?"
   - If add: delegate to skill with feature context
   - If new: proceed as standalone
3. IF no active feature (standalone mode):
   - Create scratch file: docs/brainstorms/YYYYMMDD-HHMMSS-{slug}.md
   - Run brainstorming exploration
   - At end, ask: "Turn this into a feature?"
   - If yes: trigger feature creation flow
   - If no: inform user file saved for later
```

**Command frontmatter changes:**
```yaml
---
description: Start brainstorming - works with or without active feature
argument-hint: [topic or idea to explore]
---
```

### 2. skills/brainstorming/SKILL.md

**Current behavior:** Assumes feature context exists

**New behavior:**
- Add `## Standalone Mode` section
- Handle scratch file creation/naming
- Add promotion prompt logic
- Add feature creation steps (mode, folder, worktree, meta)

**Key additions:**
```markdown
## Standalone Mode (No Active Feature)

When no feature context exists:

### 1. Create Scratch File
- Generate timestamp: YYYYMMDD-HHMMSS
- Generate slug from topic (lowercase, hyphens, max 30 chars)
- Create: `docs/dev_artifacts/brainstorms/{timestamp}-{slug}.md`

### 2. Run Exploration
(Same as existing process)

### 3. Promotion Prompt
At end of session:
"Turn this into a feature? (y/n)"

If yes:
1. Ask for mode (suggest based on scope)
2. Generate feature ID (highest in docs/features/ + 1)
3. Create folder: docs/features/{id}-{slug}/
4. Handle worktree based on mode
5. Move scratch file to feature folder as brainstorm.md
6. Create .meta.json
7. Auto-invoke /specify

If no:
- Inform: "Saved to docs/brainstorms/{filename}. You can revisit later."
```

### 3. commands/create-feature.md

**Current behavior:** Primary entry point, tells user to run /brainstorm next

**New behavior:**
- Alternative entry point (not recommended flow)
- After creation, auto-invoke /specify (not /brainstorm)
- Update messaging to reflect this is for skipping exploration

**Key changes:**
```markdown
## Output

```
✓ Feature {id}-{slug} created
  Mode: {mode}
  Folder: docs/features/{id}-{slug}/
  Worktree: ../{project}-{id}-{slug} (if created)

  Note: Skipped brainstorming. Proceeding to /specify.
```

## Auto-Continue

After creation, invoke /specify skill.
```

### 4. commands/specify.md

**Current behavior:** Assumes feature exists, delegates to skill

**New behavior:**
```
1. Check for active feature
2. IF no feature:
   - Prompt: "No active feature found."
   - Ask: "Would you like to /brainstorm to explore ideas first?"
   - Do NOT auto-create feature
3. IF feature exists:
   - Check for brainstorm.md, read if present
   - Delegate to skill
```

### 5. skills/specifying/SKILL.md

**Current behavior:** Reads brainstorm.md if exists

**New behavior:** Same, but update Prerequisites section:
```markdown
## Prerequisites

Check for feature context:
- Look for feature folder in `docs/dev_artifacts/workitems/`
- If not found:
  - "No active feature. Would you like to /brainstorm first to explore ideas?"
  - Do NOT proceed without user confirmation
- If found: Continue with specification
```

### 6. NEW: commands/cleanup-brainstorms.md

```yaml
---
description: List and delete old brainstorm scratch files
---
```

**Behavior:**
```markdown
# /cleanup-brainstorms Command

Manage brainstorm scratch files.

## Process

1. List all files in `docs/dev_artifacts/brainstorms/` (exclude .gitkeep)
2. Display with dates:
   ```
   Brainstorm files:
   1. 20260129-143052-api-caching.md (today)
   2. 20260128-091530-auth-rework.md (yesterday)
   3. 20260115-220000-old-idea.md (14 days ago)

   Enter numbers to delete (comma-separated), or 'q' to quit:
   ```
3. Confirm before deletion
4. Delete selected files
```

### 7. Directory Structure

Create `docs/dev_artifacts/brainstorms/.gitkeep`:
```
(empty file to ensure directory exists in git)
```

### 8. Rename /plan to /create-plan

**Problem:** `/plan` collides with Claude Code's built-in plan mode command.

**Solution:** Rename command to `/create-plan`.

**File changes:**
```
commands/plan.md → commands/create-plan.md
```

**Frontmatter update:**
```yaml
---
description: Create implementation plan for current feature
---
```

**Reference updates:**

| File | Line | Change |
|------|------|--------|
| `skills/designing/SKILL.md` | 121 | `/plan` → `/create-plan` |
| `skills/breaking-down-tasks/SKILL.md` | 13 | `/plan` → `/create-plan` |
| `README.md` | 72, 166 | `/plan` → `/create-plan` |

**Note:** Output artifact remains `plan.md` - only the command name changes.

## Data Flow

### Scratch File Format

`docs/dev_artifacts/brainstorms/YYYYMMDD-HHMMSS-{slug}.md`:
```markdown
# Brainstorm: {Topic}

## Problem Statement
{captured during exploration}

## Goals
- {Goal 1}

## Approaches Considered
...

## Chosen Direction
...

## Open Questions
...

---
_Created: {ISO timestamp}_
_Status: Not promoted to feature_
```

### Feature Metadata (.meta.json)

No changes to structure, but add `brainstorm_source` field:
```json
{
  "id": "003",
  "name": "api-caching",
  "mode": "standard",
  "created": "2026-01-29T14:30:52Z",
  "worktree": "../my-ai-setup-003-api-caching",
  "brainstorm_source": "docs/brainstorms/20260129-143052-api-caching.md"
}
```

## Helper Functions

### generate_timestamp()
```
Output: "YYYYMMDD-HHMMSS" format
Example: "20260129-143052"
```

### generate_slug(topic)
```
Input: "API caching for better performance"
Output: "api-caching-for-better"
Rules:
- Lowercase
- Replace spaces/special chars with hyphens
- Max 30 characters
- Trim trailing hyphens
```

### get_next_feature_id()
```
Scan docs/features/*/
Extract numeric prefixes
Return max + 1, zero-padded to 3 digits
```

## Error Handling

| Scenario | Response |
|----------|----------|
| docs/brainstorms/ doesn't exist | Create it with .gitkeep |
| Scratch file write fails | Error message, don't lose conversation content |
| Feature folder already exists | Append numeric suffix (003-slug-2) |
| Worktree creation fails | Warn user, continue without worktree |
| Move file fails | Copy then delete (safer), warn if delete fails |

## Testing Considerations

1. **Standalone brainstorm flow**
   - Verify scratch file created with correct naming
   - Verify promotion creates feature correctly
   - Verify file moved (not copied)

2. **Context-aware behavior**
   - With feature: asks add vs new
   - Without feature: standalone mode

3. **Edge cases**
   - Empty topic (generate generic slug)
   - Very long topic (truncation)
   - Special characters in topic

4. **Command rename**
   - `/create-plan` invokes planning skill (not built-in plan mode)
   - All workflow references updated

## Migration

No migration needed - existing features unaffected. New workflow is additive.
