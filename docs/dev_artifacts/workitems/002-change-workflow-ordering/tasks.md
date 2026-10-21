# Tasks: Change Workflow Ordering

## Task List

### Phase 1: Foundation

#### Task 1.1: Create brainstorms directory
- **Files:** `docs/dev_artifacts/brainstorms/.gitkeep`
- **Do:** Create empty `.gitkeep` file to ensure directory exists in git
- **Test:** `ls docs/brainstorms/.gitkeep` succeeds
- **Done when:** File exists and directory is tracked by git

#### Task 1.2: Rename plan command
- **Files:** `commands/plan.md` → `commands/create-plan.md`
- **Do:** `git mv commands/plan.md commands/create-plan.md`
- **Test:** `ls commands/create-plan.md` succeeds, `ls commands/plan.md` fails
- **Done when:** Command file renamed, git tracks the rename

---

### Phase 2: Reference Updates

#### Task 2.1: Update /plan reference in designing skill
- **Depends on:** Task 1.2
- **Files:** `skills/designing/SKILL.md`
- **Do:** Change line 121 from `/plan` to `/create-plan`
- **Test:** `grep "/plan" skills/designing/SKILL.md` returns no matches
- **Done when:** Only `/create-plan` appears in completion message

#### Task 2.2: Update /plan reference in breaking-down-tasks skill
- **Depends on:** Task 1.2
- **Files:** `skills/breaking-down-tasks/SKILL.md`
- **Do:** Change line 13 from `/plan` to `/create-plan`
- **Test:** `grep "/plan" skills/breaking-down-tasks/SKILL.md` returns no matches
- **Done when:** Only `/create-plan` appears in prerequisite message

#### Task 2.3: Update /plan references in README
- **Depends on:** Task 1.2
- **Files:** `README.md`
- **Do:** Change `/plan` to `/create-plan` on lines 72 and 166
- **Test:** `grep "/plan" README.md` returns no command references (only plan.md artifact)
- **Done when:** Command listing shows `/create-plan`

#### Task 2.4: Update SessionStart hook workflow display
- **Depends on:** Task 1.2
- **Files:** `hooks/session-start.sh`
- **Do:**
  - Line 118: Replace entire workflow string. Current value:
    ```
    Available commands: /create-feature | /brainstorm → /specify → /design → /create-tasks → /implement → /verify → /finish
    ```
    New value:
    ```
    Available commands: /brainstorm → /specify → /design → /create-plan → /create-tasks → /implement → /verify → /finish (/create-feature as alternative)
    ```
  - Lines 120-121: Change "No active feature" message from suggesting `/create-feature` to suggesting `/brainstorm`
- **Test:** Run session start hook manually: `./hooks/session-start.sh`, verify output shows:
  - `/brainstorm` as first command (primary entry)
  - `/create-plan` between `/design` and `/create-tasks`
  - `/create-feature` noted as alternative
- **Done when:** Workflow string fully rewritten with correct order and emphasis

---

### Phase 3: Core Skill Updates

#### Task 3.1: Update specifying skill prerequisites
- **Files:** `skills/specifying/SKILL.md`
- **Do:** Update Prerequisites section:
  ```
  - If not found:
    - "No active feature. Would you like to /brainstorm first to explore ideas?"
    - Do NOT proceed without user confirmation
  ```
- **Test:** Read skill, verify new prerequisite text present
- **Done when:** Skill guides user to /brainstorm when no feature exists

#### Task 3.2: Add context-aware check to brainstorming skill
- **Files:** `skills/brainstorming/SKILL.md`
- **Do:** Update Prerequisites section to:
  - Check for active feature in `docs/dev_artifacts/workitems/`
  - If found: Ask "Add to existing feature or start new brainstorm?"
  - If not found: Proceed to standalone mode
- **Test:** Read skill, verify context-aware logic documented
- **Done when:** Skill handles both with-feature and without-feature cases

