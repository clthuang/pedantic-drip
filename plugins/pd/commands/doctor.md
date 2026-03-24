---
description: Run diagnostic checks on pd workspace health
---

# /pd:doctor Command

Run 10 data consistency checks across entity DB, memory DB, workflow state, and filesystem artifacts.

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` -- root directory for feature artifacts (default: `docs`)

## Step 1: Run Diagnostics

Run the doctor module via Bash. Use the plugin portability pattern:

```bash
# Primary: cached plugin
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/hooks 2>/dev/null | head -1 | xargs dirname)
if [[ -n "$PLUGIN_ROOT" ]] && [[ -x "$PLUGIN_ROOT/.venv/bin/python" ]]; then
  PYTHONPATH="$PLUGIN_ROOT/hooks/lib" "$PLUGIN_ROOT/.venv/bin/python" -m doctor \
    --entities-db ~/.claude/pd/entities/entities.db \
    --memory-db ~/.claude/pd/memory/memory.db \
    --artifacts-root {pd_artifacts_root} \
    --project-root . \
    2>/dev/null
else
  # Fallback: dev workspace
  if [[ -x "plugins/pd/.venv/bin/python" ]]; then
    PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor \ # Fallback (dev workspace)
      --entities-db ~/.claude/pd/entities/entities.db \
      --memory-db ~/.claude/pd/memory/memory.db \
      --artifacts-root {pd_artifacts_root} \
      --project-root . \
      2>/dev/null
  else
    echo '{"healthy":false,"checks":[],"total_issues":1,"error_count":1,"warning_count":0,"elapsed_ms":0,"_error":"No pd venv found. Run: cd plugins/pd && uv sync"}'
  fi
fi
```

## Step 2: Parse and Format Output

Parse the JSON output from stdout. Format as a summary table:

| Check | Status | Issues |
|-------|--------|--------|
| db_readiness | PASS/FAIL | N issues |
| feature_status | PASS/FAIL | N issues |
| workflow_phase | PASS/FAIL | N issues |
| brainstorm_status | PASS/FAIL | N issues |
| backlog_status | PASS/FAIL | N issues |
| memory_health | PASS/FAIL | N issues |
| branch_consistency | PASS/FAIL | N issues |
| entity_orphans | PASS/FAIL | N issues |
| referential_integrity | PASS/FAIL | N issues |
| config_validity | PASS/FAIL | N issues |

For each check that failed (passed=false), show the issues grouped by severity:
- Errors first (with fix_hint if available)
- Warnings second
- Info last

## Step 3: Summary

Report the overall health status:
- "Workspace healthy" if all checks passed
- "N issues found (E errors, W warnings)" otherwise

Footer: "Doctor runs after session-start reconciliation. Issues here indicate problems that survived auto-repair."
