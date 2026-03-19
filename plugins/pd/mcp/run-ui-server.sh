#!/bin/bash
# Bootstrap and run the pd UI server (Kanban board).
# Uses shared bootstrap-venv.sh for coordinated venv creation.
#
# Unlike MCP servers, this is browser-facing, not stdio protocol.
# Bootstrap diagnostics still go to stderr.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"
SERVER_SCRIPT="$PLUGIN_DIR/ui/__main__.py"

# Two PYTHONPATH entries: hooks/lib for entity_registry, $PLUGIN_DIR for ui module
export PYTHONPATH="$PLUGIN_DIR/hooks/lib:$PLUGIN_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

source "$SCRIPT_DIR/bootstrap-venv.sh"
bootstrap_venv "$VENV_DIR" "ui-server"

exec "$PYTHON" "$SERVER_SCRIPT" "$@"
