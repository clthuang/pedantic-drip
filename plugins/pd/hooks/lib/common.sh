#!/usr/bin/env bash
# Shared library for hook utilities
# Source this file at the start of hook scripts:
#   source "${SCRIPT_DIR}/lib/common.sh"

# Detect project root: use PWD (where Claude is running), not PLUGIN_ROOT (cached plugin location)
# This is critical because PLUGIN_ROOT points to ~/.claude/plugins/cache/... which has stale data
detect_project_root() {
    local dir="${PWD}"

    # Walk up to find .git (project marker): a directory in a main checkout,
    # a file in a linked worktree, so a worktree roots at itself. A git
    # submodule's .git is a file too, and so is an orphaned worktree's.
    while [[ "$dir" != "/" ]]; do
        if [[ -e "${dir}/.git" ]]; then
            echo "$dir"
            return 0
        fi
        dir=$(dirname "$dir")
    done

    # Fallback to PWD if no markers found
    echo "${PWD}"
}

# Escape string for JSON output
escape_json() {
    local input="$1"
    local output=""
    local i char
    for (( i=0; i<${#input}; i++ )); do
        char="${input:$i:1}"
        case "$char" in
            '\') output+='\\';;
            '"') output+='\"';;
            $'\n') output+='\n';;
            $'\r') output+='\r';;
            $'\t') output+='\t';;
            *) output+="$char";;
        esac
    done
    printf '%s' "$output"
}

# Read a YAML frontmatter field from a .local.md file
# Usage: read_local_md_field "$file" "field_name" "default_value" [preserve_spaces]
# When preserve_spaces=1, trims only leading/trailing whitespace and surrounding
# quotes instead of stripping all whitespace (needed for values like cron exprs).
read_local_md_field() {
    local file="$1" field="$2" default="${3:-}" preserve_spaces="${4:-0}"
    if [[ ! -f "$file" ]]; then
        echo "$default"
        return
    fi
    local value
    if [[ "$preserve_spaces" == "1" ]]; then
        value=$(grep "^${field}:" "$file" 2>/dev/null \
            | head -1 \
            | sed -e 's/^[^:]*://' \
                  -e 's/^[[:space:]]*//' \
                  -e 's/[[:space:]]*$//' \
                  -e 's/^"\(.*\)"$/\1/' \
                  -e "s/^'\(.*\)'\$/\1/" || echo "")
    else
        value=$(grep "^${field}:" "$file" 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d ' ' || echo "")
    fi
    if [[ -z "$value" || "$value" == "null" ]]; then
        echo "$default"
    else
        echo "$value"
    fi
}

# Install ERR trap that outputs valid JSON on uncaught errors.
# Call immediately after sourcing common.sh in hook scripts.
install_err_trap() {
    trap 'echo "{}" 2>/dev/null; exit 0' ERR
}
