---
description: Archive fully-closed backlog sections via update_entity + re-project.
argument-hint: [--dry-run | --apply]
---

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Archive per-feature sections in `{pd_artifacts_root}/backlog.md` whose items are 100% closed.
Closed = strikethrough OR contains `(closed:`, `(promoted →`, `(fixed in feature:`, or `**CLOSED`.

**Feature 110 FR-4.3 update:** Archival no longer moves rows between `backlog.md`
and `backlog-archive.md`. Instead, the script flips
`update_entity(type_id, status='archived')` on each archivable backlog entity
and invokes `_project_backlog_md` to regenerate `{pd_artifacts_root}/backlog.md`
(which excludes archived rows per design TD-10). The standalone
`backlog-archive.md` file is no longer maintained.

## Instructions

1. **Resolve script path** via two-location glob:
   - Primary: `~/.claude/plugins/cache/*/pd*/*/scripts/cleanup_backlog.py`
   - Fallback (dev workspace): `plugins/pd/scripts/cleanup_backlog.py`

2. **Default mode is `--dry-run`.** If user passed `--dry-run` or no argument, run preview:
   ```
   python3 ${script_path} --dry-run --backlog-path {pd_artifacts_root}/backlog.md
   ```
   Display the markdown table to user. STOP.

3. **If user passed `--apply`:**
   - YOLO mode override: auto-confirm.
   - Otherwise prompt:
     ```
     AskUserQuestion:
       questions: [{
         "question": "Archive {N} fully-closed sections from {pd_artifacts_root}/backlog.md?",
         "header": "Cleanup Backlog",
         "options": [
           {"label": "Apply", "description": "Flip status='archived' in DB and re-project backlog.md"},
           {"label": "Cancel", "description": "Do nothing"}
         ],
         "multiSelect": false
       }]
     ```
   - On Apply: invoke
     ```
     python3 ${script_path} --apply --backlog-path {pd_artifacts_root}/backlog.md
     ```
     (The `--archive-path` flag is deprecated under feature 110 FR-4.3
     and is ignored when supplied.)
   - **Commit ONLY when:** (a) `--apply` was selected AND (b) no `--backlog-path` override was used (canonical project paths). Skip commit on fixture-based runs.
   - Commit message: `docs(backlog): archive {N} fully-closed sections via update_entity`.

4. **Errors:**
   - Script not found → "cleanup_backlog.py not found; pd plugin may need re-install."
   - Backlog not found → "No backlog.md at {pd_artifacts_root}/. Skipping."
   - Script exit non-zero → surface stderr to user; do not commit.

## See Also

- `/pd:doctor` — `check_active_backlog_size` warns when active items exceed threshold.
- Spec: `{pd_artifacts_root}/features/099-retro-prevention-batch/spec.md` FR-6a.
