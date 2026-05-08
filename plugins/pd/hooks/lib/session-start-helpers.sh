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

    # Indirect lookup of env var (bash 3.2 compat — no nameref ${!var})
    # shellcheck disable=SC2086,SC2294
    local log_path
    eval "log_path=\${$log_env_var_name:-$default_log_path}"

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
    local rc="$1"
    set +e

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
