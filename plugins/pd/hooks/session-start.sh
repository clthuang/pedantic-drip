#!/usr/bin/env bash
# SessionStart hook: inject workflow context and surface active feature

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap
PROJECT_ROOT="$(detect_project_root)"

# Resolve artifacts_root from config (default: docs)
resolve_artifacts_root() {
    local config_file="${PROJECT_ROOT}/.claude/pd.local.md"
    read_local_md_field "$config_file" "artifacts_root" "docs"
}

# Resolve base branch: explicit config > git symbolic-ref > main
resolve_base_branch() {
    local config_file="${PROJECT_ROOT}/.claude/pd.local.md"
    local configured
    configured=$(read_local_md_field "$config_file" "base_branch" "auto")

    if [[ "$configured" != "auto" && -n "$configured" ]]; then
        echo "$configured"
        return
    fi

    # Auto-detect from remote HEAD
    local remote_head
    remote_head=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||') || true
    if [[ -n "$remote_head" ]]; then
        echo "$remote_head"
        return
    fi

    # Fallback
    echo "main"
}

# Find active feature (most recently modified .meta.json with status=active)
find_active_feature() {
    local artifacts_root
    artifacts_root=$(resolve_artifacts_root)
    local features_dir="${PROJECT_ROOT}/${artifacts_root}/features"

    if [[ ! -d "$features_dir" ]]; then
        return 1
    fi

    # Find .meta.json files and check for active status
    # Use portable find + python for cross-platform compatibility (macOS + Linux)
    local latest_meta
    latest_meta=$(python3 -c "
import os
import json
import sys

features_dir = '$features_dir'
active_features = []

for root, dirs, files in os.walk(features_dir):
    if '.meta.json' in files:
        meta_path = os.path.join(root, '.meta.json')
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            # Only consider features with explicit active status
            # Note: planned features are excluded here — only active features are surfaced
            status = meta.get('status')
            if status == 'active':
                mtime = os.path.getmtime(meta_path)
                active_features.append((mtime, meta_path))
        except:
            pass

if active_features:
    # Sort by modification time, most recent first
    active_features.sort(reverse=True)
    print(active_features[0][1])
" 2>/dev/null)

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
with open('$meta_file') as f:
    meta = json.load(f)
    print(meta.get('id', 'unknown'))
    print(meta.get('slug', meta.get('name', 'unknown')))
    print(meta.get('mode', 'Standard'))
    print(meta.get('branch', ''))
    print(meta.get('project_id', ''))
" 2>/dev/null
}

# Detect current phase from existing artifacts
detect_phase() {
    local feature_dir="$1"

    if [[ -f "${feature_dir}/tasks.md" ]]; then
        echo "implementing"
    elif [[ -f "${feature_dir}/plan.md" ]]; then
        echo "creating-tasks"
    elif [[ -f "${feature_dir}/design.md" ]]; then
        echo "creating-plan"
    elif [[ -f "${feature_dir}/spec.md" ]]; then
        echo "designing"
    elif [[ -f "${feature_dir}/brainstorm.md" ]]; then
        echo "specifying"
    else
        echo "brainstorming"
    fi
}

# Get next command suggestion based on current phase
get_next_command() {
    local phase="$1"

    case "$phase" in
        "brainstorming") echo "/brainstorm" ;;
        "specifying") echo "/specify" ;;
        "designing") echo "/design" ;;
        "creating-plan") echo "/create-plan" ;;
        "creating-tasks") echo "/create-tasks" ;;
        "implementing") echo "/implement" ;;
        *) echo "/finish-feature" ;;
    esac
}

# Check if current branch matches expected feature branch
check_branch_mismatch() {
    local expected_branch="$1"

    # Skip check if no branch defined
    if [[ -z "$expected_branch" ]]; then
        return 1
    fi

    # Get current branch
    local current_branch
    current_branch=$(git branch --show-current 2>/dev/null) || return 1

    # Compare branches
    if [[ "$current_branch" != "$expected_branch" ]]; then
        return 0  # Mismatch
    fi

    return 1  # Match
}

