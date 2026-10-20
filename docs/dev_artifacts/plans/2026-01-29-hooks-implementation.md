# Hooks Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add SessionStart and PreToolUse hooks to the my-ai-setup plugin for workflow context injection and commit guardrails.

**Architecture:** Two bash scripts registered via hooks.json. SessionStart injects workflow context on every session. PreToolUse guards git commits by blocking direct commits to main/master and reminding about tests.

**Tech Stack:** Bash, JSON, Claude Code hooks API

---

## Task 1: Create hooks directory and registry

**Files:**
- Create: `hooks/hooks.json`

**Step 1: Create hooks directory**

```bash
mkdir -p hooks
```

**Step 2: Create hooks.json registry**

Create `hooks/hooks.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pre-commit-guard.sh"
          }
        ]
      }
    ]
  }
}
```

**Step 3: Validate JSON syntax**

Run: `python3 -c "import json; json.load(open('hooks/hooks.json')); print('Valid JSON')"`
Expected: `Valid JSON`

**Step 4: Commit**

```bash
git add hooks/hooks.json
git commit -m "feat(hooks): add hooks registry"
```

---

## Task 2: Implement session-start.sh hook

**Files:**
- Create: `hooks/session-start.sh`

**Step 1: Create the script with shebang and strict mode**

Create `hooks/session-start.sh`:

```bash
#!/usr/bin/env bash
# SessionStart hook: inject workflow context and surface active feature

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
```

**Step 2: Add helper function to escape JSON strings**

Append to `hooks/session-start.sh`:

```bash
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
```

**Step 3: Add feature detection logic**

Append to `hooks/session-start.sh`:

```bash
# Find active feature (most recently modified .meta.json)
find_active_feature() {
    local features_dir="${PLUGIN_ROOT}/docs/features"

    if [[ ! -d "$features_dir" ]]; then
        return 1
    fi

    # Find most recently modified .meta.json
    local latest_meta
    latest_meta=$(find "$features_dir" -name ".meta.json" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)

    if [[ -z "$latest_meta" ]]; then
        return 1
    fi

    echo "$latest_meta"
}

# Parse feature metadata
parse_feature_meta() {
    local meta_file="$1"

    if [[ ! -f "$meta_file" ]]; then
        return 1
    fi

    # Extract fields using python (more reliable than bash JSON parsing)
    python3 -c "
import json
import sys
with open('$meta_file') as f:
    meta = json.load(f)
    print(meta.get('id', 'unknown'))
    print(meta.get('name', 'unknown'))
    print(meta.get('mode', 'Standard'))
    print(meta.get('worktree', ''))
" 2>/dev/null
}

# Detect current phase from existing artifacts
detect_phase() {
    local feature_dir="$1"

    if [[ -f "${feature_dir}/tasks.md" ]]; then
        echo "implementing"
    elif [[ -f "${feature_dir}/design.md" ]]; then
        echo "creating-tasks"
    elif [[ -f "${feature_dir}/spec.md" ]]; then
        echo "designing"
    elif [[ -f "${feature_dir}/brainstorm.md" ]]; then
        echo "specifying"
    else
        echo "brainstorming"
    fi
}
```

**Step 4: Add main logic and output**

Append to `hooks/session-start.sh`:

