#!/usr/bin/env bash
# Shared library for hook utilities
# Source this file at the start of hook scripts:
#   source "${SCRIPT_DIR}/lib/common.sh"

# Detect project root: use PWD (where Claude is running), not PLUGIN_ROOT (cached plugin location)
# This is critical because PLUGIN_ROOT points to ~/.claude/plugins/cache/... which has stale data
detect_project_root() {
    local dir="${PWD}"

    # Walk up to find .git (project marker)
    while [[ "$dir" != "/" ]]; do
        if [[ -d "${dir}/.git" ]]; then
            echo "$dir"
            return 0
        fi
        dir=$(dirname "$dir")
    done

    # Fallback to PWD if no markers found
    echo "${PWD}"
}

# Extract working directory from a command string
# Handles patterns like:
#   cd /path && git commit...
#   (cd /path && git commit...)
#   git -C /path commit...
#   git commit... (returns empty, meaning use PWD)
extract_command_workdir() {
    local command="$1"

    # Strip leading parenthesis for subshell commands
    command="${command#(}"

    # Match: cd /path && ... or cd "/path" && ...
    if [[ "$command" =~ ^[[:space:]]*cd[[:space:]]+[\"\']?([^\"\'[:space:]]+)[\"\']?[[:space:]]*\&\& ]]; then
        echo "${BASH_REMATCH[1]}"
        return 0
    fi

    # Match: git -C /path ... or git -C "/path" ...
    if [[ "$command" =~ git[[:space:]]+-C[[:space:]]+[\"\']?([^\"\'[:space:]]+)[\"\']? ]]; then
        echo "${BASH_REMATCH[1]}"
        return 0
    fi

    # No directory prefix found - return empty (caller should use PWD)
    echo ""
}

# Run git command in the appropriate directory for a given command string
# Usage: run_git_in_command_context "$command" rev-parse --abbrev-ref HEAD
run_git_in_command_context() {
    local command="$1"
    shift
    local git_args=("$@")

    local workdir
    workdir=$(extract_command_workdir "$command")

    if [[ -n "$workdir" ]] && [[ -d "$workdir" ]]; then
        git -C "$workdir" "${git_args[@]}" 2>/dev/null
    else
        git "${git_args[@]}" 2>/dev/null
    fi
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
# Usage: read_local_md_field "$file" "field_name" "default_value"
read_local_md_field() {
    local file="$1" field="$2" default="${3:-}"
    if [[ ! -f "$file" ]]; then
        echo "$default"
        return
    fi
    local value
    value=$(grep "^${field}:" "$file" 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d ' ' || echo "")
    if [[ -z "$value" || "$value" == "null" ]]; then
        echo "$default"
    else
        echo "$value"
    fi
}

# Read a key from a hook state file (key=value format)
# Usage: read_hook_state "$file" "key" "default"
read_hook_state() {
    local file="$1" key="$2" default="${3:-}"
    if [[ ! -f "$file" ]]; then
        echo "$default"
        return
    fi
    local value
    value=$(grep "^${key}=" "$file" 2>/dev/null | head -1 | cut -d'=' -f2- || echo "")
    if [[ -z "$value" || "$value" == "null" ]]; then
        echo "$default"
    else
        echo "$value"
    fi
}

# Write a key=value to a hook state file (create or update)
# Usage: write_hook_state "$file" "key" "value"
write_hook_state() {
    local file="$1" key="$2" value="$3"
    local dir
    dir=$(dirname "$file")
    [[ -d "$dir" ]] || mkdir -p "$dir"
    if [[ -f "$file" ]] && grep -q "^${key}=" "$file" 2>/dev/null; then
        local tmp="${file}.tmp"
        sed "s/^${key}=.*/${key}=${value}/" "$file" > "$tmp" && mv "$tmp" "$file"
    else
        echo "${key}=${value}" >> "$file"
    fi
}

# Install ERR trap that outputs valid JSON on uncaught errors.
# Call immediately after sourcing common.sh in hook scripts.
install_err_trap() {
    trap 'echo "{}" 2>/dev/null; exit 0' ERR
}
