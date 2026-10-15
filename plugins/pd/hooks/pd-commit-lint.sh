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

# The directory a `git commit` in the command runs in, or nothing when the command doesn't commit.
# Shell words, not a regex: quoted prose isn't a command, and `git -C dir` / `--no-pager` / `cd dir &&` count.
dir=$(printf '%s' "$input" | python3 -c 'import json, os, re, shlex, sys
d = json.load(sys.stdin)
here, cmd = d.get("cwd") or ".", d.get("tool_input", {}).get("command", "")
try:
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    words = list(lex)
except ValueError:
    sys.exit(0)
seps, takes_arg = {";", "&&", "||", "|", "&", "(", ")"}, {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
start = True
for i, w in enumerate(words):
    if w in seps:
        start = True
        continue
    if not start:
        continue
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):  # an env assignment before the command
        continue
    start = False
    if w == "cd" and i + 1 < len(words) and words[i + 1] not in seps:
        here = os.path.join(here, os.path.expanduser(words[i + 1]))
    elif os.path.basename(w) == "git":
        j, at = i + 1, here
        while j < len(words) and words[j].startswith("-"):
            if words[j] == "-C" and j + 1 < len(words):
                at = os.path.join(at, os.path.expanduser(words[j + 1]))
            j += 2 if words[j] in takes_arg else 1
        if j < len(words) and words[j] == "commit":
            print(at)
            break' 2>/dev/null) || exit 0
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
