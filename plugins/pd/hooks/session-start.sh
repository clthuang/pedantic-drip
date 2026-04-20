#!/usr/bin/env bash
# SessionStart hook: inject workflow context and surface active feature

set -euo pipefail

# Ignore SIGPIPE: during /clear or /compact, CC may close stdout before the
# hook finishes writing JSON. Without this, cat <<EOF gets SIGPIPE (exit 141),
# ERR trap's echo also gets SIGPIPE (stdout closed), exit 0 never runs, and
# CC reports "Failed with non-blocking status code: No stderr output".
trap '' PIPE

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
    # FR-1.1: single-quoted Python source + positional args (no bash var interpolation).
    local latest_meta
    latest_meta=$(python3 -c '
import os
import json
import sys

features_dir = sys.argv[1]
active_features = []

for root, dirs, files in os.walk(features_dir):
    if ".meta.json" in files:
        meta_path = os.path.join(root, ".meta.json")
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            # Only consider features with explicit active status
            # Note: planned features are excluded here — only active features are surfaced
            status = meta.get("status")
            if status == "active":
                mtime = os.path.getmtime(meta_path)
                active_features.append((mtime, meta_path))
        except Exception:
            pass

if active_features:
    # Sort by modification time, most recent first
    active_features.sort(reverse=True)
    print(active_features[0][1])
' "$features_dir" 2>/dev/null)

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
    # FR-1.1: single-quoted Python source + positional arg (no bash var interpolation).
    python3 -c '
import json, sys
with open(sys.argv[1]) as f:
    meta = json.load(f)
    print(meta.get("id", "unknown"))
    print(meta.get("slug", meta.get("name", "unknown")))
    print(meta.get("mode", "Standard"))
    print(meta.get("branch", ""))
    print(meta.get("project_id", ""))
' "$meta_file" 2>/dev/null
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
        "creating-tasks") echo "/implement" ;;
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

# Ensure capture-tool-failure hook is registered in .claude/settings.local.json.
# Plugin hooks.json PostToolUse doesn't fire for built-in tools (CC limitation #6305),
# so we register via settings.local.json which does fire. Also adds PostToolUseFailure.
# Called at session start to keep the path current if the plugin cache moves.
ensure_capture_hook() {
    local settings_path="${PROJECT_ROOT}/.claude/settings.local.json"
    local hook_cmd="${SCRIPT_DIR}/capture-tool-failure.sh"

    # Fast path: check if already configured with correct path
    if [[ -f "$settings_path" ]] && grep -q "capture-tool-failure" "$settings_path" 2>/dev/null; then
        if grep -q "$hook_cmd" "$settings_path" 2>/dev/null; then
            return 0  # Already configured with correct path
        fi
    fi

    # Use python3 to safely read/create/update JSON
    # FR-1.1: single-quoted Python source (bash does not expand vars inside).
    python3 -c '
import json, os, sys
settings_path = sys.argv[1]
hook_cmd = sys.argv[2]

if os.path.exists(settings_path):
    with open(settings_path) as f:
        settings = json.load(f)
else:
    settings = {}

hooks = settings.setdefault("hooks", {})

# Ensure both PostToolUse and PostToolUseFailure have the hook
for event in ["PostToolUse", "PostToolUseFailure"]:
    entries = hooks.setdefault(event, [])
    found = False
    for entry in entries:
        for h in entry.get("hooks", []):
            if "capture-tool-failure" in h.get("command", ""):
                h["command"] = hook_cmd
                found = True
    if not found:
        entries.append({
            "matcher": "Bash|Edit|Write",
            "hooks": [{"type": "command", "command": hook_cmd, "async": True}]
        })

os.makedirs(os.path.dirname(settings_path), exist_ok=True)
with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
' "$settings_path" "$hook_cmd" 2>/dev/null || true
}

