#!/bin/bash
# Asserts FR-C-115.1 atomicity invariant on the staged diff.
#
# FR-C-115.1: the commit that inserts an entity_status_changed emit in
# plugins/pd/hooks/lib/entity_registry/database.py MUST also delete the
# F111 manual emit block in plugins/pd/mcp/workflow_state_server.py
# (the db.append_phase_event(event_type='entity_status_changed', ...) call
# inside the closure_targets loop).
#
# Exit 0 if both sides of the invariant are present, OR if neither is
# (commit unrelated to FR-C-115.1). Exit 1 if exactly one side is staged.
#
# Use: invoke manually before `git commit`, OR symlink to .git/hooks/pre-commit
# during the FR-C-115.1 commit only (remove afterward).

set -euo pipefail

DB_ADDS=$(git diff --cached -- plugins/pd/hooks/lib/entity_registry/database.py \
    | grep -cE '^\+.*event_type[[:space:]]*=[[:space:]]*"entity_status_changed"' || true)
WSS_DELS=$(git diff --cached -- plugins/pd/mcp/workflow_state_server.py \
    | grep -cE '^-.*event_type[[:space:]]*=[[:space:]]*"entity_status_changed"' || true)

if [[ "$DB_ADDS" -gt 0 && "$WSS_DELS" -gt 0 ]]; then
    exit 0  # both sides present — atomic
elif [[ "$DB_ADDS" -eq 0 && "$WSS_DELS" -eq 0 ]]; then
    exit 0  # neither — unrelated commit
else
    echo "ERROR: FR-C-115.1 atomicity violation:" >&2
    echo "  database.py emit additions: $DB_ADDS" >&2
    echo "  workflow_state_server.py emit deletions: $WSS_DELS" >&2
    echo "  Both must be present in the same commit per spec FR-C-115.1." >&2
    exit 1
fi
