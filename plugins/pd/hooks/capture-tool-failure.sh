#!/usr/bin/env bash
# PostToolUseFailure hook: Capture tool failures as anti-pattern learnings
# Event: PostToolUseFailure (fires only on tool failures — no success-path filtering needed)
# Matcher: Bash|Edit|Write
# Output: {} (empty JSON, non-blocking)
#
# Verified stdin schema (PostToolUseFailure):
# {
#   "hook_event_name": "PostToolUseFailure",
#   "tool_name": "Bash",
#   "tool_input": {"command": "..."},  // or {"file_path": "..."} for Edit/Write
#   "error": "error message string",
#   "is_interrupt": false,
#   "tool_use_id": "...",
#   "session_id": "...",
#   "cwd": "..."
# }

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap
PROJECT_ROOT="${PD_TEST_PROJECT_ROOT:-$(detect_project_root)}"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"

# Read stdin
INPUT=$(cat)

# Config check: memory_model_capture_mode
PD_CONFIG="${PROJECT_ROOT}/.claude/pd.local.md"
CAPTURE_MODE=$(read_local_md_field "$PD_CONFIG" "memory_model_capture_mode" "silent")
if [[ "$CAPTURE_MODE" == "off" ]]; then
    echo '{}'; exit 0
fi

# Parse JSON with system python3
PARSED=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    tool_name = data.get('tool_name', '')
    error = data.get('error', '')
    tool_input = data.get('tool_input', {})
    # Extract command or file_path based on tool_name
    if tool_name == 'Bash':
        subject = tool_input.get('command', '')
    else:
        subject = tool_input.get('file_path', '')
    # Output: tool_name|subject|error (pipe-separated, newlines replaced)
    print(tool_name)
    print(subject.replace('\n', ' ')[:500])
    print(error.replace('\n', ' ')[:500])
except:
    print('')
    print('')
    print('')
" 2>/dev/null) || { echo '{}'; exit 0; }

# Split parsed output into variables
TOOL_NAME=$(echo "$PARSED" | sed -n '1p')
SUBJECT=$(echo "$PARSED" | sed -n '2p')
ERROR_MSG=$(echo "$PARSED" | sed -n '3p')

# If parsing failed (empty tool_name), exit
if [[ -z "$TOOL_NAME" ]]; then
    echo '{}'; exit 0
fi

# --- Exclusion filters ---

if [[ "$TOOL_NAME" == "Bash" ]]; then
    # Test runner exclusion
    if echo "$SUBJECT" | grep -qE '\b(pytest|jest|npm test|cargo test|go test|python -m pytest)\b' 2>/dev/null; then
        echo '{}'; exit 0
    fi

    # agent_sandbox/ exclusion
    if echo "$SUBJECT" | grep -q 'agent_sandbox/' 2>/dev/null; then
        echo '{}'; exit 0
    fi

    # Git read-only commands exclusion
    if echo "$SUBJECT" | grep -qE '\bgit\s+(status|diff|log|branch|tag|remote|show|rev-parse)\b' 2>/dev/null; then
        echo '{}'; exit 0
    fi
fi

if [[ "$TOOL_NAME" == "Edit" || "$TOOL_NAME" == "Write" ]]; then
    # agent_sandbox/ exclusion
    if echo "$SUBJECT" | grep -q 'agent_sandbox/' 2>/dev/null; then
        echo '{}'; exit 0
    fi
fi

# --- Pattern match error against categories ---

CATEGORY=""
if echo "$ERROR_MSG" | grep -qEi 'No such file|not found|ENOENT|FileNotFoundError' 2>/dev/null; then
    CATEGORY="Path error"
elif echo "$ERROR_MSG" | grep -qEi 'not compatible|version mismatch|unsupported|deprecated' 2>/dev/null; then
    CATEGORY="Compatibility"