# Clean up stale/orphaned MCP server processes via PID files + lsof fallback.
# Called BEFORE doctor autofix and MCP health check to release DB locks early.
cleanup_stale_mcp_servers() {
    local pid_dir="$HOME/.claude/pd/run"
    [[ -d "$pid_dir" ]] || return 0
    for pid_file in "$pid_dir"/*.pid; do
        [[ -f "$pid_file" ]] || continue
        local pid
        pid=$(cat "$pid_file" 2>/dev/null)
        # Invalid/empty PID file — remove it
        if [[ -z "$pid" ]] || ! [[ "$pid" =~ ^[0-9]+$ ]]; then
            rm -f "$pid_file" 2>/dev/null
            continue
        fi
        # Process not running — remove stale PID file
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$pid_file" 2>/dev/null
            continue
        fi
        # Verify it's a Python process
        local comm
        comm=$(ps -o comm= -p "$pid" 2>/dev/null)
        echo "$comm" | grep -iq python 2>/dev/null || continue
        # Check if orphaned (PPID=1)
        local ppid
        ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
        [[ "$ppid" == "1" ]] || continue
        # Kill orphan: SIGTERM, wait 5s, SIGKILL if still alive
        kill -TERM "$pid" 2>/dev/null
        sleep 5
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
        rm -f "$pid_file" 2>/dev/null
    done
    # lsof fallback: find Python processes with PPID=1 holding DB files
    if command -v lsof >/dev/null 2>&1; then
        local db_files=""
        [[ -f "$HOME/.claude/pd/entities/entities.db" ]] && db_files="$HOME/.claude/pd/entities/entities.db"
        [[ -f "$HOME/.claude/pd/memory/memory.db" ]] && db_files="$db_files $HOME/.claude/pd/memory/memory.db"
        if [[ -n "$db_files" ]]; then
            lsof $db_files 2>/dev/null | awk 'NR>1{print $2}' | sort -u | while read -r lpid; do
                local lppid
                lppid=$(ps -o ppid= -p "$lpid" 2>/dev/null | tr -d ' ')
                [[ "$lppid" == "1" ]] || continue
                local lcomm
                lcomm=$(ps -o comm= -p "$lpid" 2>/dev/null)
                echo "$lcomm" | grep -iq python 2>/dev/null || continue
                kill -TERM "$lpid" 2>/dev/null
                sleep 5
                kill -0 "$lpid" 2>/dev/null && kill -9 "$lpid" 2>/dev/null
            done
        fi
    fi
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

# Build CronCreate instruction block when doctor_schedule is configured.
# Returns empty string if unset/empty or config file missing. Never fails.
#
# Security (OWASP LLM01): doctor_schedule is user-controlled config interpolated
# into an emitted CronCreate instruction. Validate against a strict cron-charset
# allowlist BEFORE emission so a crafted value cannot escape the quoted string
# and inject additional tool arguments. Allowed: digits, `* / , -`, spaces, or
# the `@hourly|daily|weekly|monthly|yearly` shortcuts. Invalid values are
# dropped with a suppressed-stderr warning (stderr is redirected to /dev/null
# by callers to avoid corrupting JSON hook output).
build_cron_schedule_context() {
    local config_file="${PROJECT_ROOT}/.claude/pd.local.md"
    [[ -f "$config_file" ]] || return 0
    local schedule
    schedule=$(read_local_md_field "$config_file" "doctor_schedule" "" 1) || schedule=""
    if [[ -z "$schedule" ]]; then
        return 0
    fi

    # Strict allowlist: digits, `*`, `/`, `,`, `-`, spaces, OR a cron shortcut.
    # This blocks quote characters, brackets, equals-signs, commas-as-arg-seps,
    # and newlines that could escape the CronCreate(schedule="...") string.
    if [[ ! "$schedule" =~ ^([0-9*/,\ -]+|@(hourly|daily|weekly|monthly|yearly))$ ]]; then
        echo "WARNING: doctor_schedule value rejected (invalid cron syntax): ${schedule}" >&2
        return 0
    fi

    # Emit natural-language instruction block for the agent to invoke CronCreate.
    # Hooks cannot call tools directly — this surfaces an instruction via additionalContext
    # (per design TD-4: graceful degradation — agent will skip if CronCreate is unavailable).
    printf "## Scheduled Doctor\n"
    printf "doctor_schedule is configured: %s\n" "$schedule"
    printf "If a scheduled doctor run is not already registered for this session, invoke the CronCreate tool:\n"
    printf "  CronCreate(schedule=\"%s\", prompt=\"/pd:doctor\", recurrence=\"recurring\")\n" "$schedule"
    printf "If CronCreate is unavailable (CLAUDE_CODE_DISABLE_CRON=1, cloud tier without local file access, or tool not present), skip silently — manual /pd:doctor invocation is unaffected.\n"
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
                # FR-1.1: single-quoted Python source + positional args (no bash expansion).
                project_slug=$(python3 -c '
import os, json, glob, sys
dirs = glob.glob(os.path.join(sys.argv[1], sys.argv[3], "projects", sys.argv[2] + "-*/"))
if dirs:
    with open(os.path.join(dirs[0], ".meta.json")) as f:
        print(json.load(f).get("slug", "unknown"))
else:
    print("unknown")
' "$PROJECT_ROOT" "$project_id" "$artifacts_root_val" 2>/dev/null)
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
    context+="\nAvailable commands: /brainstorm → /specify → /design → /create-plan → /implement → /finish-feature (/create-feature, /create-project as alternatives)"
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
    limit=$(read_local_md_field "$config_file" "memory_injection_limit" "15")
    [[ "$limit" =~ ^[0-9]+$ ]] || limit="15"

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
    if [[ "$semantic_enabled" == "false" ]]; then
        # [DEPRECATED] Legacy memory: markdown-based with observation count sorting
        # This path will be removed next release. Set memory_semantic_enabled=true (default) to use semantic injection.
        deprecation_warning="[DEPRECATED] memory_semantic_enabled=false — legacy memory.py injection will be removed next release."
        echo "$deprecation_warning"
        # stderr suppressed: memory.py errors must not corrupt hook JSON output
        while (( attempt < max_retries )); do
            memory_output=$($timeout_cmd $python_cmd "${SCRIPT_DIR}/lib/memory.py" \
                --project-root "$PROJECT_ROOT" \
                --limit "$limit" \
                --global-store "$HOME/.claude/pd/memory" 2>/dev/null) && break
            memory_output=""
            (( attempt++ ))
        done
    else
        # Semantic memory: embedding-based retrieval with FTS5 keyword search (default)
        # stderr suppressed: injector.py errors must not corrupt hook JSON output
        while (( attempt < max_retries )); do
            memory_output=$(PYTHONPATH="${SCRIPT_DIR}/lib" $timeout_cmd "$python_cmd" -m semantic_memory.injector \
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
# Returns reconciliation summary line via stdout (empty if no changes).
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

    # Extract workflow_reconcile summary and format for display (AC-6)
    # Silent when zero changes.
    # FR-1.1: single-quoted Python source + positional arg (no bash expansion).
    if [[ -n "$result" ]]; then
        python3 -c '
import json, sys
try:
    data = json.loads(sys.argv[1])
    wr = data.get("workflow_reconcile") or {}
    synced = wr.get("reconciled", 0) + wr.get("created", 0)
    kanban = wr.get("kanban_fixed", 0)
    warnings = wr.get("error", 0)
    if synced or kanban or warnings:
        print(f"Reconciled: {synced} features synced, {kanban} kanban fixed, {warnings} warnings")
except Exception:
    pass
' "$result" 2>/dev/null
    fi
}

# Run doctor auto-fix: apply safe fixes for detected issues.
# Returns single summary line via stdout (empty if healthy).
run_doctor_autofix() {
    local python_cmd="$PLUGIN_ROOT/.venv/bin/python"
    local entity_db="${ENTITY_DB_PATH:-$HOME/.claude/pd/entities/entities.db}"
    local memory_db="${MEMORY_DB_PATH:-$HOME/.claude/pd/memory/memory.db}"
    local artifacts_root
    artifacts_root=$(resolve_artifacts_root)

    # Platform-aware timeout (macOS: gtimeout from coreutils, Linux: timeout)
    local timeout_cmd=""
    if command -v gtimeout &>/dev/null; then
        timeout_cmd="gtimeout 10"
    elif command -v timeout &>/dev/null; then
        timeout_cmd="timeout 10"
    fi

    local result
    result=$(PYTHONPATH="$SCRIPT_DIR/lib" \
        $timeout_cmd "$python_cmd" -m doctor \
        --entities-db "$entity_db" \
        --memory-db "$memory_db" \
        --project-root "$PROJECT_ROOT" \
        --artifacts-root "$artifacts_root" \
        --fix 2>/dev/null) || true

    # FR-1.1: single-quoted Python source + positional arg (no bash expansion).
    if [[ -n "$result" ]]; then
        python3 -c '
import json, sys
try:
    data = json.loads(sys.argv[1])
    fixes = data.get("fixes") or {}
    fixed = fixes.get("fixed_count", 0)
    post = data.get("post_fix") or {}
    remaining = post.get("error_count", 0) + post.get("warning_count", 0)
    if fixed > 0 and remaining > 0:
        print(f"Doctor: fixed {fixed} issues ({remaining} remaining)")
    elif fixed > 0:
        print(f"Doctor: fixed {fixed} issues")
    elif remaining > 0:
        print(f"Doctor: {remaining} issues need manual attention")
except Exception:
    pass
' "$result" 2>/dev/null
    fi
}

# Run memory confidence-decay maintenance pass (feature 082).
# Invokes `python -m semantic_memory.maintenance --decay` with the project root.
# Returns the summary line via stdout (empty when disabled, dry-run with no
# changes, module missing, or DB error).  Must NEVER crash session-start.
#
# Timeout budget: 10s ceiling.  Decay touches the whole entries table when
# seeded; matches run_doctor_autofix's budget (vs run_reconciliation's 5s).
# Internal NFR-2 ceiling is 5000ms (AC-24); 10s leaves margin for subprocess
# startup + BEGIN IMMEDIATE busy-wait (per spec FR-5 writer-contention note).
run_memory_decay() {
    # FR-1.3 (#00112): PATH pinning + venv hard-fail + timeout enforcement.
    # (a) Pin PATH to a known-safe value for the duration of the subprocess
    #     invocation so `command -v gtimeout/timeout` and any implicit child
    #     lookups cannot be redirected via a tampered user $PATH.
    # (b) Hard-fail (silent skip) if the plugin venv Python is missing — do
    #     NOT fall back to $PATH-resolved python3.
    # (c) Enforce a 10s subprocess budget via gtimeout/timeout, falling back
    #     to a Python subprocess.run(..., timeout=10) wrapper on platforms
    #     where neither is present.
    #
    # Feature 089 FR-3.5 / AC-15 (#00153):
    # - Use ``trap ... RETURN`` so PATH is restored on ANY exit path (early
    #   return, SIGINT, unexpected error) — the previous ``export PATH=...``
    #   at function end ran only on the happy path.
    # - Extend pinned PATH to include ``/usr/local/bin`` (Intel Homebrew) and
    #   ``/opt/homebrew/bin`` (Apple Silicon Homebrew) so ``gtimeout`` is
    #   discoverable on macOS where ``timeout`` is not available by default.
    local PATH_OLD="$PATH"
    # shellcheck disable=SC2064  # intentional early expansion of PATH_OLD
    trap "export PATH=\"$PATH_OLD\"" RETURN
    export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

    local VENV_PYTHON="${PLUGIN_ROOT}/.venv/bin/python"
    if [[ ! -x "$VENV_PYTHON" ]]; then
        return 0  # skip silently; trap restores PATH on return
    fi

    # Platform-aware timeout (macOS: gtimeout from coreutils, Linux: timeout).
    local TIMEOUT_CMD=""
    if command -v gtimeout >/dev/null 2>&1; then
        TIMEOUT_CMD="gtimeout 10"
    elif command -v timeout >/dev/null 2>&1; then
        TIMEOUT_CMD="timeout 10"
    fi

    # stderr suppressed: maintenance.py errors must not corrupt hook JSON output.
    # `|| true` belt-and-suspenders on top of FR-8 / I-1 internal exception-swallowing.
    if [[ -n "$TIMEOUT_CMD" ]]; then
        PYTHONPATH="${SCRIPT_DIR}/lib" $TIMEOUT_CMD "$VENV_PYTHON" -m semantic_memory.maintenance \
            --decay \
            --project-root "$PROJECT_ROOT" \
            2>/dev/null || true
    else
        # Portable fallback: invoke via Python's subprocess.run with timeout=10.
        # FR-1.1: single-quoted Python source + positional args.
        PYTHONPATH="${SCRIPT_DIR}/lib" "$VENV_PYTHON" -c '
import sys, subprocess
try:
    r = subprocess.run(
        [sys.argv[1], "-m", "semantic_memory.maintenance",
         "--decay", "--project-root", sys.argv[2]],
        timeout=10, capture_output=True, text=True,
    )
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
except subprocess.TimeoutExpired:
    sys.stderr.write("[memory-decay] subprocess timeout (10s)\n")
' "$VENV_PYTHON" "$PROJECT_ROOT" 2>/dev/null || true
    fi

    # trap 'export PATH="$PATH_OLD"' RETURN handles PATH restoration on all
    # function-exit paths, including early ``return`` above and any unexpected
    # error — no explicit restore needed here.
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

    # Clean up stale/orphaned MCP servers before health checks (feature 063)
    cleanup_stale_mcp_servers

    # Ensure capture-tool-failure hook is registered in settings.local.json (feature 077)
    ensure_capture_hook

    # Check MCP health before building context (R4: surface bootstrap failures early)
    local mcp_warning=""
    mcp_warning=$(check_mcp_health)

    # First-run detection (R5: moved to main() for early evaluation, before build_context)
    local first_run_warning=""
    if [[ ! -d "$HOME/.claude/pd/memory" ]] || [[ ! -x "${PLUGIN_ROOT}/.venv/bin/python" ]]; then
        first_run_warning="Setup required for MCP workflow tools. Run: bash \"${PLUGIN_ROOT}/scripts/setup.sh\""
    fi

    local cron_schedule_context=""
    cron_schedule_context=$(build_cron_schedule_context) || cron_schedule_context=""

    # Feature 082: decay confidence BEFORE build_memory_context so memory
    # injection uses post-decay confidence values (per spec TD-5 / FR-4).
    local decay_summary=""
    decay_summary=$(run_memory_decay)

    local memory_context=""
    memory_context=$(build_memory_context)

    local recon_summary=""
    recon_summary=$(run_reconciliation)

    local doctor_summary=""
    doctor_summary=$(run_doctor_autofix)

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
    # AC-6: Surface reconciliation summary (silent when zero changes)
    if [[ -n "$recon_summary" ]]; then
        if [[ -n "$full_context" ]]; then
            full_context="${full_context}\n\n${recon_summary}"
        else
            full_context="${recon_summary}"
        fi
    fi
    # Doctor auto-fix summary (silent when healthy)
    if [[ -n "$doctor_summary" ]]; then
        if [[ -n "$full_context" ]]; then
            full_context="${full_context}\n\n${doctor_summary}"
        else
            full_context="${doctor_summary}"
        fi
    fi
    # Feature 082: confidence-decay summary (silent when disabled / no changes)
    if [[ -n "$decay_summary" ]]; then
        if [[ -n "$full_context" ]]; then
            full_context="${full_context}\n\n${decay_summary}"
        else
            full_context="${decay_summary}"
        fi
    fi
    # Scheduled doctor CronCreate instruction (silent when doctor_schedule unset)
    if [[ -n "$cron_schedule_context" ]]; then
        if [[ -n "$full_context" ]]; then
            full_context="${full_context}\n\n${cron_schedule_context}"
        else
            full_context="${cron_schedule_context}"
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
