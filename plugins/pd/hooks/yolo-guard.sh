#!/usr/bin/env bash
# PreToolUse hook: Block AskUserQuestion in YOLO mode, auto-select (Recommended) option
# Control 1: Keeps review loops running uninterrupted
# Control 2: Auto-selects next phase at completion prompts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap
PROJECT_ROOT="$(detect_project_root)"

PD_CONFIG="${PROJECT_ROOT}/.claude/pd.local.md"

# Read stdin
INPUT=$(cat)

# Fast path: skip python3 for non-AskUserQuestion tools (~99% of calls)
if [[ "$INPUT" != *"AskUserQuestion"* ]]; then
    exit 0
fi

# Confirm with proper JSON parsing (handles edge cases like AskUserQuestion in a string value)
TOOL_NAME=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_name', ''))
except:
    print('')
" 2>/dev/null)

if [[ "$TOOL_NAME" != "AskUserQuestion" ]]; then
    exit 0
fi

# Check YOLO mode
YOLO=$(read_local_md_field "$PD_CONFIG" "yolo_mode" "false")
if [[ "$YOLO" != "true" ]]; then
    exit 0
fi

# If YOLO is paused (usage limit hit), allow questions through
STATE_FILE="${PROJECT_ROOT}/.claude/.yolo-hook-state"
YOLO_PAUSED=$(read_hook_state "$STATE_FILE" "yolo_paused" "false")
if [[ "$YOLO_PAUSED" == "true" ]]; then
    exit 0
fi

# Parse question and options, check safety valve, find recommended option
RESULT=$(echo "$INPUT" | python3 -c "
import json, sys

SAFETY_KEYWORDS = [
    'circuit breaker',
    '5 iterations',
    'force approve',
    'abandon',
    'merge conflict',
    'YOLO MODE STOPPED',
    'pre-merge validation failed',
]

try:
    data = json.load(sys.stdin)
    questions = data.get('tool_input', {}).get('questions', [])
    if not questions:
        print('ALLOW')
        sys.exit(0)

    q = questions[0]
    question_text = q.get('question', '')

    # Safety valve: let critical questions through
    question_lower = question_text.lower()
    for kw in SAFETY_KEYWORDS:
        if kw.lower() in question_lower:
            print('ALLOW')
            sys.exit(0)

    # Also check option descriptions for safety keywords
    options = q.get('options', [])
    for opt in options:
        opt_text = (opt.get('label', '') + ' ' + opt.get('description', '')).lower()
        for kw in SAFETY_KEYWORDS:
            if kw.lower() in opt_text:
                print('ALLOW')
                sys.exit(0)

    # Find (Recommended) option, fall back to first
    selected = None
    for opt in options:
        label = opt.get('label', '')
        if '(Recommended)' in label or '(recommended)' in label:
            selected = label
            break

    if not selected and options:
        selected = options[0].get('label', 'first option')

    if not selected:
        selected = 'continue'

    print('DENY:' + selected)
except Exception as e:
    print('ALLOW')
" 2>/dev/null)

if [[ "$RESULT" == "ALLOW" ]]; then
    exit 0
fi

if [[ "$RESULT" == DENY:* ]]; then
    SELECTED="${RESULT#DENY:}"
    ESCAPED=$(escape_json "[YOLO_MODE] Auto-selected: '${SELECTED}'. Proceed as if user chose this option.")
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

# Fallback: allow through
exit 0
