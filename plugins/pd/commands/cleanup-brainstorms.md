---
description: Select and delete stale brainstorm scratch files
argument-hint: "[--dry-run]"
---

# /pd:cleanup-brainstorms

**Steps:**
1. List `{pd_artifacts_root}/brainstorms/` excluding `.gitkeep`, each with its age from mtime. Missing directory or no files → `No brainstorm scratch files found.` and stop. `--dry-run` stops here.
2. Offer the list for selection:

```
AskUserQuestion:
  questions: [{
    "question": "Select brainstorm files to delete:",
    "header": "Delete",
    "options": [
      {"label": "{filename}", "description": "{age}"}
    ],
    "multiSelect": true
  }]
```

3. Confirm the selected set once with a single-select Yes/Cancel question before any deletion.
4. Per confirmed file: delete it, then `update_entity(type_id="brainstorm:{stem}", archived=true)` where `{stem}` drops the `.prd.md` suffix. This sets the entity's archive flag and leaves its status alone; session start never archives a brainstorm whose file is missing. Entity missing or MCP error → warn for that stem and continue; the file stays deleted.
5. Report the deleted count.

**Constraints:** the confirmation lists every selected filename, so nothing is deleted behind a count-only prompt; a brainstorm already promoted to a feature keeps its entity — only the scratch file goes.
