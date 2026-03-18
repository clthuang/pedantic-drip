---
description: Transition a feature to abandoned status
argument-hint: "[--feature={id}-{slug}]"
---

# /iflow:abandon-feature Command

Mark a feature as abandoned. Updates `.meta.json` and entity registry. Does not merge, run retro, or delete the branch.

## Config Variables
- `{iflow_artifacts_root}` — root directory for feature artifacts (default: `docs`)

## YOLO Mode Override

If `[YOLO_MODE]` is active: skip Step 3 (confirmation prompt).

## Step 1: Resolve Feature

If `--feature={id}-{slug}` argument provided: use that as the folder name under `{iflow_artifacts_root}/features/`.

Otherwise: scan `{iflow_artifacts_root}/features/` for folders whose `.meta.json` has `status: "active"` or `status: "planned"`. If exactly one found, use it. If multiple found, use AskUserQuestion to let user select. If none found, output "No active feature found. Specify --feature={id}-{slug}." and stop.

## Step 2: Validate Status

Read `{iflow_artifacts_root}/features/{folder-name}/.meta.json`.

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

Write `{iflow_artifacts_root}/features/{folder-name}/.meta.json` with `status` set to `"abandoned"`. Preserve all other fields.

## Step 5: Update Entity Registry

Call `update_entity` MCP tool:
```
update_entity(type_id="feature:{folder-name}", status="abandoned")
```

If MCP call fails: output "Warning: Entity registry update failed. Status will reconcile on next session start." and continue (`.meta.json` change persists).

## Step 6: Output

```
Feature {folder-name} abandoned.
Branch feature/{folder-name} left intact. Delete manually with 'git branch -D feature/{folder-name}' if no longer needed.
```
