#!/bin/bash
# Bootstrap and run the MCP workflow-engine server.
# Uses shared bootstrap-venv.sh for coordinated venv creation.
#
# Called by Claude Code via plugin.json mcpServers — do NOT write to stdout
# (would corrupt MCP stdio protocol). All diagnostics go to stderr.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"
SERVER_SCRIPT="$SCRIPT_DIR/workflow_state_server.py"

export PYTHONPATH="$PLUGIN_DIR/hooks/lib${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

source "$SCRIPT_DIR/bootstrap-venv.sh"
bootstrap_venv "$VENV_DIR" "workflow-engine"

exec "$PYTHON" "$SERVER_SCRIPT" "$@"
