# Tasks: Harden Brainstorm Workflow

## Task 1: Verify brainstorm-reviewer agent exists

**Status:** pending

**Description:**
Confirm `plugins/iflow/agents/brainstorm-reviewer.md` exists and has correct format.

**Acceptance Criteria:**
- [ ] File exists at `plugins/iflow/agents/brainstorm-reviewer.md`
- [ ] File has valid frontmatter with `name`, `description`, `tools`
- [ ] Description mentions reviewing brainstorm for promotion readiness

**Files:** `plugins/iflow/agents/brainstorm-reviewer.md` (read only)

---

## Task 2: Add Verification section to brainstorming skill

**Status:** pending
**Depends on:** Task 1

**Description:**
Insert new "### 7. Verification (REQUIRED)" section after the "### 6. Capture Ideas" section in the brainstorming skill.

**Content to add** (from design.md lines 188-223):
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

**Acceptance Criteria:**
- [ ] Section inserted after "### 6. Capture Ideas"
- [ ] Task tool syntax is correct
- [ ] Blocker handling loop is documented

**Files:** `plugins/iflow/skills/brainstorming/SKILL.md`

---

## Task 3: Replace Promotion Flow section

**Status:** pending
**Depends on:** Task 2

**Description:**
Replace the current "### 3. Promotion Flow" section (in Standalone Mode) with the hardened "### 8. Promotion Flow (REQUIRED)" section.

**Content to replace with** (from design.md lines 229-270):
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

**Acceptance Criteria:**
- [ ] Old "### 3. Promotion Flow" section removed
- [ ] New "### 8. Promotion Flow (REQUIRED)" section in place
- [ ] AskUserQuestion syntax is exact
- [ ] Both Yes and No paths documented with STOP

**Files:** `plugins/iflow/skills/brainstorming/SKILL.md`

---

## Task 4: Update Completion section

**Status:** pending
**Depends on:** Task 3

**Description:**
Replace the current "## Completion" section to unify standalone and with-feature paths.

**Content to replace with** (from design.md lines 276-286):
```markdown
## Completion

**Both standalone and with-feature modes** use the same closing sequence:
1. Run verification (### 7)
2. Run promotion flow (### 8)

The only difference is where the file is saved:
- Standalone: `docs/dev_artifacts/brainstorms/{timestamp}-{slug}.md`
- With feature: `docs/dev_artifacts/workitems/{id}-{slug}/brainstorm.md`
```

**Acceptance Criteria:**
- [ ] Old Completion section replaced
- [ ] Both modes reference same flow (### 7 and ### 8)
- [ ] File location difference documented

**Files:** `plugins/iflow/skills/brainstorming/SKILL.md`

---

## Task 5: Add PROHIBITED section

**Status:** pending
**Depends on:** None (can run in parallel with Tasks 2-4)

**Description:**
Append the PROHIBITED section at the end of the brainstorming skill file.

**Content to add** (from design.md lines 292-303):
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

**Acceptance Criteria:**
- [ ] Section appended at end of file
- [ ] All prohibited actions listed
- [ ] Uses "MUST NOT" language

**Files:** `plugins/iflow/skills/brainstorming/SKILL.md`

---

## Task 6: Manual test - standalone brainstorm

**Status:** pending
**Depends on:** Tasks 2, 3, 4, 5

**Description:**
Run `/iflow:brainstorm` on a new topic and verify the hardened flow works.

**Test Steps:**
1. Run `/iflow:brainstorm test topic`
2. Complete a minimal brainstorm
3. Verify reviewer is invoked
4. Answer "No" to promotion → verify session ends
5. Re-run and answer "Yes" → verify /create-feature is invoked

**Acceptance Criteria:**
- [ ] Reviewer subagent is invoked before promotion question
- [ ] AskUserQuestion appears with Yes/No options
- [ ] "No" path ends session with "Brainstorm saved" message
- [ ] "Yes" path invokes /create-feature

**Files:** None (manual test)

---

## Task 7: Manual test - with-feature brainstorm

**Status:** pending
**Depends on:** Tasks 2, 3, 4, 5

**Description:**
Run `/iflow:brainstorm` while an active feature exists and verify the hardened flow works for that path too.

**Test Steps:**
1. Create a test feature folder with `.meta.json`
2. Run `/iflow:brainstorm`
3. Choose "Add to existing feature's brainstorm"
4. Complete a minimal brainstorm
5. Verify reviewer is invoked
6. Verify AskUserQuestion appears
7. Clean up test feature

**Acceptance Criteria:**
- [ ] With-feature path uses same verification step
- [ ] With-feature path uses same AskUserQuestion gate
- [ ] Brainstorm saved to feature folder, not scratch

**Files:** None (manual test)
