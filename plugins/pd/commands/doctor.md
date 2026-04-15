---
description: Run diagnostic checks on pd workspace health
---

# /pd:doctor Command

Run 13 data consistency checks across entity DB, memory DB, workflow state, and filesystem artifacts. Optionally apply safe auto-fixes.

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` -- root directory for feature artifacts (default: `docs`)

## Modes

- **Diagnostic only** (default): Run checks, report issues with fix_hints
- **Auto-fix** (when user asks to fix): Add `--fix` flag -- applies safe fixes, re-runs diagnostics to verify
- **Dry-run**: Add `--fix --dry-run` -- shows what would be fixed without applying

## Step 1: Run Diagnostics

Run the doctor module via Bash. Use the plugin portability pattern.

If the user asks to **fix** issues, add `--fix` to the command. If the user asks for a **dry run**, add `--fix --dry-run`.

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
    echo '{"diagnostic":{"healthy":false,"checks":[],"total_issues":1,"error_count":1,"warning_count":0,"elapsed_ms":0,"_error":"No pd venv found. Run: cd plugins/pd && uv sync"}}'
  fi
fi
```

## Step 2: Parse and Format Output

The JSON output is wrapped: `{"diagnostic": {...}}` for default mode.

With `--fix`: `{"diagnostic": {...}, "fixes": {...}, "post_fix": {...}}`.

Parse the `diagnostic` key. Format as a summary table:

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
| security_review_command | PASS/FAIL | N issues |

For each check that failed (passed=false), show the issues grouped by severity:
- Errors first (with fix_hint if available)
- Warnings second
- Info last

## Step 3: Fix Results (--fix mode only)

If `fixes` key is present in the output:

1. Show fix summary: "Fixed N, skipped M (manual), failed F"
2. List each applied fix with its action
3. List failed fixes with error details
4. List manual fixes that need human attention with their fix_hints

If `post_fix` key is present, show before/after comparison:
- "Before: E errors, W warnings"
- "After: E errors, W warnings"

## Step 4: Summary

Report the overall health status:
- "Workspace healthy" if all checks passed
- "N issues found (E errors, W warnings)" otherwise

If fixes were applied, note: "Re-run `/pd:doctor` to verify current state."

For manual fixes, list each with its fix_hint so the user can take action.

Footer: "Doctor runs automatically at session start. Issues here indicate problems that survived auto-repair."
