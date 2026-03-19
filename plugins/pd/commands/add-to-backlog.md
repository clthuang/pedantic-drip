---
description: Add an item to the backlog for capturing ad-hoc ideas, todos, or fixes.
argument-hint: <description>
---

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Add an item to the centralized backlog at `{pd_artifacts_root}/backlog.md`.

## Instructions

1. **Validate input:** If no description was provided in the arguments, output:
   ```
   Usage: /pd:add-to-backlog <description>
   ```
   Then stop.

2. **Ensure directory exists:** `mkdir -p {pd_artifacts_root}/`

3. **Read or initialize backlog:**
   - Try to read `{pd_artifacts_root}/backlog.md`
   - If file exists: Parse the table to find the highest existing ID (5-digit numbers like `00001`)
   - If file doesn't exist or has no entries: The next ID will be `00001`

4. **Generate the new entry:**
   - ID: Next sequential 5-digit ID (e.g., `00001`, `00002`), zero-padded
   - Timestamp: Current time in ISO 8601 format (e.g., `2026-01-30T14:23:00Z`)
   - Description: The user's input (escape pipe characters `|` as `\|` if present)

5. **Write to backlog:**
   - If file doesn't exist, create it with this header:
     ```markdown
     # Backlog

     | ID | Timestamp | Description |
     |----|-----------|-------------|
     ```
   - Append the new row: `| {ID} | {Timestamp} | {Description} |`

6. **Register entity and initialize workflow:**
   - Derive title: if description > 80 chars, truncate at last word boundary before char 80 and append "…"; otherwise use description as-is
   ```
   register_entity(
     entity_type="backlog",
     entity_id="{5-digit-id}",
     name="{title}",
     artifact_path="{pd_artifacts_root}/backlog.md",
     status="open",
     metadata={"description": "{full-description}"}
   )
   ```
   ```
   init_entity_workflow(
     type_id="backlog:{5-digit-id}",
     workflow_phase="open",
     kanban_column="backlog"
   )
   ```
   If MCP call fails, warn "Entity registration failed: {error}" but do NOT block backlog creation.

7. **Confirm to user:**
   ```
   Added to backlog: #{ID} - {Description}
   ```

## Example

User runs: `/pd:add-to-backlog Fix the login timeout bug`

Output:
```
Added to backlog: #00001 - Fix the login timeout bug
```

And `{pd_artifacts_root}/backlog.md` now contains:
```markdown
# Backlog

| ID | Timestamp | Description |
|----|-----------|-------------|
| 00001 | 2026-01-30T14:23:00Z | Fix the login timeout bug |
```
