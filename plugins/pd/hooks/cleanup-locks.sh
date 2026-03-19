#!/bin/bash
# Cleanup stale lock files before session starts

# Remove directory-based history lock
rmdir ~/.claude/history.jsonl.lock 2>/dev/null

# Remove file-based task locks
find ~/.claude/tasks -name ".lock" -delete 2>/dev/null

# Output required JSON (no additional context needed)
echo '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":""}}'
exit 0
