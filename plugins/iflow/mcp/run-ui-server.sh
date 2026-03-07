#!/bin/bash
# Bootstrap and run the iflow UI server (Kanban board).
# Adapts the run-workflow-server.sh pattern.
# Unlike MCP servers, this writes to stdout (browser-facing, not stdio protocol).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"

# Two PYTHONPATH entries: hooks/lib for entity_registry, $PLUGIN_DIR for ui module
export PYTHONPATH="$PLUGIN_DIR/hooks/lib:$PLUGIN_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

# Step 1: Fast path -- existing venv
if [[ -x "$VENV_DIR/bin/python" ]]; then
    exec "$VENV_DIR/bin/python" "$PLUGIN_DIR/ui/__main__.py" "$@"
fi

# Step 2: System python3 with required deps already available
if python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    exec python3 "$PLUGIN_DIR/ui/__main__.py" "$@"
fi

# Step 3: Bootstrap with uv (preferred)
if command -v uv >/dev/null 2>&1; then
    echo "ui-server: bootstrapping venv with uv at $VENV_DIR..." >&2
    uv venv "$VENV_DIR" >&2
    uv pip install --python "$VENV_DIR/bin/python" "fastapi>=0.128.3" "uvicorn" "jinja2" >&2
    exec "$VENV_DIR/bin/python" "$PLUGIN_DIR/ui/__main__.py" "$@"
fi

# Step 4: Bootstrap with pip (fallback)
echo "ui-server: bootstrapping venv with pip at $VENV_DIR..." >&2
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q "fastapi>=0.128.3" "uvicorn" "jinja2" >&2
exec "$VENV_DIR/bin/python" "$PLUGIN_DIR/ui/__main__.py" "$@"
