# Tasks: Backlog to Feature Link

## Task 1: Add Handle Backlog Source Section

**File:** `plugins/iflow/commands/create-feature.md`

**Action:** Insert new section after "Create Metadata File" section, before "State Tracking" section

**Content:**
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

**Acceptance:** Section exists at correct location with exact regex pattern and all 5 conditional branches.

---

## Task 2: Add brainstorm_source to Meta Template

**File:** `plugins/iflow/commands/create-feature.md`

**Action:** Update the JSON template in "Create Metadata File" section to include `brainstorm_source` field

**Change:** Add `"brainstorm_source": "{path-to-brainstorm-if-promoted}"` to the template

**Acceptance:** Template shows brainstorm_source field. (Note: backlog_source is added dynamically by Handle Backlog Source step, not in template)

---

## Task 3: Update Output Message

**File:** `plugins/iflow/commands/create-feature.md`

**Action:** Update "Output" section to include conditional backlog linkage line

**Change:** Add line `Linked from: Backlog #{backlog_id} (removed)` with note that it only appears when backlog source found

**Acceptance:** Output section shows the conditional backlog linkage message.

---

## Verification Checklist

After all tasks complete:

- [ ] "Handle Backlog Source" section exists between "Create Metadata File" and "State Tracking"
- [ ] Regex pattern `\*Source: Backlog #(\d{5})\*` present
- [ ] Error handling covers: no brainstorm, no pattern, ID not found
- [ ] Output section includes conditional backlog linkage message
- [ ] Meta template includes brainstorm_source field
