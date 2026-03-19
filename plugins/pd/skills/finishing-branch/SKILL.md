---
name: finishing-branch
description: Guides branch completion with PR or merge options. Use when the user says 'finish the branch', 'merge to main', 'create PR', or 'complete the feature'.
---

# Finishing a Development Branch

Guide completion of development work with streamlined options.

## Config Variables
Use these values from session context (injected at session start):
- `{pd_base_branch}` — base branch for merges (default: `main`)
- `{pd_release_script}` — path to release script (empty if not configured)

## Base Branch

The default base branch is `{pd_base_branch}`. Feature branches merge to `{pd_base_branch}`.

If `{pd_release_script}` is configured, that script handles releases.

## Core Principle

Commit changes → Present options → Execute choice → Clean up branch.

## The Process

### Step 1: Verify Clean State

Ensure all changes are committed:
```bash
git status --short
```

If uncommitted changes exist, commit them first:
```bash
git add -A && git commit -m "wip: uncommitted changes before finish"
git push
```

### Step 2: Present Options

Present exactly 2 options via AskUserQuestion. The second option label depends on whether `{pd_release_script}` is configured:

```
AskUserQuestion:
  questions: [{
    "question": "Implementation complete. How would you like to proceed?",
    "header": "Finish",
    "options": [
      {"label": "Create PR", "description": "Open pull request for team review"},
      {"label": "Merge & Release", "description": "Merge to {pd_base_branch} and run release script"}
      // ↑ Use "Merge" (without "& Release") and description "Merge to {pd_base_branch}"
      //   if {pd_release_script} is not configured
    ],
    "multiSelect": false
  }]
```

### Step 3: Execute Choice

**Option 1: Create PR**
```bash
git push -u origin {feature-branch}
gh pr create --title "{title}" --body "..."
```
Output: "PR created: {url}"
Note: Branch will be deleted when PR is merged via GitHub.

**Option 2: Merge & Release** (or "Merge" if `{pd_release_script}` is not configured)
```bash
# Merge to base branch
git checkout {pd_base_branch}
git pull origin {pd_base_branch}
git merge {feature-branch}
git push
```

If `{pd_release_script}` is set and the file exists at that path, run it:
```bash
{pd_release_script}
```
Otherwise, skip the release step and output "No release script configured."

```bash
# Delete feature branch
git branch -d {feature-branch}
```
Output: "Merged to {pd_base_branch}." followed by "Released v{version}" if release script ran, or "No release script configured." if not.

## Quick Reference

| Option | Merge | Push | Release | Delete Branch |
|--------|-------|------|---------|---------------|
| Create PR | - | Yes | - | GitHub deletes on merge |
| Merge (& Release) | Yes | Yes | If configured | Yes (local) |

## Red Flags - Never

- Force-push without explicit request
- Delete work without confirmation
- Skip the release script on Merge & Release option (when `{pd_release_script}` is configured)
