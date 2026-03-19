#!/bin/bash
# Bootstrap and run the MCP memory server.
# Uses shared bootstrap-venv.sh for coordinated venv creation.
#
# Called by Claude Code via plugin.json mcpServers — do NOT write to stdout
# (would corrupt MCP stdio protocol). All diagnostics go to stderr.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"
SERVER_SCRIPT="$SCRIPT_DIR/memory_server.py"

export PYTHONPATH="$PLUGIN_DIR/hooks/lib${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

# --- .env loading (R5) ---
# Export only known API key vars from project .env (cwd = project root).
# Supports KEY=value, KEY="value", KEY='value' — not multi-line values
if [ -f ".env" ]; then
    for _key in GEMINI_API_KEY OPENAI_API_KEY VOYAGE_API_KEY MEMORY_EMBEDDING_PROVIDER; do
        _val=$(grep -E "^${_key}=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^["'"'"']//;s/["'"'"']$//')
        if [ -n "$_val" ]; then export "$_key=$_val"; fi
    done
fi

source "$SCRIPT_DIR/bootstrap-venv.sh"
bootstrap_venv "$VENV_DIR" "memory-server"

# --- Optional embedding SDK (R6) ---
# MEMORY_EMBEDDING_PROVIDER may come from .env, shell env, or .claude/pd.local.md
_PROVIDER="${MEMORY_EMBEDDING_PROVIDER:-}"
if [ -z "$_PROVIDER" ] && [ -f ".claude/pd.local.md" ]; then
    _PROVIDER=$(grep -E "^memory_embedding_provider:" .claude/pd.local.md 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d '[:space:]')
fi
# Default to gemini (matches Python config.py DEFAULTS)
_PROVIDER="${_PROVIDER:-gemini}"
if [ -n "$_PROVIDER" ]; then
    case "$_PROVIDER" in
        gemini)  _PKG="google-genai>=1.0,<2"; _IMPORT="google.genai" ;;
        openai)  _PKG="openai>=1.0,<3"; _IMPORT="openai" ;;
        voyage)  _PKG="voyageai>=0.3,<1"; _IMPORT="voyageai" ;;
        ollama)  _PKG="ollama>=0.4,<1"; _IMPORT="ollama" ;;
        *)       _PKG=""; _IMPORT="" ;;
    esac
    if [ -n "$_PKG" ] && [ -n "$_IMPORT" ]; then
        if ! "$PYTHON" -c "import $_IMPORT" 2>/dev/null; then
            echo "memory-server: installing ${_PROVIDER} SDK..." >&2
            uv pip install --python "$PYTHON" "$_PKG" >&2 || \
                echo "memory-server: WARNING: failed to install ${_PROVIDER} SDK" >&2
        fi
    fi
fi

exec "$PYTHON" "$SERVER_SCRIPT" "$@"
