#!/bin/bash
# Asserts FR-C-115.1 commit message marker.
# Invoked by git as: ./script /path/to/COMMIT_EDITMSG
#
# Spec FR-C-115.1: the atomic commit MUST begin with 'FR-C-115.1:' marker
# so the AC verification protocol can locate it via `git log --grep`.
#
# Only enforces when atomicity-relevant changes are staged.

set -euo pipefail

MSG_FILE="${1:-/dev/null}"
if [[ ! -f "$MSG_FILE" ]]; then
    # Not invoked with a message file — exit cleanly (no marker check).
    exit 0
fi
FIRST_LINE=$(head -1 "$MSG_FILE")

DB_ADDS=$(git diff --cached -- plugins/pd/hooks/lib/entity_registry/database.py \
    | grep -cE '^\+.*event_type[[:space:]]*=[[:space:]]*"entity_status_changed"' || true)
WSS_DELS=$(git diff --cached -- plugins/pd/mcp/workflow_state_server.py \
    | grep -cE '^-.*event_type[[:space:]]*=[[:space:]]*"entity_status_changed"' || true)

if [[ "$DB_ADDS" -gt 0 || "$WSS_DELS" -gt 0 ]]; then
    if [[ ! "$FIRST_LINE" =~ ^FR-C-115\.1: ]]; then
        echo "ERROR: FR-C-115.1 commit must begin with 'FR-C-115.1:' marker." >&2
        echo "  Current first line: $FIRST_LINE" >&2
        exit 1
    fi
fi
exit 0
