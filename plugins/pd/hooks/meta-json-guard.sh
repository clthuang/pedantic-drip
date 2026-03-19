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

# Check if MCP workflow tools are available via bootstrap sentinel.
# Enhanced: reads sentinel content, validates interpreter path + version.
# Falls back to mtime check for legacy empty sentinels.
check_mcp_available() {
    local sentinel_file
    sentinel_file=$(ls "$HOME"/.claude/plugins/cache/*/pd*/*/.venv/.bootstrap-complete 2>/dev/null | head -1) || true

    if [[ -z "$sentinel_file" ]] || [[ ! -f "$sentinel_file" ]]; then
        return 1
    fi

    # Read sentinel content (format: <path>:<version>)
    local interp_path="" interp_version=""
    IFS=: read -r interp_path interp_version < "$sentinel_file" 2>/dev/null || true

    if [[ -n "$interp_path" ]] && [[ -n "$interp_version" ]]; then
        # Content present: validate interpreter path exists
        if [[ ! -x "$interp_path" ]]; then
            MCP_UNAVAILABLE_REASON="stale-sentinel"
            return 1
        fi

        # Parse version and validate >= 3.12
        local major="${interp_version%%.*}"
        local minor="${interp_version#*.}"

        # Guard against non-numeric values
        [[ -n "$minor" ]] && [[ "$minor" -eq "$minor" ]] 2>/dev/null || { MCP_UNAVAILABLE_REASON="stale-sentinel"; return 1; }
        [[ -n "$major" ]] && [[ "$major" -eq "$major" ]] 2>/dev/null || { MCP_UNAVAILABLE_REASON="stale-sentinel"; return 1; }

        # Version too low check (correctly handles Python 4.x: major > 3 passes)
        if [[ "$major" -lt 3 ]] 2>/dev/null || { [[ "$major" -eq 3 ]] && [[ "$minor" -lt 12 ]]; } 2>/dev/null; then
            MCP_UNAVAILABLE_REASON="stale-sentinel"
            return 1
        fi

        # Both OK — interpreter exists and version is adequate
        return 0
    fi

    # Legacy sentinel: content empty, fall back to mtime check (< 24h = recent)
    if [[ -n "$(find "$sentinel_file" -mmin -1440 -print 2>/dev/null)" ]]; then
        return 0
    fi

    # Legacy sentinel is stale (> 24h)
    MCP_UNAVAILABLE_REASON="stale-sentinel"
    return 1
}

# Log guard event (FR-11 instrumentation)
log_guard_event() {
    local file_path="$1"
    local tool_name="$2"
    local action="${3:-}"
    local log_dir="$HOME/.claude/pd"
    local log_file="$log_dir/meta-json-guard.log"
    local timestamp feature_id action_field

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

    # Build optional action field
    if [[ -n "$action" ]]; then
        action_field=",\"action\":\"$(escape_json "$action")\""
    else
        action_field=""
    fi

    # Append JSONL (>> is atomic for lines < PIPE_BUF on POSIX)
    echo "{\"timestamp\":\"$timestamp\",\"tool\":\"$tool_name\",\"path\":\"$(escape_json "$file_path")\",\"feature_id\":\"$feature_id\"${action_field}}" >> "$log_file"
}

# Degraded permit: allow write when MCP tools unavailable
MCP_UNAVAILABLE_REASON=""
if ! check_mcp_available; then
    if [[ "$MCP_UNAVAILABLE_REASON" == "stale-sentinel" ]]; then
        log_guard_event "$FILE_PATH" "$TOOL_NAME" "permit-degraded-stale-sentinel"
    else
        log_guard_event "$FILE_PATH" "$TOOL_NAME" "permit-degraded"
    fi
    echo '{}'
    exit 0
fi

log_guard_event "$FILE_PATH" "$TOOL_NAME"

# Deny (inline JSON -- no shared output_block helper exists across hooks)
REASON="Direct .meta.json writes are blocked. Use MCP workflow tools instead: transition_phase(feature_type_id, target_phase) to enter a phase, complete_phase(feature_type_id, phase) to finish a phase, or init_feature_state(...) to create a new feature. The feature_type_id format is \"feature:{id}-{slug}\" (e.g., \"feature:041-meta-json-guard-degradation\"). If MCP workflow tools are not available in this session, the guard will allow direct writes as a fallback."
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
