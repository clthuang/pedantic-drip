#!/bin/bash
# Bootstrap and run the MCP workflow-engine server.
# Shared venv with memory server -- each server's bootstrap handles its own deps.
# Resolution order: existing venv -> system python3 -> uv bootstrap -> pip bootstrap.
#
# Called by Claude Code via plugin.json mcpServers -- do NOT write to stdout
# (would corrupt MCP stdio protocol). All diagnostics go to stderr.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"
SERVER_SCRIPT="$SCRIPT_DIR/workflow_state_server.py"

export PYTHONPATH="$PLUGIN_DIR/hooks/lib${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

# Step 1: Fast path -- existing venv
if [[ -x "$VENV_DIR/bin/python" ]]; then
    exec "$VENV_DIR/bin/python" "$SERVER_SCRIPT"
fi

# Step 2: System python3 with required deps already available
if python3 -c "import mcp.server.fastmcp" 2>/dev/null; then
    exec python3 "$SERVER_SCRIPT"
fi

# Step 3: Bootstrap with uv (preferred)
if command -v uv >/dev/null 2>&1; then
    echo "workflow-engine: bootstrapping venv with uv at $VENV_DIR..." >&2
    uv venv "$VENV_DIR" >&2
    uv pip install --python "$VENV_DIR/bin/python" "mcp>=1.0,<2" >&2
    exec "$VENV_DIR/bin/python" "$SERVER_SCRIPT"
fi

# Step 4: Bootstrap with pip (fallback)
echo "workflow-engine: bootstrapping venv with pip at $VENV_DIR..." >&2
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q "mcp>=1.0,<2" >&2
exec "$VENV_DIR/bin/python" "$SERVER_SCRIPT"
