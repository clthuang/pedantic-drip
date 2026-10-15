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
    # submodule's .git is a file too, and so is an orphaned worktree's, where
    # git cannot answer: no workspace resolves there, and sync-cache publishes
    # nothing (may_publish_plugin_cache).
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

# Succeed when sync-cache.sh may publish the plugin from a checkout root, the
# directory detect_project_root answers (the .git test is made there).
# Publishes:
#   - a main checkout, where git's --git-dir and --git-common-dir are one
#     directory;
#   - where git cannot answer: a .git directory, or no .git at all (a git
#     archive export), as before.
# Publishes nothing, so no worktree overwrites the shared cache with its
# branch's plugin:
#   - a linked worktree, where --git-dir (<common dir>/worktrees/<name>)
#     differs from --git-common-dir;
#   - a .git FILE git cannot answer for, which may be a worktree: an orphaned
#     one whose <common dir>/worktrees/<name> is gone, or any worktree under a
#     failing git or a git older than 2.31 (it prints the --path-format option
#     it does not know back as a third line).
# A bare repository's worktree: its --git-dir differs from --git-common-dir,
# so nothing publishes from it (a bare repository has no main checkout).
# Usage: may_publish_plugin_cache "$root"
may_publish_plugin_cache() {
    local root="${1:-$PWD}" dirs git_dir common_dir
    if dirs=$(git -C "$root" rev-parse --path-format=absolute \
            --git-dir --git-common-dir 2>/dev/null); then
        git_dir="${dirs%%$'\n'*}"
        common_dir="${dirs#*$'\n'}"
        # Git answered only when it printed exactly two lines.
        if [[ "$common_dir" != "$dirs" && "$common_dir" != *$'\n'* ]]; then
            [[ "$git_dir" == "$common_dir" ]]
            return
        fi
    fi
    [[ ! -f "${root}/.git" ]]
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