# Check MCP bootstrap error log for recent failures.
# Reads ~/.claude/pd/mcp-bootstrap-errors.log for entries < 10 minutes old.
# Returns warning text via stdout, or empty string.
# Truncates entries > 1 hour from the log file on every invocation.
# Wrapped for error resilience — must never crash session-start.
check_mcp_health() {
    (
        set +e
        local log_file="$HOME/.claude/pd/mcp-bootstrap-errors.log"
        if [[ ! -f "$log_file" ]]; then
            return 0
        fi

        local current_epoch
        current_epoch=$(date +%s 2>/dev/null) || return 0

        local recent_errors=""
        local keep_lines=""
        local one_hour=3600
        local ten_min=600

        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            # Extract timestamp from JSONL
            local ts
            ts=$(echo "$line" | sed 's/.*"timestamp":"\([^"]*\)".*/\1/')
            [[ -z "$ts" ]] && continue

            # Parse timestamp to epoch (timestamps are UTC ISO-8601)
            local entry_epoch=""
            # BSD date (macOS) — TZ=UTC ensures input is treated as UTC
            entry_epoch=$(TZ=UTC date -jf '%Y-%m-%dT%H:%M:%SZ' "$ts" +%s 2>/dev/null) || true
            # Python fallback
            if [[ -z "$entry_epoch" ]]; then
                entry_epoch=$(python3 -c "import calendar,time,sys; print(calendar.timegm(time.strptime(sys.argv[1],'%Y-%m-%dT%H:%M:%SZ')))" "$ts" 2>/dev/null) || true
            fi
            [[ -z "$entry_epoch" ]] && continue

            local age=$((current_epoch - entry_epoch))

            # Keep entries < 1 hour for the truncated file
            if [[ "$age" -lt "$one_hour" ]]; then
                if [[ -n "$keep_lines" ]]; then
                    keep_lines="${keep_lines}
${line}"
                else
                    keep_lines="$line"
                fi
            fi

            # Collect entries < 10 minutes for warning
            if [[ "$age" -lt "$ten_min" ]]; then
                local msg
                msg=$(echo "$line" | sed 's/.*"message":"\([^"]*\)".*/\1/')
                if [[ -n "$msg" ]]; then
                    if [[ -n "$recent_errors" ]]; then
                        recent_errors="${recent_errors}; ${msg}"
                    else
                        recent_errors="$msg"
                    fi
                fi
            fi
        done < "$log_file"

        # Truncate: write kept entries to temp file, atomic mv
        local tmp_file="$HOME/.claude/pd/.mcp-errors-tmp.$$"
        if [[ -n "$keep_lines" ]]; then
            echo "$keep_lines" > "$tmp_file" 2>/dev/null && mv "$tmp_file" "$log_file" 2>/dev/null || rm -f "$tmp_file" 2>/dev/null
        else
            rm -f "$log_file" 2>/dev/null
        fi

        # Output warning if recent errors found
        if [[ -n "$recent_errors" ]]; then
            printf "WARNING: MCP servers failed to start. Workflow tools (transition_phase, store_memory, etc.) are unavailable.\nError: %s. Run: bash \"%s/scripts/setup.sh\"" "$recent_errors" "$PLUGIN_ROOT"
        fi
    ) 2>/dev/null || echo ""
}

# Check if claude-md-management plugin is available
check_claude_md_plugin() {
    local cache_dir="$HOME/.claude/plugins/cache"
    # Check if any marketplace has claude-md-management cached
    if compgen -G "${cache_dir}/*/claude-md-management" > /dev/null 2>&1; then
        return 0  # Found
    fi
    return 1  # Not found
}

