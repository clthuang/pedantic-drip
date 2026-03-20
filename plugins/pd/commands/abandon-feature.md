---
description: Transition a feature to abandoned status
argument-hint: "[--feature={id}-{slug}]"
---

# /pd:abandon-feature Command

Mark a feature as abandoned. Updates `.meta.json` and entity registry. Offers branch cleanup.

## Config Variables
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

## YOLO Mode Override

If `[YOLO_MODE]` is active: skip Step 3 (confirmation prompt). Step 6 (branch cleanup) → auto "Yes, delete branch".

## Step 1: Resolve Feature

If `--feature={id}-{slug}` argument provided: use that as the folder name under `{pd_artifacts_root}/features/`.

Otherwise: scan `{pd_artifacts_root}/features/` for folders whose `.meta.json` has `status: "active"` or `status: "planned"`. If exactly one found, use it. If multiple found, use AskUserQuestion to let user select. If none found, output "No active feature found. Specify --feature={id}-{slug}." and stop.

## Step 2: Validate Status

Read `{pd_artifacts_root}/features/{folder-name}/.meta.json`.

- If `status` is `"completed"`: output "Error: Feature already completed. Cannot abandon." and stop.
- If `status` is `"abandoned"`: output "Error: Feature already abandoned." and stop.
- If `status` is not `"active"` or `"planned"`: output "Error: Cannot abandon feature with status '{status}'." and stop.

## Step 3: Confirm (skip in YOLO mode)

```
AskUserQuestion:
  questions: [{
    "question": "Abandon feature {folder-name}? This cannot be undone.",
    "header": "Confirm Abandon",
    "options": [
      {"label": "Yes, abandon", "description": "Set status to abandoned"},
      {"label": "Cancel", "description": "Keep feature as-is"}
    ],
    "multiSelect": false
  }]
```

If "Cancel": output "Cancelled." and stop.

## Step 4: Update .meta.json

Write `{pd_artifacts_root}/features/{folder-name}/.meta.json` with `status` set to `"abandoned"`. Preserve all other fields.

## Step 5: Update Entity Registry

Call `update_entity` MCP tool:
```
update_entity(type_id="feature:{folder-name}", status="abandoned")
```

If MCP call fails: output "Warning: Entity registry update failed. Status will reconcile on next session start." and continue (`.meta.json` change persists).

## Step 6: Branch Cleanup

Check if branch `feature/{folder-name}` exists locally:

```bash
git branch --list feature/{folder-name}
```

- If branch does **not** exist → skip to Step 7.
- If branch exists:
  - **YOLO mode**: Auto-delete (treat as "Yes, delete branch").
  - **Normal mode**: Ask via AskUserQuestion:

```
AskUserQuestion:
  questions: [{
    "question": "Delete local branch feature/{folder-name}? (It is unmerged and will be force-deleted.)",
    "header": "Branch Cleanup",
    "options": [
      {"label": "Yes, delete branch", "description": "Run git branch -D feature/{folder-name}"},
      {"label": "No, keep branch", "description": "Leave branch intact"}
    ],
    "multiSelect": false
  }]
```

**If deleting:**
1. If currently on `feature/{folder-name}` → `git checkout {pd_base_branch}` first.
2. `git branch -D feature/{folder-name}` (use `-D` since abandoned branches are unmerged).

## Step 7: Output

- If branch deleted: `"Feature {folder-name} abandoned. Branch feature/{folder-name} deleted."`
- If branch kept: `"Feature {folder-name} abandoned. Branch feature/{folder-name} left intact."`
- If branch didn't exist: `"Feature {folder-name} abandoned."`
