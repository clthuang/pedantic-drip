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

# Line 1: the hook input's cwd; the rest: the Bash command.
parsed=$(printf '%s' "$input" | python3 -c 'import json, sys
d = json.load(sys.stdin)
print(d.get("cwd", "")); print(d.get("tool_input", {}).get("command", ""))' 2>/dev/null) || exit 0
cwd=${parsed%%$'\n'*}
command=${parsed#*$'\n'}
[[ "$command" =~ (^|[[:space:]\;\&\|\(])git([[:space:]]+-[Cc][[:space:]]+[^[:space:]]+)*[[:space:]]+commit([[:space:]]|$) ]] || exit 0

[ -n "$cwd" ] && [ -d "$cwd" ] && cd "$cwd"
top=$(run_git_in_command_context "$command" rev-parse --show-toplevel) || exit 0
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
