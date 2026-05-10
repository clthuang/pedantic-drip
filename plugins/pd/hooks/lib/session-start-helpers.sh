#!/usr/bin/env bash
# Helpers for session-start.sh broken-pipe handling.
# Feature 107. See docs/dev_guides/hook-development.md and
# docs/features/107-fix-sessionstart-broken-pipe/design.md.
#
# REQUIRES caller to have set `trap '' PIPE` BEFORE invoking
# safe_emit_hook_json. Without it, the bash process is SIGPIPE-killed
# before printf's `|| true` runs (verified empirically — see
# probe-printf-sigpipe.sh and design.md "Verified Bash Behavior").

# safe_emit_hook_json(json: string)
# EPIPE-safe write of a JSON document to stdout.
# - { ...; } || true swallows non-zero exit (printf returns 1 on EPIPE).
# - 2>/dev/null suppresses 'printf: write error: Broken pipe' diagnostic.
safe_emit_hook_json() {
    local json="$1"
    { printf '%s\n' "$json" 2>/dev/null; } || true
}

# pd_log_diagnostic(env_var_name, default_log_path, basename, line, exit_code, reason)
# Generic diagnostic logger with bash-side rotation at 1 MB.
# All failure modes return 0 (recovery-of-recovery per spec FR5).
pd_log_diagnostic() {
    local log_env_var_name="$1"
    local default_log_path="$2"
    local script_basename="$3"
    local line_no="$4"
    local exit_code="$5"
    local reason="$6"

    # Indirect env-var expansion via ${!var} (bash 2.0+, available on 3.2).
    # Avoids `eval` to eliminate command-injection vector through hostile $HOME
    # (per security-reviewer iter 1).
    local log_path="${!log_env_var_name:-$default_log_path}"

    local log_dir
    log_dir="$(dirname "$log_path")"

    # Idempotent directory creation (FR5 first-run handling, AC12).
    mkdir -p "$log_dir" 2>/dev/null || return 0

    # Rotation: if file > 1 MB, keep last 500 KB (FR5b, TD3).
    # macOS BSD: `stat -f%z`; Linux GNU: `stat -c%s`. Fallback: skip rotation.
    if [[ -f "$log_path" ]]; then
        local size
        size=$(stat -f%z "$log_path" 2>/dev/null || stat -c%s "$log_path" 2>/dev/null || echo 0)
        if (( size > 1048576 )); then
            local tmp
            tmp=$(mktemp "${log_path}.XXXXXX" 2>/dev/null) || return 0
            tail -c 524288 "$log_path" > "$tmp" 2>/dev/null && mv "$tmp" "$log_path" 2>/dev/null
        fi
    fi

    # Append TSV line; recovery-of-recovery: failures swallowed.
    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "0000-00-00T00:00:00Z")
    printf '%s\t%s:%s\t%s\t%s\n' "$ts" "$script_basename" "$line_no" "$exit_code" "$reason" \
        >> "$log_path" 2>/dev/null || return 0
}

# pd_log_session_start_diagnostic(line, exit_code, reason)
# Convenience wrapper for session-start.sh.
pd_log_session_start_diagnostic() {
    pd_log_diagnostic "PD_SESSION_START_LOG" "$HOME/.claude/pd/session-start.log" \
        "session-start.sh" "$1" "$2" "$3"
}

# ensure_workspace_uuid()
# Resolve the workspace UUID for the current project root via the Python
# helper (entity_registry.project_identity.resolve_workspace_uuid). Echoes
# the canonical 36-char lowercase hyphenated UUID to stdout on success.
#
# Feature 108 FR-2 / FR-11 / NFR-1: this helper is the SOLE shell-level
# entry point for workspace UUID resolution. It MUST NOT itself perform
# tempfile manipulation or `mktemp`-based atomic writes — those live in
# Python (`_atomic_workspace_json_write`) under the same fcntl.flock the
# Python path uses for cross-process safety.
#
# Inputs:
#   $1 (optional)  Project root directory; defaults to $PWD.
#   $PLUGIN_ROOT   Set by caller (session-start.sh, meta-json-guard.sh, …).
# Output:
#   stdout         The 36-char workspace UUID (no trailing newline beyond
#                  what `print()` emits).
#
# Returns 0 on success, non-zero otherwise. On failure, the caller is
# responsible for downgrading to fail-soft behaviour (e.g., warn-only via
# safe_emit_hook_json) — this helper never abort()s the parent shell.
ensure_workspace_uuid() {
    local project_root="${1:-$PWD}"
    local plugin_root="${PLUGIN_ROOT:-}"
    local venv_python=""

    if [[ -n "$plugin_root" ]] && [[ -x "$plugin_root/.venv/bin/python" ]]; then
        venv_python="$plugin_root/.venv/bin/python"
    elif [[ -x "$HOME/.claude/plugins/cache/anthropic/pedantic-drip/main/.venv/bin/python" ]]; then
        # Plugin cache fallback (multi-version layout).
        venv_python="$HOME/.claude/plugins/cache/anthropic/pedantic-drip/main/.venv/bin/python"
    else
        # Last-resort: glob the cache layout.
        local cached
        cached=$(ls -d "$HOME"/.claude/plugins/cache/*/pd*/*/.venv/bin/python 2>/dev/null | head -1) || true
        if [[ -n "$cached" ]] && [[ -x "$cached" ]]; then
            venv_python="$cached"
        fi
    fi

    if [[ -z "$venv_python" ]]; then
        return 1
    fi

    local hooks_lib="$plugin_root/hooks/lib"
    if [[ ! -d "$hooks_lib" ]]; then
        # Fallback: derive from venv path.
        hooks_lib="${venv_python%/.venv/bin/python}/hooks/lib"
    fi

    # Suppress Python tracebacks/warnings (CLAUDE.md "Hook subprocess safety").
    PYTHONPATH="$hooks_lib" "$venv_python" -c "
import os, sys
sys.path.insert(0, os.environ.get('PYTHONPATH', ''))
from entity_registry.project_identity import resolve_workspace_uuid
print(resolve_workspace_uuid(os.environ.get('PD_WORKSPACE_PROJECT_ROOT') or None))
" 2>/dev/null
    return $?
}

# install_session_start_traps()
# Sets up ERR + EXIT traps. The EXIT trap is the recovery path
# (always fires); the ERR trap logs diagnostics. Both `set +e`
# defensively to prevent set -e from aborting the trap body.
install_session_start_traps() {
    trap '__pd_err_handler ${LINENO} $?' ERR
    trap '__pd_exit_handler $?' EXIT
}

__pd_err_handler() {
    local line_no="$1"
    local rc="$2"
    set +e
    pd_log_session_start_diagnostic "$line_no" "$rc" "ERR trap fired"
    # ERR trap fires under set -e; the script then exits at the failing
    # site after this function returns. The EXIT trap runs next and
    # handles fallback emission. We do not call `exit` explicitly here
    # so the EXIT trap observes the original failure rc via $?.
}

__pd_exit_handler() {
    set +e
    local rc="$1"

    if (( rc != 0 )); then
        # Main failed; emit fallback JSON. Happy path already emitted via
        # main's safe_emit_hook_json call, so we only emit on failure
        # path — no double emission, no need for a flag.
        { printf '{}\n' 2>/dev/null; } || true
        pd_log_session_start_diagnostic "${BASH_LINENO[0]:-0}" "$rc" "EXIT non-zero"
    fi

    # CRITICAL: exit 0 regardless of upstream rc. AC1/FR1-3 depend on this.
    exit 0
}
