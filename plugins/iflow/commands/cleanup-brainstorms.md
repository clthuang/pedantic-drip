---
description: List and delete old brainstorm scratch files
argument-hint: "[--dry-run]"
---

# /iflow:cleanup-brainstorms Command

## Config Variables
Use these values from session context (injected at session start):
- `{iflow_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Manage brainstorm scratch files in `{iflow_artifacts_root}/brainstorms/`.

## Process

### 1. List Files

List all files in `{iflow_artifacts_root}/brainstorms/` (exclude `.gitkeep`). If the directory does not exist, display "No brainstorm scratch files found." and stop.

```
Brainstorm scratch files:

1. 20260129-143052-api-caching.prd.md (today)
2. 20260128-091530-auth-rework.prd.md (yesterday)
3. 20260115-220000-old-idea.prd.md (14 days ago)

Total: 3 files
```

Calculate relative dates:
- Same day: "today"
- Yesterday: "yesterday"
- Within 7 days: "N days ago"
- Older: "N weeks ago" or date

### 2. Select Files to Delete

Use AskUserQuestion with multiSelect:
```
AskUserQuestion:
  questions: [{
    "question": "Select files to delete:",
    "header": "Delete",
    "options": [
      {"label": "{filename1}", "description": "{relative date}"},
      {"label": "{filename2}", "description": "{relative date}"},
      ...dynamically generated from file list...
    ],
    "multiSelect": true
  }]
```

Note: User can always select "Other" to specify custom input if needed.

### 3. Confirm Deletion

Show selected files and confirm via AskUserQuestion:
```
AskUserQuestion:
  questions: [{
    "question": "Will delete: {list of selected files}. Confirm?",
    "header": "Delete",
    "options": [
      {"label": "Yes, Delete", "description": "Remove selected files permanently"},
      {"label": "Cancel", "description": "Keep all files"}
    ],
    "multiSelect": false
  }]
```

### 4. Delete Files

If confirmed:
- For each selected file:
  - Delete the file
  - Extract filename stem (filename without `.prd.md` extension)
  - Call update_entity MCP tool:
    `update_entity(type_id="brainstorm:{filename_stem}", status="archived")`
  - If MCP call fails or entity not found:
    Warn "Entity update skipped for {filename_stem}" and continue
- Report: "Deleted N file(s)."

If cancelled:
- Report: "Cancelled. No files deleted."

## Edge Cases

- No files found: "No brainstorm scratch files found."
- Invalid selection: AskUserQuestion handles selection validation automatically
- File already deleted: Skip gracefully
