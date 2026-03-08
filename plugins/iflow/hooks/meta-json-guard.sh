#!/usr/bin/env bash
# PreToolUse hook: block all direct .meta.json writes
# LLM agents must use MCP workflow tools instead of Write/Edit to .meta.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap

# Read all stdin once
INPUT=$(cat)

# Fast path: skip JSON parse if no .meta.json reference anywhere in input
if [[ "$INPUT" != *".meta.json"* ]]; then
    echo '{}'
    exit 0
fi

# Extract file_path AND tool_name in a single python3 call (design D2)
# Use tab delimiter to handle paths with spaces
IFS=$'\t' read -r FILE_PATH TOOL_NAME < <(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    fp = data.get('tool_input', {}).get('file_path', '')
    tn = data.get('tool_name', 'unknown')
    print(fp + '\t' + tn)
except:
    print('\tunknown')
" 2>/dev/null) || true

# Check if target is actually .meta.json (content may mention it but file_path doesn't)
if [[ "$FILE_PATH" != *".meta.json" ]]; then
    echo '{}'
    exit 0
fi

# Log blocked attempt (FR-11 instrumentation)
log_blocked_attempt() {
    local file_path="$1"
    local tool_name="$2"
    local log_dir="$HOME/.claude/iflow"
    local log_file="$log_dir/meta-json-guard.log"
    local timestamp feature_id

    mkdir -p "$log_dir"
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Extract feature_id from path
    if [[ "$file_path" =~ features/([^/]+)/\.meta\.json ]]; then
        feature_id="${BASH_REMATCH[1]}"
    elif [[ "$file_path" =~ projects/([^/]+)/\.meta\.json ]]; then
        feature_id="${BASH_REMATCH[1]}"
    else
        feature_id="unknown"
    fi

    # Append JSONL (>> is atomic for lines < PIPE_BUF on POSIX)
    echo "{\"timestamp\":\"$timestamp\",\"tool\":\"$tool_name\",\"path\":\"$(escape_json "$file_path")\",\"feature_id\":\"$feature_id\"}" >> "$log_file"
}

log_blocked_attempt "$FILE_PATH" "$TOOL_NAME"

# Deny (inline JSON -- no shared output_block helper exists across hooks)
REASON="Direct .meta.json writes are blocked. Use MCP workflow tools instead: transition_phase() to enter a phase, complete_phase() to finish a phase, or init_feature_state() to create a new feature."
ESCAPED_REASON=$(escape_json "$REASON")
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "${ESCAPED_REASON}"
  }
}
EOF
exit 0
