#!/usr/bin/env bash
# test-pd-agent-write-guard.sh — the agent write hook fed PreToolUse JSON on stdin (build-tasks T4.2).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/../pd-agent-write-guard.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
PASSED=0
FAILED=0

R="$TMP/repo"
H="$TMP/home"
mkdir -p "$R/src" "$H/.claude/pd/gate"
git -C "$R" init -q
LEDGER="agent_sandbox/2026-10-15/2026-10-15-x/calvin-cycle-1.md"
printf '{"calvin_ledger": "%s"}\n' "$LEDGER" > "$H/.claude/pd/gate/s1.json"

# expect <exit code> <label> <agent_type> <file_path> [session id] [cwd]
expect() {
  local want="$1" label="$2" code
  printf '{"session_id":"%s","agent_type":"%s","cwd":"%s","tool_name":"Write","tool_input":{"file_path":"%s","content":"x"}}' \
    "${5:-s1}" "$3" "${6:-$R}" "$4" | HOME="$H" bash "$HOOK" 2>/dev/null
  code=$?
  if [ "$code" = "$want" ]; then PASSED=$((PASSED + 1)); else FAILED=$((FAILED + 1)); echo "FAIL: $label (exit $code, want $want)"; fi
}

# QA: agent_sandbox/ only.
expect 2 "QA writing src/x.py" qa-executor "$R/src/x.py"
expect 0 "QA writing under agent_sandbox/" qa-executor "$R/agent_sandbox/2026-10-15/probe.py"
expect 0 "QA writing a relative agent_sandbox/ path" qa-executor "agent_sandbox/probe.py"
expect 2 "QA escaping agent_sandbox/ with .." qa-executor "$R/agent_sandbox/../src/x.py"
expect 2 "QA writing a sibling named agent_sandboxx" qa-executor "$R/agent_sandboxx/x.py"
expect 2 "a namespaced pd:qa-executor writing src/" pd:qa-executor "$R/src/x.py"
expect 0 "QA from a subdirectory, into the root's agent_sandbox/" qa-executor "$R/agent_sandbox/x.py" s1 "$R/src"

# A symlinked agent_sandbox doesn't move the boundary: writes through it land in src/ and are refused.
L="$TMP/linked"; mkdir -p "$L/src"; git -C "$L" init -q; ln -s src "$L/agent_sandbox"
expect 2 "QA writing through an agent_sandbox symlinked to src/" qa-executor "$L/agent_sandbox/x.py" s1 "$L"
expect 2 "calvin-runner writing its ledger through a symlinked agent_sandbox" calvin-runner "$L/$LEDGER" s1 "$L"

# calvin-runner: exactly the recorded ledger.
expect 0 "calvin-runner writing its ledger" calvin-runner "$R/$LEDGER"
expect 0 "calvin-runner writing its ledger by a relative path" calvin-runner "$LEDGER"
expect 2 "calvin-runner writing cycle 2's ledger" calvin-runner "$R/agent_sandbox/2026-10-15/2026-10-15-x/calvin-cycle-2.md"
expect 2 "calvin-runner writing another work item's ledger" calvin-runner "$R/agent_sandbox/2026-10-15/2026-10-15-y/calvin-cycle-1.md"
expect 2 "calvin-runner writing shape.md" calvin-runner "$R/docs/dev_artifacts/workitems/2026-10-15-x/shape.md"
expect 2 "calvin-runner with no gate state file" calvin-runner "$R/$LEDGER" s2
printf '{"other": 1}\n' > "$H/.claude/pd/gate/s3.json"
expect 2 "calvin-runner with no calvin_ledger recorded" calvin-runner "$R/$LEDGER" s3
err=$(printf '{"session_id":"s3","agent_type":"calvin-runner","cwd":"%s","tool_input":{"file_path":"%s"}}' "$R" "$R/$LEDGER" | HOME="$H" bash "$HOOK" 2>&1 >/dev/null)
if echo "$err" | grep -q 'no calvin_ledger is recorded'; then PASSED=$((PASSED + 1)); else FAILED=$((FAILED + 1)); echo "FAIL: no ledger names its reason: $err"; fi
expect 2 "calvin-runner with a session id that walks out of the gate dir" calvin-runner "$R/$LEDGER" "../gate/s1"

# A check that can't run refuses: malformed input naming a guarded agent.
code=0; printf '{"agent_type":"qa-executor",' | HOME="$H" bash "$HOOK" 2>/dev/null || code=$?
if [ "$code" = 2 ]; then PASSED=$((PASSED + 1)); else FAILED=$((FAILED + 1)); echo "FAIL: malformed input fails closed (exit $code)"; fi

# Everyone else passes.
expect 0 "the implementer writing src/x.py" implementer "$R/src/x.py"
expect 0 "the main session (no agent_type) writing src/x.py" "" "$R/src/x.py"
expect 0 "the implementer writing a file whose name mentions qa-executor" implementer "$R/src/qa-executor-notes.md"

echo "test-pd-agent-write-guard: $PASSED passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
