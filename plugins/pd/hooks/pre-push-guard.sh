#!/usr/bin/env bash
# PreToolUse hook: validate .meta.json consistency before git push
# Catches: status=completed without 'completed' timestamp (breaks CI)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap
PROJECT_ROOT="$(detect_project_root)"

# Read tool input from stdin
INPUT=$(cat)

# Only intercept Bash tool calls containing "git push"
COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

if [[ "$COMMAND" != *"git push"* ]]; then
    echo '{}'
    exit 0
fi

# Check all .meta.json files for consistency
ARTIFACTS_ROOT="${PROJECT_ROOT}/docs"
ERRORS=()

if [[ -d "${ARTIFACTS_ROOT}/features" ]]; then
    while IFS= read -r meta_path; do
        result=$(python3 -c "
import json, sys
with open('$meta_path') as f:
    meta = json.load(f)
status = meta.get('status', '')
completed = meta.get('completed')
if status in ('completed', 'abandoned') and completed is None:
    slug = '$meta_path'.split('/')[-2]
    print(f'{slug}: status={status} but no completed timestamp')
" 2>/dev/null || true)
        if [[ -n "$result" ]]; then
            ERRORS+=("$result")
        fi
    done < <(find "${ARTIFACTS_ROOT}/features" -name ".meta.json" -maxdepth 2 2>/dev/null)
fi

if [[ ${#ERRORS[@]} -gt 0 ]]; then
    MSG="BLOCKED: .meta.json consistency errors (would fail CI):\n"
    for err in "${ERRORS[@]}"; do
        MSG+="  - $err\n"
    done
    MSG+="\nFix: run pd:doctor --fix or use complete_phase MCP tool."
    ESCAPED=$(escape_json "$(echo -e "$MSG" | tr '\n' ' ')")
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "${ESCAPED}"
  }
}
EOF
    exit 0
fi

echo '{}'
