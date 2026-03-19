#!/usr/bin/env bash
# SessionStart hook: sync plugin source files to cache directory
# Ensures Claude Code always uses the latest plugin code

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap

# Find the source project root
SOURCE_ROOT="$(detect_project_root)"
SOURCE_PLUGIN="${SOURCE_ROOT}/plugins/pd"

# Detect installed plugin path dynamically from installed_plugins.json
INSTALLED_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
CACHE_PLUGIN=""

if [[ -f "$INSTALLED_PLUGINS" ]]; then
    # Extract installPath for pd@my-local-plugins
    CACHE_PLUGIN=$(grep -o '"installPath": *"[^"]*my-local-plugins/pd/[^"]*"' "$INSTALLED_PLUGINS" 2>/dev/null | head -1 | sed 's/"installPath": *"\([^"]*\)"/\1/' || true)
fi

# Exit gracefully if pd not found in installed_plugins.json
if [[ -z "$CACHE_PLUGIN" ]]; then
    echo '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":""}}'
    exit 0
fi

# Sync pd plugin
if [[ -d "${SOURCE_PLUGIN}" && -f "${SOURCE_PLUGIN}/.claude-plugin/plugin.json" ]]; then
    rsync -a --delete --exclude='.venv' "${SOURCE_PLUGIN}/" "${CACHE_PLUGIN}/" 2>/dev/null || true
fi

# Also sync marketplace.json to marketplace cache
SOURCE_MARKETPLACE="${SOURCE_ROOT}/.claude-plugin/marketplace.json"
CACHE_MARKETPLACE="$HOME/.claude/plugins/marketplaces/my-local-plugins/.claude-plugin/marketplace.json"

if [[ -f "$SOURCE_MARKETPLACE" && -d "$(dirname "$CACHE_MARKETPLACE")" ]]; then
    cp "$SOURCE_MARKETPLACE" "$CACHE_MARKETPLACE" 2>/dev/null || true
fi

# Output required JSON
echo '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":""}}'
exit 0
