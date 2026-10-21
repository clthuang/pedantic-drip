# Design: Harden Brainstorm Workflow

## Architecture Overview

Modify the `brainstorming` skill to enforce a strict closing sequence:

```
Brainstorm Content Complete
         ↓
  ┌──────────────────┐
  │ Invoke brainstorm│
  │ -reviewer agent  │
  └────────┬─────────┘
           ↓
    ┌─────────────┐
    │ Has blockers?│
    └──────┬──────┘
       No  │  Yes
           ↓    ↓
    ┌──────┐  ┌──────────────┐
    │ Ask  │  │ Show issues, │
    │ User │  │ fix & retry  │
    └──┬───┘  └──────────────┘
       ↓
  ┌─────────┐
  │ "Yes"?  │
  └────┬────┘
   Yes │  No
       ↓    ↓
┌──────────┐ ┌─────────────┐
│ /create- │ │ "Saved to   │
│ feature  │ │ {file}."    │
└──────────┘ │ STOP        │
             └─────────────┘
```

## Components

### Component 1: Brainstorm Reviewer Invocation

- Purpose: Validate brainstorm quality before promotion
- Location: New section between "### 6. Capture Ideas" and "Promotion Flow"
- Implementation: Use Task tool with `brainstorm-reviewer` subagent

### Component 2: Hardened Promotion Flow

- Purpose: Replace current "### 3. Promotion Flow" section (lines 49-85)
- Changes:
  - Add verification step before promotion question
  - Use `AskUserQuestion` tool (not text prompt)
  - Change auto-invoke from `/iflow:specify` to `/iflow:create-feature`
  - Add explicit PROHIBITED section

### Component 4: With Active Feature Path

