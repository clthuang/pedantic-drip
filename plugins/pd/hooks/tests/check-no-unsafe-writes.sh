#!/usr/bin/env bash
# FR8 static guard for feature 107.
# Forbids line-leading `cat <<` heredoc — legal cat-heredocs in pd hooks
# are always inside `$(...)` substitutions (line-prefixed with `=$(`).
#
# Usage: check-no-unsafe-writes.sh [target_path]
# Default target: plugins/pd/hooks/session-start.sh
#
# CRITICAL: Use POSIX [[:space:]] not `\s` — BSD grep on macOS does NOT
# support `\s` in ERE; using `\s` would silently match nothing.

set -euo pipefail

target="${1:-plugins/pd/hooks/session-start.sh}"

if [[ ! -f "$target" ]]; then
    echo "FR8 guard: target not found: $target" >&2
    exit 2
fi

# grep returns 1 on no match, 2 on error. We want 0 on no match (success).
violations=$(grep -nE '^[[:space:]]*cat[[:space:]]*<<' "$target" || true)

if [[ -n "$violations" ]]; then
    echo "FR8 violation in $target:" >&2
    echo "$violations" >&2
    exit 1
fi

exit 0
