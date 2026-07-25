---
description: Capture an ad-hoc idea, todo, or fix in the backlog
argument-hint: "<description>"
---

# /pd:add-to-backlog

**DB-only (feature 134 closed #060).** The entity DB is the sole home; registration durability is regression-pinned (separate-connection visibility test). `{pd_artifacts_root}/backlog-manual.md` is a historical archive — long-form context for pre-134 items only; new items do not write it.

**Steps:**
1. No description argument → print `Usage: /pd:add-to-backlog <description>` and stop.
2. `mkdir -p {pd_artifacts_root}`.
3. `register_entity(entity_type="backlog", auto_id=true, name="{description truncated at a word boundary before char 80}", status="open", metadata={"description": "{full description}"})`. Error envelope → surface it verbatim and stop.
4. `init_entity_workflow(type_id="backlog:{entity_id}", workflow_phase="open", kanban_column="backlog")`. Failure warns; it does not undo step 3.
5. Report `Added to backlog: #{entity_id} — {description}`.

**Constraints:** never Write `{pd_artifacts_root}/backlog.md` — the MCP server regenerates it from the DB, and `data-file-guard.sh` denies direct edits.
