# Implementation Plan: Backlog to Feature Link

## Summary

Add backlog source handling to `/iflow:create-feature` command. Single file modification with three logical steps.

## Dependencies

```
[Step 1] ──► [Step 2] ──► [Step 3]
```

All steps are sequential - each builds on the previous.

## Steps

### Step 1: Add "Handle Backlog Source" Section

**File:** `plugins/iflow/commands/create-feature.md`

**Location:** After "Create Metadata File" section (line ~71), before "State Tracking" section

**Content to add:**

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
5. **If ID found but row missing:** Display warning `⚠️ Backlog item #{id} not found in docs/backlog.md`, continue with feature creation
```

### Step 2: Update Meta JSON Template

**File:** `plugins/iflow/commands/create-feature.md`

**Location:** "Create Metadata File" section, JSON template

**Change:** Add comment indicating optional `backlog_source` field

Update the JSON template to show:
```json
{
  "id": "{id}",
  "slug": "{slug}",
  "mode": "{selected-mode}",
  "status": "active",
  "created": "{ISO timestamp}",
  "branch": "feature/{id}-{slug}",
  "brainstorm_source": "{path-to-brainstorm-if-promoted}"
}
```

Note: `backlog_source` is added dynamically by Handle Backlog Source step, not in template.

### Step 3: Update Output Message

**File:** `plugins/iflow/commands/create-feature.md`

**Location:** "Output" section

**Change:** Add conditional line for backlog linkage

Update output template to include:
```
✓ Feature {id}-{slug} created
  Mode: {mode}
  Folder: docs/features/{id}-{slug}/
  Branch: feature/{id}-{slug}
  Linked from: Backlog #{backlog_id} (removed)  ← only if backlog source found
```

## Verification

After implementation, verify by checking:

1. The new "Handle Backlog Source" section exists between "Create Metadata File" and "State Tracking"
2. The section contains the correct regex pattern `\*Source: Backlog #(\d{5})\*`
3. Error handling covers: no brainstorm, no pattern, ID not found in backlog
4. Output section includes conditional backlog linkage message
