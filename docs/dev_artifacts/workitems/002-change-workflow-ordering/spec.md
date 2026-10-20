# Specification: Change Workflow Ordering

## Problem Statement

The current workflow requires users to run `/create-feature` before `/brainstorm`, forcing premature commitment to a feature before exploration. This is counterintuitive—brainstorming should happen freely, and only after exploration should the user decide whether to formalize an idea into a feature.

## Goals

1. Allow `/brainstorm` to run without an active feature
2. Persist brainstorm notes in a scratch folder for later review
3. Prompt user to promote brainstorm to feature at session end
4. Support both standalone and feature-attached brainstorming
5. Provide cleanup mechanism for old brainstorm files

## Non-Goals

- Auto-cleanup of old brainstorm files
- `/promote-brainstorm` command for deferred promotion
- Merging multiple brainstorms into one feature

## Requirements

### R1: Standalone Brainstorming

- `/brainstorm` MUST work without an active feature
- When no feature exists, create scratch file in `docs/dev_artifacts/brainstorms/`
- File naming: `YYYYMMDD-HHMMSS-{slug}.md`
- Slug derived from brainstorm topic (lowercase, hyphens, max 30 chars)

### R2: Context-Aware Behavior

- When active feature exists, prompt user:
  - "Add to current feature's brainstorm?" → Append to `brainstorm.md` in feature folder
  - "Start new brainstorm?" → Create scratch file (same as R1)

### R3: Promotion Flow (End of Brainstorm)

- At end of every standalone brainstorm, ask: "Turn this into a feature? (y/n)"
- If yes:
  - Ask for workflow mode (Hotfix, Quick, Standard, Full)
  - Create feature folder: `docs/dev_artifacts/workitems/{id}-{slug}/`
  - Handle worktree based on mode:
    - Hotfix: No worktree
    - Quick: Optional worktree (ask user)
    - Standard/Full: Required worktree
  - Move scratch file to feature folder as `brainstorm.md`
  - Create `.meta.json` with feature metadata
  - Auto-invoke `/specify` to continue workflow
- If no:
  - File remains in `docs/dev_artifacts/brainstorms/` for later

### R4: Create Feature Command (Standalone Entry Point)

- `/create-feature` remains available for users who want to skip brainstorming
- When called directly (no brainstorm context):
  - Ask for feature description
  - Ask for workflow mode
  - Create feature folder and worktree as needed
  - Auto-invoke `/specify` to continue workflow
- This is an **alternative entry point**, not the recommended flow

### R5: Specify Expects Brainstorm Upstream

- `/specify` expects `/brainstorm` as the recommended upstream
- When invoked without active feature:
  - Prompt: "No active feature. Would you like to /brainstorm first?"
  - Guide user to exploration before specification
- When active feature exists:
  - Read `brainstorm.md` from feature folder for context (if exists)
  - Proceed with specification

### R6: Cleanup Command

- New `/cleanup-brainstorms` command
- Lists all files in `docs/dev_artifacts/brainstorms/` with dates
- User selects which files to delete
- Confirm before deletion

### R7: Directory Structure

- Create `docs/dev_artifacts/brainstorms/.gitkeep` to ensure folder exists in repo
- Scratch files are gitignored OR committed (user preference via `.gitignore`)

### R8: Rename /plan to /create-plan

- `/plan` conflicts with Claude Code's built-in plan mode command
- Rename `commands/plan.md` to `commands/create-plan.md`
- Update all references to `/plan` in skills and documentation:
  - `skills/designing/SKILL.md` - completion message
  - `skills/breaking-down-tasks/SKILL.md` - prerequisite message
  - `README.md` - command listing
- Output file remains `plan.md` (no change to artifact name)

## Acceptance Criteria

- [ ] `/brainstorm "idea"` works without any prior setup
- [ ] Scratch file created at `docs/dev_artifacts/brainstorms/YYYYMMDD-HHMMSS-slug.md`
- [ ] Promotion prompt appears at end of standalone brainstorm
- [ ] Answering "yes" triggers mode selection, feature creation, worktree setup, and chains to `/specify`
- [ ] Answering "no" leaves file in scratch folder
- [ ] With active feature, user is asked to add or start new
- [ ] `/create-feature` works as standalone alternative entry point
- [ ] `/specify` without active feature prompts user to `/brainstorm` first
- [ ] `/specify` uses `brainstorm.md` content when available
- [ ] `/cleanup-brainstorms` lists and allows selective deletion
- [ ] No data loss during promotion (file moved atomically)
- [ ] `/plan` renamed to `/create-plan` (no collision with built-in)
- [ ] All references to `/plan` updated to `/create-plan`

## Files to Modify

| Action | File | Description |
|--------|------|-------------|
| Modify | `skills/brainstorming/SKILL.md` | Update flow, add standalone support |
| Modify | `commands/brainstorm.md` | Remove feature requirement, add context detection |
| Modify | `commands/create-feature.md` | Alternative entry point, chains to /specify |
| Modify | `commands/specify.md` | Expect brainstorm upstream, prompt if no feature |
| Create | `commands/cleanup-brainstorms.md` | New cleanup command |
| Create | `docs/dev_artifacts/brainstorms/.gitkeep` | Ensure folder exists |
| Rename | `commands/plan.md` → `commands/create-plan.md` | Avoid collision with built-in /plan |
| Modify | `skills/designing/SKILL.md` | Update /plan → /create-plan reference |
| Modify | `skills/breaking-down-tasks/SKILL.md` | Update /plan → /create-plan reference |
| Modify | `README.md` | Update /plan → /create-plan in command listing |

## Open Questions

None - all decisions made during brainstorming.
