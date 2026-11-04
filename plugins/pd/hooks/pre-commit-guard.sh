#!/usr/bin/env bash
# PreToolUse hook: reminders on git commits (a commit to main/master; tests when the project has them).
# It never makes a permission decision: "allow" would skip the user's permission prompt, so a
# pass-through prints nothing and a reminder goes to Claude as additionalContext.

set -euo pipefail
trap '' PIPE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/lib/session-start-helpers.sh"
install_err_trap
PROJECT_ROOT="$(detect_project_root)"

# Read the hook JSON from stdin (with timeout to prevent indefinite blocking)
# Uses gtimeout (macOS with coreutils) or timeout (Linux), falls back to cat
read_tool_input() {
    local timeout_cmd=""

    # Find available timeout command
    if command -v gtimeout &>/dev/null; then
        timeout_cmd="gtimeout 5"
    elif command -v timeout &>/dev/null; then
        timeout_cmd="timeout 5"
    fi

    if [[ -n "$timeout_cmd" ]]; then
        $timeout_cmd cat || echo '{}'
    else
        # Fallback: read without timeout (stdin from Claude should close promptly)
        cat
    fi
}

# Check if on protected branch
# Protected: main (releases), master (legacy)
is_protected_branch() {
    local branch="$1"
    [[ "$branch" == "main" || "$branch" == "master" ]]
}

# Check if test files exist in the project
has_test_files() {
    local patterns=(
        "test_*.py"
        "*_test.py"
        "*.test.ts"
        "*.test.js"
        "*.test.tsx"
        "*.test.jsx"
        "*_test.go"
        "Test*.java"
        "*Test.java"
        "*_spec.rb"
        "*.spec.ts"
        "*.spec.js"
    )

    for pattern in "${patterns[@]}"; do
        if find "${PROJECT_ROOT}" -name "$pattern" -type f \
            -not -path "*/node_modules/*" \
            -not -path "*/.git/*" \
            -not -path "*/vendor/*" \
            -not -path "*/.venv/*" \
            -not -path "*/venv/*" \
            2>/dev/null | head -1 | grep -q .; then
            return 0
        fi
    done

    return 1
}

# A reminder for Claude, with no permission decision.
remind() {
    safe_emit_hook_json "{\"hookSpecificOutput\": {\"hookEventName\": \"PreToolUse\", \"additionalContext\": \"$(escape_json "$1")\"}}"
}

main() {
    local input target dir branch
    input=$(read_tool_input) || exit 0  # unreadable input: no opinion, the normal permission flow decides
    case "$input" in *commit*|*\$\'*) ;; *) exit 0 ;; esac

    # Where the command's `git commit` runs and the branch it lands on, after any checkout or switch
    # earlier in the command (lib/commit_target.py); nothing means it doesn't commit.
    target=$(printf '%s' "$input" | python3 "${SCRIPT_DIR}/lib/commit_target.py" 2>/dev/null) || exit 0
    [[ -n "$target" ]] || exit 0
    dir=${target%%$'\t'*}
    branch=${target#*$'\t'}
    [[ -n "$branch" ]] || branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

    if is_protected_branch "$branch"; then
        remind "Reminder: Committing directly to '${branch}'. Consider using a work item branch for larger changes."
    elif has_test_files; then
        remind "Reminder: Test files exist in this project. Have you run the tests?"
    fi
    exit 0
}
main