#### Task 3.3: Add standalone mode to brainstorming skill
- **Depends on:** Task 3.2
- **Files:** `skills/brainstorming/SKILL.md`
- **Do:** Add new section "## Standalone Mode (No Active Feature)":
  - Generate timestamp: `YYYYMMDD-HHMMSS`
  - Generate slug from topic (lowercase, hyphens, max 30 chars)
  - Create scratch file: `docs/dev_artifacts/brainstorms/{timestamp}-{slug}.md`
  - Run normal brainstorming exploration
- **Test:** Section exists with timestamp/slug/file creation instructions
- **Done when:** Standalone mode fully documented

#### Task 3.4: Add promotion flow to brainstorming skill
- **Depends on:** Task 3.3
- **Files:** `skills/brainstorming/SKILL.md`
- **Do:** Add new section "## Promotion Flow" after standalone mode:
  - At end, ask: "Turn this into a feature? (y/n)"
  - If yes:
    - Ask for mode (Hotfix, Quick, Standard, Full)
    - Generate feature ID (highest in docs/features/ + 1)
    - Create folder: `docs/dev_artifacts/workitems/{id}-{slug}/`
    - Handle worktree based on mode
    - Move scratch file as `brainstorm.md`
    - Create `.meta.json`
    - Auto-invoke `/specify`
  - If no: Inform user file saved for later
- **Test:** Section exists with complete promotion logic
- **Done when:** Promotion flow fully documented with all mode handling

---

### Phase 4: Command Updates

#### Task 4.1: Update brainstorm command
- **Depends on:** Tasks 3.2, 3.3, 3.4
- **Files:** `commands/brainstorm.md`
- **Do:**
  - Update description: "Start brainstorming - works with or without active feature"
  - Update argument-hint: `[topic or idea to explore]`
  - Update body to reference standalone mode in skill
- **Test:** Read command, verify new description and instructions
- **Done when:** Command no longer requires active feature

#### Task 4.2: Update create-feature command
- **Depends on:** Tasks 3.2, 3.3, 3.4
- **Files:** `commands/create-feature.md`
- **Do:**
  - Update description to indicate "alternative entry point"
  - Update output message: "Note: Skipped brainstorming. Proceeding to /specify."
  - Change "Next: Run /brainstorm" to "Auto-continuing to /specify"
  - Remove references to running /brainstorm after
- **Test:** Read command, verify it chains to /specify not /brainstorm
- **Done when:** Command is clearly alternative path, chains to /specify

#### Task 4.3: Update specify command
- **Depends on:** Task 3.1
- **Files:** `commands/specify.md`
- **Do:**
  - Add instruction to check for active feature first
  - If no feature: "No active feature found. Would you like to /brainstorm to explore ideas first?"
- **Test:** Read command, verify no-feature guard documented
- **Done when:** Command guides user to /brainstorm when no feature

---

### Phase 5: New Command

#### Task 5.1: Create cleanup-brainstorms command
- **Depends on:** Task 1.1
- **Files:** `commands/cleanup-brainstorms.md` (new)
- **Do:** Create new command with:
  ```yaml
  ---
  description: List and delete old brainstorm scratch files
  ---
  ```
  Body:
  - List all files in `docs/dev_artifacts/brainstorms/` (exclude .gitkeep)
  - Display with relative dates (today, yesterday, N days ago)
  - Ask user which to delete (by number)
  - Confirm before deletion
  - Delete selected files
- **Test:** File exists at `commands/cleanup-brainstorms.md`
- **Done when:** Command fully documented with list/select/confirm/delete flow

---

## Summary

- **Total tasks:** 13
- **Phase 1 (Foundation):** 2 tasks
- **Phase 2 (Reference Updates):** 4 tasks
- **Phase 3 (Core Skills):** 4 tasks
- **Phase 4 (Command Updates):** 3 tasks
- **Phase 5 (New Command):** 1 task

## Execution Order

Can be parallelized as follows:

```
[1.1, 1.2] → [2.1, 2.2, 2.3, 2.4] (after 1.2)
            → [5.1] (after 1.1)

[3.1] → [4.3]
[3.2] → [3.3] → [3.4] → [4.1, 4.2]
```