```bash
# Build context message
build_context() {
    local context=""
    local meta_file

    meta_file=$(find_active_feature)

    if [[ -n "$meta_file" ]]; then
        local feature_dir
        feature_dir=$(dirname "$meta_file")

        # Parse metadata
        local meta_output
        meta_output=$(parse_feature_meta "$meta_file")

        if [[ -n "$meta_output" ]]; then
            local id name mode worktree phase
            id=$(echo "$meta_output" | sed -n '1p')
            name=$(echo "$meta_output" | sed -n '2p')
            mode=$(echo "$meta_output" | sed -n '3p')
            worktree=$(echo "$meta_output" | sed -n '4p')
            phase=$(detect_phase "$feature_dir")

            context="You're working on feature ${id}-${name} (${mode} mode).\n"
            context+="Current phase: ${phase}\n"
            if [[ -n "$worktree" ]]; then
                context+="Worktree: ${worktree}\n"
            fi
            context+="\n"
        fi
    fi

    # Always include workflow overview
    context+="Available commands: /create-feature | /brainstorm → /specify → /design → /create-tasks → /implement → /verify → /finish"

    if [[ -z "$meta_file" ]]; then
        context+="\n\nNo active feature. Use /create-feature to start a structured workflow, or work freely—skills are available on demand."
    fi

    echo "$context"
}

# Main
main() {
    local context
    context=$(build_context)

    local escaped_context
    escaped_context=$(escape_json "$context")

    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "${escaped_context}"
  }
}
EOF

    exit 0
}

main
```

**Step 5: Make script executable**

Run: `chmod +x hooks/session-start.sh`

**Step 6: Test the script directly**

Run: `./hooks/session-start.sh | python3 -c "import json,sys; d=json.load(sys.stdin); print('Valid JSON'); print(d['hookSpecificOutput']['additionalContext'])"`

Expected:
```
Valid JSON
Available commands: /create-feature | /brainstorm → /specify → /design → /create-tasks → /implement → /verify → /finish

No active feature. Use /create-feature to start a structured workflow, or work freely—skills are available on demand.
```

**Step 7: Commit**

```bash
git add hooks/session-start.sh
git commit -m "feat(hooks): implement SessionStart hook for workflow context"
```

---

## Task 3: Implement pre-commit-guard.sh hook

**Files:**
- Create: `hooks/pre-commit-guard.sh`

**Step 1: Create the script with shebang, strict mode, and JSON helper**

Create `hooks/pre-commit-guard.sh`:

```bash
#!/usr/bin/env bash
# PreToolUse hook: guard git commits

set -euo pipefail

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
```

**Step 2: Add command parsing logic**

Append to `hooks/pre-commit-guard.sh`:

```bash
# Read tool input from stdin
read_tool_input() {
    local input
    input=$(cat)

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
```

**Step 3: Add branch detection and test file detection**

Append to `hooks/pre-commit-guard.sh`:

```bash
# Get current git branch
get_current_branch() {
    git rev-parse --abbrev-ref HEAD 2>/dev/null || echo ""
}

# Check if on protected branch
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
        if find . -name "$pattern" -type f 2>/dev/null | head -1 | grep -q .; then
            return 0
        fi
    done

    return 1
}
```

**Step 4: Add output functions**

Append to `hooks/pre-commit-guard.sh`:

```bash
# Output: allow the action
output_allow() {
    local context="${1:-}"
    if [[ -n "$context" ]]; then
        local escaped
        escaped=$(escape_json "$context")
        cat <<EOF
{
  "decision": "allow",
  "additionalContext": "${escaped}"
}
EOF
    else
        cat <<EOF
{
  "decision": "allow"
}
EOF
    fi
}

# Output: block the action
output_block() {
    local reason="$1"
    local escaped
    escaped=$(escape_json "$reason")
    cat <<EOF
{
  "decision": "block",
  "reason": "${escaped}"
}
EOF
}
```

**Step 5: Add main logic**

Append to `hooks/pre-commit-guard.sh`:

```bash
# Main
main() {
    local command
    command=$(read_tool_input)

    # Only process git commit commands
    if [[ ! "$command" =~ git[[:space:]]+commit ]]; then
        output_allow
        exit 0
    fi

    # Check branch
    local branch
    branch=$(get_current_branch)

    if is_protected_branch "$branch"; then
        output_block "Direct commits to ${branch} branch are blocked. Create a feature branch first:
  git checkout -b feature/your-feature-name

Or use /create-feature for the full workflow."
        exit 2
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
```

**Step 6: Make script executable**

