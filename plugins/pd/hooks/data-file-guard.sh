#!/usr/bin/env bash
# PreToolUse hook: generalized data-file guard (feature 110, FR-7).
#
# Replaces the hardcoded meta-json-guard.sh with a config-driven dispatcher.
# Reads stdin once, hands the payload to the Python dispatcher
# (data_file_guards.dispatcher), and emits the dispatcher's JSON response.
#
# Fail-open contract (AC-7.8 / R6): on ANY venv-discovery or invocation
# failure, emit `{}` (allow) and exit 0 — never block writes due to internal
# hook failures.
#
# EPIPE safety: per feature 107, install `trap '' PIPE` and route all stdout
# writes through `safe_emit_hook_json` so SIGPIPE on a closed reader never
# tears down the bash process before fallback emission runs.

set -uo pipefail

# Disable SIGPIPE so EPIPE-protected writes can fall through (feature 107).
trap '' PIPE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# common.sh provides safe_emit_hook_json fallback if session-start-helpers
# can't be sourced; we always want SOME emitter available.
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh" 2>/dev/null || true
# shellcheck source=lib/session-start-helpers.sh
source "${SCRIPT_DIR}/lib/session-start-helpers.sh" 2>/dev/null || true

# Emit-and-allow helper. Always exits 0.
emit_allow_and_exit() {
    if declare -F safe_emit_hook_json >/dev/null 2>&1; then
        safe_emit_hook_json '{}'
    else
        { printf '%s\n' '{}' 2>/dev/null; } || true
    fi
    exit 0
}

# Resolve venv python: plugin cache layout first, dev workspace fallback.
# On failure, fail-open (allow + exit 0).
resolve_venv_python() {
    # 1. Plugin cache layout (primary).
    local cached
    cached=$(ls -d "$HOME"/.claude/plugins/cache/*/pd*/*/.venv/bin/python 2>/dev/null | head -1) || true
    if [[ -n "${cached:-}" ]] && [[ -x "$cached" ]]; then
        printf '%s' "$cached"
        return 0
    fi
    # 2. Dev workspace fallback (plugins/pd/.venv/bin/python).
    local dev="${PLUGIN_ROOT}/.venv/bin/python"
    if [[ -x "$dev" ]]; then
        printf '%s' "$dev"
        return 0
    fi
    return 1
}

# Resolve PYTHONPATH for the data_file_guards package import.
resolve_pythonpath() {
    local venv_py="$1"
    local hooks_lib="${PLUGIN_ROOT}/hooks/lib"
    if [[ -d "$hooks_lib" ]]; then
        printf '%s' "$hooks_lib"
        return 0
    fi
    # Derive from venv path as a last resort.
    printf '%s' "${venv_py%/.venv/bin/python}/hooks/lib"
}

# Read all stdin once.
STDIN_JSON=""
if ! STDIN_JSON=$(cat); then
    emit_allow_and_exit
fi

VENV_PY=""
if ! VENV_PY=$(resolve_venv_python); then
    # No venv -> fail-open (AC-7.8).
    emit_allow_and_exit
fi

PYTHONPATH_VAL=$(resolve_pythonpath "$VENV_PY")

# Invoke the dispatcher. On any subprocess failure -> fail-open.
# stderr is suppressed (CLAUDE.md "Hook subprocess safety") to avoid
# corrupting the JSON stream.
DISPATCH_OUT=""
if ! DISPATCH_OUT=$(
    printf '%s' "$STDIN_JSON" \
        | PYTHONPATH="$PYTHONPATH_VAL" "$VENV_PY" -m data_file_guards.dispatcher 2>/dev/null
); then
    emit_allow_and_exit
fi

# Empty dispatcher output is a degenerate state — fail-open.
if [[ -z "$DISPATCH_OUT" ]]; then
    emit_allow_and_exit
fi

# Forward the dispatcher's JSON to stdout via the EPIPE-safe emitter.
if declare -F safe_emit_hook_json >/dev/null 2>&1; then
    safe_emit_hook_json "$DISPATCH_OUT"
else
    { printf '%s\n' "$DISPATCH_OUT" 2>/dev/null; } || true
fi
exit 0
