#!/usr/bin/env bash
# PreToolUse hook (Bash): runs pd-lint --staged before a `git commit`; exit 2 blocks the commit
# and puts the lint message on stderr, which Claude sees (plan Part B §9, the pd-lint row).
# Every other Bash call leaves on the fast path below, before any subprocess runs.
set -uo pipefail
trap '' PIPE

input=$(cat)
case "$input" in *commit*) ;; *) exit 0 ;; esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap

# The directory a `git commit` in the command runs in, or nothing when the command doesn't commit (lib/commit_target.py).
target=$(printf '%s' "$input" | python3 "${SCRIPT_DIR}/lib/commit_target.py" 2>/dev/null) || exit 0
dir=${target%%$'\t'*}
[ -n "$dir" ] || exit 0
top=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -n "$top" ] || exit 0

if out=$(cd "$top" && "${SCRIPT_DIR}/../scripts/pd-lint" --staged 2>&1); then
    exit 0
else
    code=$?
fi
if [ "$code" -eq 1 ]; then
    printf 'pd-lint blocked this commit; fix the staged artifacts:\n%s\n' "$out" >&2 || true
    exit 2
fi
# A linter crash or usage error is reported but never blocks a commit.
printf 'pd-lint failed to run (exit %s):\n%s\n' "$code" "$out" >&2 || true
exit 1
