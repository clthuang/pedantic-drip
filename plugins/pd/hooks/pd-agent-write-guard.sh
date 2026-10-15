#!/usr/bin/env bash
# PreToolUse hook (Write|Edit): narrows two agents' writes (plan §A3, Part B §9).
# qa-executor writes only under agent_sandbox/; calvin-runner writes only the exact ledger path
# the conductor recorded as calvin_ledger in ~/.claude/pd/gate/<session id>.json.
# Exit 2 blocks the write, with the reason on stderr. Every other caller leaves on the fast path.
set -uo pipefail
trap '' PIPE

input=$(cat)
case "$input" in *qa-executor*|*calvin-runner*) ;; *) exit 0 ;; esac

# Prints a reason to refuse, or nothing to allow.
reason=$(printf '%s' "$input" | python3 -c 'import json, os, re, subprocess, sys
d = json.load(sys.stdin)
agent = (d.get("agent_type") or "").split(":")[-1]
if agent not in ("qa-executor", "calvin-runner"):
    sys.exit(0)
cwd = d.get("cwd") or os.getcwd()
top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                     capture_output=True, text=True).stdout.strip() or cwd
path = (d.get("tool_input") or {}).get("file_path") or ""
target = os.path.realpath(os.path.join(cwd, path))
if agent == "qa-executor":
    if not target.startswith(os.path.realpath(os.path.join(top, "agent_sandbox")) + os.sep):
        print(f"qa-executor may write only under agent_sandbox/, not {path}")
    sys.exit(0)
sid = d.get("session_id") or ""
state = os.path.expanduser(os.path.join("~/.claude/pd/gate", sid + ".json"))
try:
    ledger = json.load(open(state)).get("calvin_ledger") if re.fullmatch(r"[\w-]+", sid) else None
except (OSError, ValueError, AttributeError):
    ledger = None
if not ledger:
    print("calvin-runner may write only its ledger, and no calvin_ledger is recorded for this session")
elif target != os.path.realpath(os.path.join(top, ledger)):
    print(f"calvin-runner may write only its ledger {ledger}, not {path}")' 2>/dev/null)
rc=$?
if [ "$rc" -ne 0 ]; then
    # Fail closed: only the two guarded agents reach this check.
    printf 'pd-agent-write-guard: the check failed (exit %s); write refused\n' "$rc" >&2 || true
    exit 2
fi
[ -z "$reason" ] && exit 0
printf 'pd-agent-write-guard: %s\n' "$reason" >&2 || true
exit 2
