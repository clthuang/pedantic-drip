---
description: Capture an idea, todo or fix as one line in the backlog
argument-hint: "<description> [--from features/<id>]"
---

# /pd:add-to-backlog

One line in `{pd_artifacts_root}/backlog.md`, with a `YYYY-MM-DD-slug` id.

1. No description: print `Usage: /pd:add-to-backlog <description>` and stop.
2. Run `${CLAUDE_PLUGIN_ROOT}/scripts/pd-new backlog $ARGUMENTS`. A refusal is reported verbatim and stops the command.
3. Commit `backlog.md` (`backlog: <title>`), and report the new line.