elif echo "$ERROR_MSG" | grep -qEi 'ModuleNotFoundError|Cannot find module|ImportError|not installed' 2>/dev/null; then
    CATEGORY="Missing dependency"
elif echo "$ERROR_MSG" | grep -qEi 'SyntaxError|unexpected token|parse error' 2>/dev/null; then
    CATEGORY="Syntax error"
elif echo "$ERROR_MSG" | grep -qEi 'Permission denied|EACCES|Operation not permitted' 2>/dev/null; then
    CATEGORY="Permission"
fi

# No category match -> optionally log for debug, then exit
if [[ -z "$CATEGORY" ]]; then
    if [[ "${PD_HOOK_DEBUG:-}" == "1" ]]; then
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) tool=$TOOL_NAME error=$ERROR_MSG" >> ~/.claude/pd/unmatched-failures.log 2>/dev/null || true
    fi
    echo '{}'; exit 0
fi

# --- Build entry JSON and call semantic_memory.writer ---

# Truncate subject for name field (max 60 chars total with prefix)
BRIEF="${SUBJECT:0:30}"
# Build name: "Tool failure: {category} - {brief}" (max 60 chars)
ENTRY_NAME="Tool failure: ${CATEGORY} - ${BRIEF}"
ENTRY_NAME="${ENTRY_NAME:0:60}"

# Build description (min 20 chars): error + command
ENTRY_DESC="${ERROR_MSG} -- Command: ${SUBJECT}"
# Ensure min 20 chars
while [[ ${#ENTRY_DESC} -lt 20 ]]; do
    ENTRY_DESC="${ENTRY_DESC} (captured)"
done

# Try to get active feature ID from .meta.json
ACTIVE_FEATURE=""
FEATURES_DIR="${PROJECT_ROOT}/docs/features"
if [[ -d "$FEATURES_DIR" ]]; then
    ACTIVE_FEATURE=$(CTF_FEATURES_DIR="$FEATURES_DIR" python3 -c "
import json, os, glob
features_dir = os.environ['CTF_FEATURES_DIR']
for meta in glob.glob(os.path.join(features_dir, '*/.meta.json')):
    try:
        d = json.load(open(meta))
        if d.get('status') in ('active', 'in-progress'):
            print(os.path.basename(os.path.dirname(meta)))
            break
    except Exception: pass
" 2>/dev/null) || true
fi

ENTRY_REASONING="Automatic capture from PostToolUseFailure hook"
if [[ -n "$ACTIVE_FEATURE" ]]; then
    ENTRY_REASONING="${ENTRY_REASONING} in feature ${ACTIVE_FEATURE}"
fi

# Build entry JSON using python3 for safe escaping (pass values via env to avoid injection)
ENTRY_JSON=$(CTF_NAME="$ENTRY_NAME" CTF_DESC="$ENTRY_DESC" CTF_REASON="$ENTRY_REASONING" python3 -c "
import json, os
entry = {
    'name': os.environ['CTF_NAME'][:60],
    'description': os.environ['CTF_DESC'][:500],
    'reasoning': os.environ['CTF_REASON'],
    'category': 'anti-patterns',
    'source': 'session-capture',
    'confidence': 'low'
}
print(json.dumps(entry))
" 2>/dev/null) || { echo '{}'; exit 0; }

# Determine python to use for writer
VENV_PYTHON="${PD_TEST_VENV_PYTHON:-${PLUGIN_ROOT}/.venv/bin/python}"
if [[ ! -x "$VENV_PYTHON" ]]; then
    echo '{}'; exit 0
fi

# Call semantic_memory.writer synchronously (async: true in hooks.json handles non-blocking)
PYTHONPATH="${PLUGIN_ROOT}/hooks/lib" "$VENV_PYTHON" -m semantic_memory.writer \
    --action upsert \
    --global-store ~/.claude/pd/memory \
    --entry-json "$ENTRY_JSON" 2>/dev/null || true

echo '{}'