# Build context message
build_context() {
    local context=""
    local meta_file
    local cwd
    cwd=$(pwd)

    meta_file=$(find_active_feature) || true

    if [[ -n "$meta_file" ]]; then
        local feature_dir
        feature_dir=$(dirname "$meta_file")

        # Parse metadata
        local meta_output
        meta_output=$(parse_feature_meta "$meta_file")

        if [[ -n "$meta_output" ]]; then
            local id name mode branch phase next_cmd current_branch
            id=$(echo "$meta_output" | sed -n '1p')
            name=$(echo "$meta_output" | sed -n '2p')
            mode=$(echo "$meta_output" | sed -n '3p')
            branch=$(echo "$meta_output" | sed -n '4p')
            project_id=$(echo "$meta_output" | sed -n '5p')
            phase=$(detect_phase "$feature_dir")
            next_cmd=$(get_next_command "$phase")

            context="You're working on feature ${id}-${name} (${mode} mode).\n"
            context+="Current phase: ${phase}\n"

            # Show project affiliation if present
            if [[ -n "$project_id" ]]; then
                local project_slug
                local artifacts_root_val
                artifacts_root_val=$(resolve_artifacts_root)
                project_slug=$(python3 -c "
import os, json, glob, sys
dirs = glob.glob(os.path.join(sys.argv[1], sys.argv[3], 'projects', sys.argv[2] + '-*/'))
if dirs:
    with open(os.path.join(dirs[0], '.meta.json')) as f:
        print(json.load(f).get('slug', 'unknown'))
else:
    print('unknown')
" "$PROJECT_ROOT" "$project_id" "$artifacts_root_val" 2>/dev/null)
                context+="Project: ${project_id}-${project_slug}\n"
            fi

            # Check branch mismatch and add warning
            if [[ -n "$branch" ]]; then
                context+="Branch: ${branch}\n"
                if check_branch_mismatch "$branch"; then
                    current_branch=$(git branch --show-current 2>/dev/null || echo "unknown")
                    context+="\n⚠️  WARNING: You are not on the feature branch.\n"
                    context+="   Current branch: ${current_branch}\n"
                    context+="   Feature branch: ${branch}\n"
                    context+="   Consider: git checkout ${branch}\n"
                fi
            fi

            # Add next command suggestion
            context+="\nNext suggested command: ${next_cmd}\n"
        fi
    fi

    # Always include workflow overview
    context+="\nAvailable commands: /brainstorm → /specify → /design → /create-plan → /create-tasks → /implement → /finish-feature (/create-feature, /create-project as alternatives)"
    context+="\nTip: Use /remember <learning> to capture insights, or use the store_memory MCP tool directly."
    context+="\nMemory capture mode: $(read_local_md_field "$PROJECT_ROOT/.claude/pd.local.md" "memory_model_capture_mode" "ask-first")"
    context+="\nMemory silent capture budget: $(read_local_md_field "$PROJECT_ROOT/.claude/pd.local.md" "memory_silent_capture_budget" "5")"

    local max_agents
    max_agents=$(read_local_md_field "$PROJECT_ROOT/.claude/pd.local.md" "max_concurrent_agents" "5")
    [[ "$max_agents" =~ ^[0-9]+$ ]] || max_agents="5"
    context+="\nmax_concurrent_agents: ${max_agents}"

    context+="\npd_plugin_root: ${PLUGIN_ROOT}"

    local artifacts_root_ctx base_branch_ctx release_script_ctx
    artifacts_root_ctx=$(resolve_artifacts_root)
    context+="\npd_artifacts_root: ${artifacts_root_ctx}"
    base_branch_ctx=$(resolve_base_branch)
    context+="\npd_base_branch: ${base_branch_ctx}"
    release_script_ctx=$(read_local_md_field "$PROJECT_ROOT/.claude/pd.local.md" "release_script" "")
    if [[ -n "$release_script_ctx" ]]; then
        context+="\npd_release_script: ${release_script_ctx}"
    fi
    local doc_tiers_ctx
    doc_tiers_ctx=$(read_local_md_field "$PROJECT_ROOT/.claude/pd.local.md" "doc_tiers" "user-guide,dev-guide,technical")
    context+="\npd_doc_tiers: ${doc_tiers_ctx}"

    # Check optional dependency
    if ! check_claude_md_plugin; then
        context+="\n\nNote: claude-md-management plugin not installed. Install it from claude-plugins-official marketplace for automatic CLAUDE.md updates during /finish-feature."
    fi

    if [[ -z "$meta_file" ]]; then
        context+="\n\nNo active feature. Use /brainstorm to start exploring ideas, or /create-feature to skip brainstorming."
    fi

    echo "$context"
}

# Build memory context from knowledge bank entries
build_memory_context() {
    local config_file="${PROJECT_ROOT}/.claude/pd.local.md"
    local enabled
    enabled=$(read_local_md_field "$config_file" "memory_injection_enabled" "true")
    if [[ "$enabled" != "true" ]]; then
        return
    fi

    local limit
    limit=$(read_local_md_field "$config_file" "memory_injection_limit" "20")
    [[ "$limit" =~ ^-?[0-9]+$ ]] || limit="20"

    local semantic_enabled
    semantic_enabled=$(read_local_md_field "$config_file" "memory_semantic_enabled" "true")

    local timeout_cmd=""
    if command -v gtimeout >/dev/null 2>&1; then
        timeout_cmd="gtimeout 5"
    elif command -v timeout >/dev/null 2>&1; then
        timeout_cmd="timeout 5"
    fi

    # Resolve Python: prefer venv, fallback to system python3
    local python_cmd="python3"
    if [[ -x "${PLUGIN_ROOT}/.venv/bin/python" ]]; then
        python_cmd="${PLUGIN_ROOT}/.venv/bin/python"
    fi

    local memory_output=""
    local max_retries=3
    local attempt=0
    if [[ "$semantic_enabled" == "true" ]]; then
        # Semantic memory: embedding-based retrieval with FTS5 keyword search
        # stderr suppressed: injector.py errors must not corrupt hook JSON output
        while (( attempt < max_retries )); do
            memory_output=$(PYTHONPATH="${SCRIPT_DIR}/lib" $timeout_cmd "$python_cmd" -m semantic_memory.injector \
                --project-root "$PROJECT_ROOT" \
                --limit "$limit" \
                --global-store "$HOME/.claude/pd/memory" 2>/dev/null) && break
            memory_output=""
            (( attempt++ ))
        done
    else
        # Legacy memory: markdown-based with observation count sorting
        # stderr suppressed: memory.py errors must not corrupt hook JSON output
        while (( attempt < max_retries )); do
            memory_output=$($timeout_cmd $python_cmd "${SCRIPT_DIR}/lib/memory.py" \
                --project-root "$PROJECT_ROOT" \
                --limit "$limit" \
                --global-store "$HOME/.claude/pd/memory" 2>/dev/null) && break
            memory_output=""
            (( attempt++ ))
        done
    fi
    echo "$memory_output"
}

# Run reconciliation orchestrator: sync entity statuses, brainstorm registry, and KB
# Runs silently for side effects (DB reconciliation). Does not contribute to full_context.
run_reconciliation() {
    local python_cmd="$PLUGIN_ROOT/.venv/bin/python"
    local result
    local entity_db="${ENTITY_DB_PATH:-$HOME/.claude/pd/entities/entities.db}"
    local memory_db="${MEMORY_DB_PATH:-$HOME/.claude/pd/memory/memory.db}"
    local artifacts_root
    artifacts_root=$(resolve_artifacts_root)

    # Platform-aware timeout (macOS: gtimeout from coreutils, Linux: timeout)
    local timeout_cmd=""
    if command -v gtimeout &>/dev/null; then
        timeout_cmd="gtimeout 5"
    elif command -v timeout &>/dev/null; then
        timeout_cmd="timeout 5"
    fi

    result=$(PYTHONPATH="$SCRIPT_DIR/lib" \
        $timeout_cmd "$python_cmd" -m reconciliation_orchestrator \
        --project-root "$PROJECT_ROOT" \
        --artifacts-root "$artifacts_root" \
        --entity-db "$entity_db" \
        --memory-db "$memory_db" \
        2>/dev/null) || true

    # Timing diagnostics are in the JSON output (elapsed_ms field).
    # stderr is suppressed to prevent JSON corruption.
    # For debugging, run the orchestrator manually with --verbose flag
    # which writes to a log file instead of stderr.
}

# Main
main() {
    # Auto-provision config from template if missing (only if .claude/ already exists)
    local config_file="${PROJECT_ROOT}/.claude/pd.local.md"
    if [[ ! -f "$config_file" && -d "${PROJECT_ROOT}/.claude" ]]; then
        local template="${PLUGIN_ROOT}/templates/config.local.md"
        [[ -f "$template" ]] && cp "$template" "$config_file"
    fi

    # Reset plan-review gate state from previous session
    rm -f "${PROJECT_ROOT}/.claude/.plan-review-state" 2>/dev/null

    # python3 is required for feature detection and memory injection
    if ! command -v python3 &>/dev/null; then
        cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "WARNING: python3 not found. Memory injection and feature detection disabled. Install python3 to enable full functionality."
  }
}
EOF
        exit 0
    fi

    # Check MCP health before building context (R4: surface bootstrap failures early)
    local mcp_warning=""
    mcp_warning=$(check_mcp_health)

    # First-run detection (R5: moved to main() for early evaluation, before build_context)
    local first_run_warning=""
    if [[ ! -d "$HOME/.claude/pd/memory" ]] || [[ ! -x "${PLUGIN_ROOT}/.venv/bin/python" ]]; then
        first_run_warning="Setup required for MCP workflow tools. Run: bash \"${PLUGIN_ROOT}/scripts/setup.sh\""
    fi

    local memory_context=""
    memory_context=$(build_memory_context)

    run_reconciliation

    local context
    context=$(build_context)

    # Prepend warnings, then memory, then workflow state
    local full_context=""
    if [[ -n "$mcp_warning" ]]; then
        full_context="${mcp_warning}"
    fi
    if [[ -n "$first_run_warning" ]]; then
        if [[ -n "$full_context" ]]; then
            full_context="${full_context}\n\n${first_run_warning}"
        else
            full_context="${first_run_warning}"
        fi
    fi
    if [[ -n "$memory_context" ]]; then
        if [[ -n "$full_context" ]]; then
            full_context="${full_context}\n\n${memory_context}"
        else
            full_context="${memory_context}"
        fi
    fi
    if [[ -n "$full_context" ]]; then
        full_context="${full_context}\n\n${context}"
    else
        full_context="$context"
    fi

    local escaped_context
    escaped_context=$(escape_json "$full_context")

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
