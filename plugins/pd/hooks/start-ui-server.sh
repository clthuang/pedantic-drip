#!/usr/bin/env bash
# SessionStart hook: auto-start UI server (Kanban board) in background

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap
PROJECT_ROOT="$(detect_project_root)"

PD_CONFIG="${PROJECT_ROOT}/.claude/pd.local.md"

# Read config
UI_ENABLED=$(read_local_md_field "$PD_CONFIG" "ui_server_enabled" "true")
PORT=$(read_local_md_field "$PD_CONFIG" "ui_server_port" "8718")

# Validate port is numeric
if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
    PORT=8718
fi

# Helper: emit SessionStart JSON and exit
emit_json() {
    local ctx="$1"
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "$(escape_json "$ctx")"
  }
}
EOF
    exit 0
}

# Disabled by config
if [[ "$UI_ENABLED" != "true" ]]; then
    emit_json ""
fi

# python3 required for port check
if ! command -v python3 &>/dev/null; then
    emit_json ""
fi

# Check if port is already in use (server already running)
if python3 -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('127.0.0.1', $PORT))
    s.close()
    sys.exit(0)
except:
    sys.exit(1)
" 2>/dev/null; then
    emit_json ""
fi

# Port is free — start the server in background
mkdir -p ~/.claude/pd
nohup bash "$PLUGIN_ROOT/mcp/run-ui-server.sh" --port "$PORT" > ~/.claude/pd/ui-server.log 2>&1 & disown

# Brief wait, then verify startup
sleep 0.5

if python3 -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('127.0.0.1', $PORT))
    s.close()
    sys.exit(0)
except:
    sys.exit(1)
" 2>/dev/null; then
    emit_json "pd UI server running at http://localhost:$PORT/"
else
    emit_json "pd UI server starting in background (first run may take longer). Check ~/.claude/pd/ui-server.log if it fails."
fi