Run: `chmod +x hooks/pre-commit-guard.sh`

**Step 7: Test with non-commit command**

Run: `echo '{"tool_name": "Bash", "tool_input": {"command": "ls -la"}}' | ./hooks/pre-commit-guard.sh`

Expected:
```json
{
  "decision": "allow"
}
```

**Step 8: Test with commit on main (simulate)**

Run:
```bash
# Save current branch
CURRENT=$(git rev-parse --abbrev-ref HEAD)
# Test (only if not on main - otherwise this would pass)
echo '{"tool_name": "Bash", "tool_input": {"command": "git commit -m test"}}' | ./hooks/pre-commit-guard.sh
echo "Exit code: $?"
```

Expected output depends on current branch:
- If on main: `"decision": "block"` and exit code 2
- If on feature branch: `"decision": "allow"` and exit code 0

**Step 9: Commit**

```bash
git add hooks/pre-commit-guard.sh
git commit -m "feat(hooks): implement PreToolUse commit guard"
```

---

## Task 4: Update validate.sh to include hooks validation

**Files:**
- Modify: `validate.sh`

**Step 1: Add hooks validation section**

After the "Validating Commands..." section (around line 215), add:

```bash
# Validate hooks
echo "Validating Hooks..."
if [ -f "hooks/hooks.json" ]; then
    log_info "Checking hooks/hooks.json"
    if python3 -c "import json; json.load(open('hooks/hooks.json'))" 2>/dev/null; then
        log_success "hooks.json valid JSON"
    else
        log_error "hooks/hooks.json: Invalid JSON syntax"
    fi

    # Check shell scripts are executable
    for hook_script in hooks/*.sh; do
        if [ -f "$hook_script" ]; then
            log_info "Checking $hook_script"
            if [ -x "$hook_script" ]; then
                log_success "$hook_script is executable"
            else
                log_error "$hook_script is not executable (run: chmod +x $hook_script)"
            fi
        fi
    done
else
    log_info "No hooks/hooks.json found"
fi
echo ""
```

**Step 2: Run validate.sh to verify**

Run: `./validate.sh`

Expected: Should show "Validating Hooks..." section with green checkmarks for hooks.json and both .sh files.

**Step 3: Commit**

```bash
git add validate.sh
git commit -m "feat(validate): add hooks validation"
```

---

## Task 5: Test hooks end-to-end

**Files:**
- None (testing only)

**Step 1: Validate entire setup**

Run: `./validate.sh`

Expected: All green checkmarks, 0 errors.

**Step 2: Test session-start.sh produces valid output**

Run: `./hooks/session-start.sh | python3 -m json.tool`

Expected: Pretty-printed valid JSON with `hookSpecificOutput.additionalContext`.

**Step 3: Test pre-commit-guard.sh allows non-commit commands**

Run: `echo '{"tool_name": "Bash", "tool_input": {"command": "npm test"}}' | ./hooks/pre-commit-guard.sh | python3 -m json.tool`

Expected: `{"decision": "allow"}`

**Step 4: Test pre-commit-guard.sh with git commit**

Run: `echo '{"tool_name": "Bash", "tool_input": {"command": "git commit -m \"test\""}}' | ./hooks/pre-commit-guard.sh | python3 -m json.tool`

Expected: Depends on current branch - allow with reminder (feature branch) or block (main).

**Step 5: Final commit with all tests passing**

```bash
git add -A
git status
# If any unstaged changes exist, commit them
git commit -m "feat(hooks): complete hooks implementation" --allow-empty
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Create hooks directory and registry | `hooks/hooks.json` |
| 2 | Implement SessionStart hook | `hooks/session-start.sh` |
| 3 | Implement PreToolUse commit guard | `hooks/pre-commit-guard.sh` |
| 4 | Update validate.sh for hooks | `validate.sh` |
| 5 | End-to-end testing | (none) |

After completing all tasks, restart Claude Code to activate the hooks.
