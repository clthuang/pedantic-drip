---
description: Archive fully-closed backlog sections in the entity DB
argument-hint: "[--dry-run | --apply]"
---

# /pd:cleanup-backlog

Archival is a DB flag flip plus re-projection, never a file move: the script sets each closed entity's archive flag (`is_archived`, through `set_archived`; its status is left alone) in the DB layer, then regenerates the `{pd_artifacts_root}/backlog.md` projection, which excludes archived rows.

**Steps:**
1. Resolve the script: glob `~/.claude/plugins/cache/*/pd*/*/scripts/cleanup_backlog.py`, else `plugins/pd/scripts/cleanup_backlog.py` (Fallback — dev workspace).
2. Default mode is `--dry-run`: run it, print the preview table, stop.
3. `--apply` → confirm first:

```
AskUserQuestion:
  questions: [{
    "question": "Archive {N} fully-closed backlog sections?",
    "header": "Cleanup",
    "options": [
      {"label": "Apply", "description": "Set the archive flag in the DB and re-project"},
      {"label": "Cancel", "description": "Do nothing"}
    ],
    "multiSelect": false
  }]
```

4. On Apply, run the script with `--apply`. Commit `docs(backlog): archive {N} closed sections` only when no `--backlog-path` override was passed — fixture runs never commit.

**Constraints:** non-zero exit → surface stderr, do not commit.
