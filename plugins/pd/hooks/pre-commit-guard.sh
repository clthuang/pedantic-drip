#!/usr/bin/env bash
# PreToolUse hook: guard git commits

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
# Feature 110 FR-4.6 / Task 14.6: load venv-discovery helper for pd_state_diff
# invocation. Fail-soft sourcing — absence of helpers is non-fatal.
# shellcheck source=/dev/null
[[ -f "${SCRIPT_DIR}/lib/session-start-helpers.sh" ]] && \
    source "${SCRIPT_DIR}/lib/session-start-helpers.sh" 2>/dev/null || true
install_err_trap
PROJECT_ROOT="$(detect_project_root)"

# Read tool input from stdin (with timeout to prevent indefinite blocking)
# Uses gtimeout (macOS with coreutils) or timeout (Linux), falls back to cat
read_tool_input() {
    local input timeout_cmd=""

    # Find available timeout command
    if command -v gtimeout &>/dev/null; then
        timeout_cmd="gtimeout 5"
    elif command -v timeout &>/dev/null; then
        timeout_cmd="timeout 5"
    fi

    if [[ -n "$timeout_cmd" ]]; then
        input=$($timeout_cmd cat || echo '{}')
    else
        # Fallback: read without timeout (stdin from Claude should close promptly)
        input=$(cat)
    fi

    # Extract command from JSON input
    # Input format: {"tool_name": "Bash", "tool_input": {"command": "..."}}
    echo "$input" | python3 -c "
import json
import sys
try:
    data = json.load(sys.stdin)
    cmd = data.get('tool_input', {}).get('command', '')
    print(cmd)
except:
    print('')
" 2>/dev/null
}

# Get git branch for the command's target directory
get_branch_for_command() {
    local command="$1"
    run_git_in_command_context "$command" rev-parse --abbrev-ref HEAD || echo ""
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

# Output: allow the action
output_allow() {
    local context="${1:-Allowed}"
    local escaped
    escaped=$(escape_json "$context")
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "${escaped}"
  }
}
EOF
}

# Output: block the action
output_block() {
    local reason="$1"
    local escaped
    escaped=$(escape_json "$reason")
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "${escaped}"
  }
}
EOF
}

# Output: ask user to confirm
output_ask() {
    local reason="$1"
    local escaped
    escaped=$(escape_json "$reason")
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "${escaped}"
  }
}
EOF
}

# Feature 110 FR-4.6 / Task 14.6 helpers ---------------------------------
# Resolve base branch via .claude/pd.local.md → fallback chain:
#   1. Parse `base_branch:` from .claude/pd.local.md.
#   2. If literal 'auto', resolve via `git remote show origin | grep "HEAD branch"`.
#   3. On any failure, fall back to `develop`.
# Fail-soft: every step swallows errors and falls through to the final default.
resolve_pd_base_branch() {
    local cfg="${PROJECT_ROOT}/.claude/pd.local.md"
    local raw=""
    if [[ -f "$cfg" ]]; then
        # Match `base_branch: <value>` (whitespace-tolerant; value to EOL).
        raw=$(grep -E '^[[:space:]]*base_branch:' "$cfg" 2>/dev/null \
            | head -1 \
            | sed -E 's/^[[:space:]]*base_branch:[[:space:]]*//' \
            | tr -d '\r' \
            | awk '{print $1}' \
            || true)
    fi

    if [[ -z "$raw" || "$raw" == "auto" ]]; then
        local detected=""
        detected=$(git remote show origin 2>/dev/null \
            | awk '/HEAD branch/ {print $NF}' \
            | head -1 || true)
        if [[ -n "$detected" && "$detected" != "(unknown)" ]]; then
            echo "$detected"
            return 0
        fi
        echo "develop"
        return 0
    fi
    echo "$raw"
}

# Find the venv python (delegates to session-start-helpers conventions).
find_pd_venv_python() {
    local plugin_root="${PLUGIN_ROOT:-}"
    if [[ -n "$plugin_root" && -x "$plugin_root/.venv/bin/python" ]]; then
        echo "$plugin_root/.venv/bin/python"
        return 0
    fi
    # Cache layout fallback.
    local cached
    cached=$(ls -d "$HOME"/.claude/plugins/cache/*/pd*/*/.venv/bin/python 2>/dev/null | head -1 || true)
    if [[ -n "$cached" && -x "$cached" ]]; then
        echo "$cached"
        return 0
    fi
    # Dev-workspace fallback.
    if [[ -x "${PROJECT_ROOT}/plugins/pd/.venv/bin/python" ]]; then
        echo "${PROJECT_ROOT}/plugins/pd/.venv/bin/python"
        return 0
    fi
    # System fallback.
    if command -v python3 &>/dev/null; then
        echo "python3"
        return 0
    fi
    return 1
}

# Find the pd_state_diff.py script (worktree-aware).
find_pd_state_diff_script() {
    local candidates=(
        "${PROJECT_ROOT}/plugins/pd/scripts/pd_state_diff.py"
        "${SCRIPT_DIR}/../scripts/pd_state_diff.py"
    )
    local c
    for c in "${candidates[@]}"; do
        if [[ -f "$c" ]]; then
            echo "$c"
            return 0
        fi
    done
    return 1
}

# Invoke pd_state_diff and write output to ${PROJECT_ROOT}/pd-state.diff.md.
# Per AC-6.6 + Task 14.6 DoD: on ANY failure, emit warn-line to stderr and
# return 0 (does NOT block the commit).
emit_pd_state_diff() {
    local base
    base=$(resolve_pd_base_branch 2>/dev/null || echo "develop")

    local script
    if ! script=$(find_pd_state_diff_script); then
        echo "[pd-state-diff] failed: script not found" >&2
        return 0
    fi

    local py
    if ! py=$(find_pd_venv_python); then
        echo "[pd-state-diff] failed: python interpreter not found" >&2
        return 0
    fi

    local out_path="${PROJECT_ROOT}/pd-state.diff.md"
    # The script handles its own atomic-rename when --output is supplied.
    # 2>/dev/null on the call site keeps the hook's own stderr clean of any
    # Python tracebacks (preserves valid JSON-on-stdout discipline). The
    # || true keeps fail-open semantics.
    if ! "$py" "$script" --base "$base" --output "$out_path" 2>/dev/null; then
        echo "[pd-state-diff] failed: invocation returned non-zero" >&2
    fi
    return 0
}

# Main
main() {
    local command
    command=$(read_tool_input)

    # Only process git commit commands
    if [[ ! "$command" =~ git[[:space:]]+commit ]]; then
        output_allow
        exit 0
    fi

    # Feature 110 FR-4.6: emit pd-state.diff.md (gitignored) as a side effect
    # BEFORE the commit completes. Failures do NOT block the commit (AC-6.6).
    emit_pd_state_diff || true

    # Check branch for the command's target directory
    local branch
    branch=$(get_branch_for_command "$command")

    if is_protected_branch "$branch"; then
        output_allow "Reminder: Committing directly to '${branch}'. Consider using a feature branch for larger changes."
        exit 0
    fi

    # Check for test files and remind
    if has_test_files; then
        output_allow "Reminder: Test files exist in this project. Have you run the tests?"
    else
        output_allow
    fi

    exit 0
}

main