- Purpose: Update "Completion" section (lines 172-179) to use same hardened flow
- Current behavior: Different paths for standalone vs active feature
- New behavior: Both paths use verification + AskUserQuestion gate
- Note: With active feature, promotion still applies (saves to feature's brainstorm.md)

### Component 3: PROHIBITED Section

- Purpose: Explicitly forbid actions that skip the workflow
- Location: End of skill file, after Completion section

## Interfaces

### Brainstorm Reviewer Invocation

**Exact Task Tool Syntax:**
```
Task tool call:
  description: "Review brainstorm for promotion"
  subagent_type: "iflow:brainstorm-reviewer"
  prompt: |
    Review this brainstorm file for readiness to become a feature:

    File: {absolute path to scratch file}

    Use the brainstorm checklist:
    - Problem clearly stated?
    - Goals defined?
    - Options explored?
    - Direction chosen?
    - Rationale documented?

    Return structured JSON:
    {
      "approved": true/false,
      "issues": [{"severity": "blocker|warning|note", "description": "...", "location": "..."}],
      "summary": "..."
    }
```

**Response Parsing:**
```
1. Extract JSON from response
2. Check issues array for any with severity: "blocker"
3. If blockers exist: approved = false
4. If no blockers: approved = true (regardless of warnings/notes)
```

### Blocker Retry Loop

**When blockers are found:**
```
1. Display to user:
   "Review found blockers that should be addressed:

   🔴 {blocker description} (at: {location})

   Please address these issues in the brainstorm, then say 'ready' to re-verify."

2. Wait for user to make changes and respond

3. Re-invoke brainstorm-reviewer with same syntax

4. Repeat until no blockers OR user says "skip verification"
   - If user says "skip": proceed to promotion with warning
```

### Promotion Question (AskUserQuestion)

**Exact AskUserQuestion Tool Syntax:**
```
AskUserQuestion tool call:
  questions: [
    {
      "question": "Turn this into a feature?",
      "header": "Promote",
      "options": [
        {"label": "Yes", "description": "Create feature and continue workflow"},
        {"label": "No", "description": "End session, brainstorm already saved"}
      ],
      "multiSelect": false
    }
  ]
```

**Response Handling:**
```
If response == "Yes":
  1. Ask for mode using AskUserQuestion:
     question: "Which workflow mode?"
     options: ["Standard", "Full"]
  2. Invoke /iflow:create-feature
  3. STOP (create-feature handles the rest)

If response == "No":
  1. Output: "Brainstorm saved to {filepath}."
  2. STOP (no further action)
```

## Technical Decisions

### Decision 1: Verification Before Promotion

- **Choice:** Run brainstorm-reviewer BEFORE asking promotion question
- **Alternatives:** Run after promotion, run optionally
- **Rationale:** Catches quality issues early; user makes promotion decision with full information

### Decision 2: Blocker Handling

- **Choice:** If reviewer returns blockers, show issues and ask user to address them before proceeding
- **Alternatives:** Proceed anyway, auto-reject
- **Rationale:** User maintains control; blockers are serious issues worth fixing

### Decision 3: Use AskUserQuestion Tool

- **Choice:** Require AskUserQuestion tool for promotion question
- **Alternatives:** Text prompt, implicit continuation
- **Rationale:** Creates hard interaction point; user always gets explicit choice

## File Changes

### `plugins/iflow/skills/brainstorming/SKILL.md`

| Section | Change |
|---------|--------|
| Lines 49-85 (Promotion Flow) | Replace with hardened version including verification |
| Lines 172-179 (Completion) | Update to reference new flow |
| End of file | Add PROHIBITED section |

### New Content: Verification Step

Add after "### 6. Capture Ideas" section:

```markdown
### 7. Verification (REQUIRED)

Before the promotion question, you MUST verify the brainstorm:

1. Invoke reviewer via Task tool:
   ```
   Task:
     description: "Review brainstorm for promotion"
     subagent_type: "iflow:brainstorm-reviewer"
     prompt: |
       Review this brainstorm file for readiness to become a feature:
       File: {absolute path to brainstorm file}

       Checklist:
       - Problem clearly stated?
       - Goals defined?
       - Options explored?
       - Direction chosen?
       - Rationale documented?

       Return JSON: { "approved": bool, "issues": [...], "summary": "..." }
   ```

2. Parse response and check for blockers (severity: "blocker")

3. If blockers found:
   - Show: "Review found blockers:\n🔴 {description} (at: {location})"
   - Ask user to address issues
   - Re-verify when user says "ready"
   - If user says "skip verification" → proceed with warning

4. If no blockers → Proceed to Promotion Flow

5. If reviewer unavailable → Show warning, proceed to Promotion Flow
```

### New Content: Hardened Promotion Flow

Replace current "### 3. Promotion Flow" (lines 49-85) with:

```markdown
### 8. Promotion Flow (REQUIRED)

After verification passes, you MUST use AskUserQuestion:

1. Call AskUserQuestion tool with EXACTLY:
   ```
   AskUserQuestion:
     questions: [{
       "question": "Turn this into a feature?",
       "header": "Promote",
       "options": [
         {"label": "Yes", "description": "Create feature and continue workflow"},
         {"label": "No", "description": "End session, brainstorm already saved"}
       ],
       "multiSelect": false
     }]
   ```

2. Handle response:

   **If "Yes":**
   a. Ask for mode:
      ```
      AskUserQuestion:
        questions: [{
          "question": "Which workflow mode?",
          "header": "Mode",
          "options": [
            {"label": "Standard", "description": "All phases, optional verification"},
            {"label": "Full", "description": "All phases, required verification"}
          ],
          "multiSelect": false
        }]
      ```
   b. Invoke `/iflow:create-feature` with brainstorm content
   c. STOP (create-feature handles the rest)

   **If "No":**
   a. Output: "Brainstorm saved to {filepath}."
   b. STOP — Do NOT continue with any other action
```

### New Content: Updated Completion Section

Replace current "## Completion" (lines 172-179) with:

```markdown
## Completion

**Both standalone and with-feature modes** use the same closing sequence:
1. Run verification (### 7)
2. Run promotion flow (### 8)

The only difference is where the file is saved:
- Standalone: `docs/dev_artifacts/brainstorms/{timestamp}-{slug}.md`
- With feature: `docs/dev_artifacts/workitems/{id}-{slug}/brainstorm.md`
```

### New Content: PROHIBITED Section

Add at end of file:

```markdown
## PROHIBITED Actions

When executing the brainstorming skill, you MUST NOT:

- Proceed to /iflow:specify, /iflow:design, /iflow:create-plan, or /iflow:implement
- Write any implementation code
- Create feature folders directly (use /iflow:create-feature)
- Continue with any action after user says "No" to promotion
- Skip the verification step
- Skip the AskUserQuestion promotion gate
```

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Agent ignores PROHIBITED section | User loses control | Use strongest language (MUST NOT); add to system prompt if needed |
| Reviewer subagent unavailable | Blocks promotion | Fallback: warn and proceed without verification |
| AskUserQuestion tool not called | Silent skip | Explicitly state "Use AskUserQuestion tool" not "ask the user" |

## Dependencies

- `plugins/iflow/agents/brainstorm-reviewer.md` (already exists)
- Task tool with subagent support
- AskUserQuestion tool
