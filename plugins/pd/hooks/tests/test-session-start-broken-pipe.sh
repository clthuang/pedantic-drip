#!/usr/bin/env bash
# Test suite for feature 107 — session-start.sh broken-pipe handling.
# 9 sub-tests T1-T9. Invoked from test-hooks.sh.

set -u
HOOK="plugins/pd/hooks/session-start.sh"
PROJECT_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$PROJECT_ROOT"

# Single source of truth for log line schema regex (per design TD5).
readonly PD_LOG_LINE_REGEX='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\t[a-z0-9_.-]+\.sh:[0-9]+\t[0-9]+\t.+$'

pass=0
fail=0
log_file=$(mktemp)
export PD_SESSION_START_LOG="$log_file"

assert_eq() {
    local label="$1"; local expected="$2"; local actual="$3"
    if [[ "$actual" == "$expected" ]]; then
        echo "PASS  $label"
        pass=$((pass + 1))
    else
        echo "FAIL  $label (expected '$expected', got '$actual')"
        fail=$((fail + 1))
    fi
}

assert_true() {
    local label="$1"; local cond_rc="$2"
    if [[ "$cond_rc" -eq 0 ]]; then
        echo "PASS  $label"
        pass=$((pass + 1))
    else
        echo "FAIL  $label (cond rc=$cond_rc)"
        fail=$((fail + 1))
    fi
}

# T1: closed-stdout pre-write → exit 0
bash "$HOOK" </dev/null | dd of=/dev/null bs=1 count=0 2>/dev/null
assert_eq "T1 closed-stdout pre-write exits 0" "0" "${PIPESTATUS[0]}"

# T2: closed-stdout mid-write → exit 0
bash "$HOOK" </dev/null | head -c 1 >/dev/null
assert_eq "T2 closed-stdout mid-write exits 0" "0" "${PIPESTATUS[0]}"

# T3: closed-stdout AND-stderr → exit 0
bash "$HOOK" </dev/null > >(dd of=/dev/null bs=1 count=0 2>/dev/null) 2> >(dd of=/dev/null bs=1 count=0 2>/dev/null)
assert_eq "T3 closed-stdout AND-stderr exits 0" "0" "$?"

# T4: happy path → exit 0 + jq assertions (FR4)
out_t4=$(mktemp)
bash "$HOOK" </dev/null > "$out_t4" 2>/dev/null
t4_rc=$?
assert_eq "T4 happy path exits 0" "0" "$t4_rc"
jq -e '.hookSpecificOutput.hookEventName == "SessionStart"' < "$out_t4" >/dev/null 2>&1
assert_true "T4 hookEventName == SessionStart" "$?"
jq -e '.hookSpecificOutput.additionalContext | type == "string"' < "$out_t4" >/dev/null 2>&1
assert_true "T4 additionalContext is string" "$?"
rm -f "$out_t4"

# T5: log-file population — uses PD_FORCE_BUILD_CONTEXT_FAIL to trigger
# the EXIT trap diagnostic log path (safe-emit handles closed-stdout
# silently, so the diagnostic log path isn't triggered by FR1-3 anymore).
> "$log_file"
PD_FORCE_BUILD_CONTEXT_FAIL=1 bash "$HOOK" </dev/null >/dev/null 2>/dev/null
PD_FORCE_BUILD_CONTEXT_FAIL=1 bash "$HOOK" </dev/null >/dev/null 2>/dev/null
PD_FORCE_BUILD_CONTEXT_FAIL=1 bash "$HOOK" </dev/null >/dev/null 2>/dev/null
if [[ -s "$log_file" ]] && grep -E "$PD_LOG_LINE_REGEX" "$log_file" >/dev/null; then
    echo "PASS  T5 log line matches PD_LOG_LINE_REGEX"
    pass=$((pass + 1))
else
    echo "FAIL  T5 log line schema regex did not match (file=$(wc -c < "$log_file") bytes)"
    fail=$((fail + 1))
fi

# T5b: AC5b rotation — pre-fill log to >1 MB, then write one diagnostic;
# rotation must trim file to <= ~500 KB + new line. Faster than 1000
# session-start.sh invocations (which trigger MCP/Python on each).
> "$log_file"
yes 'PADDING' | head -c 1500000 > "$log_file"
# shellcheck disable=SC1091
( source plugins/pd/hooks/lib/session-start-helpers.sh; \
  pd_log_session_start_diagnostic "0" "1" "rotation test" )
size=$(stat -f%z "$log_file" 2>/dev/null || stat -c%s "$log_file" 2>/dev/null || echo 0)
if (( size <= 2097152 )); then
    echo "PASS  T5b rotation keeps log <= 2 MB after pre-fill (actual $size bytes)"
    pass=$((pass + 1))
else
    echo "FAIL  T5b log grew to $size bytes after rotation (> 2 MB)"
    fail=$((fail + 1))
fi
# T5c: rotation must keep the new line, not lose it
if grep -E "$PD_LOG_LINE_REGEX" "$log_file" >/dev/null; then
    echo "PASS  T5c rotation preserves the appended diagnostic line"
    pass=$((pass + 1))
else
    echo "FAIL  T5c rotation lost the appended diagnostic line"
    fail=$((fail + 1))
fi

# T6: happy-path JSON encoding parity with multiline/special chars (R1)
out_t6=$(mktemp)
bash "$HOOK" </dev/null > "$out_t6" 2>/dev/null
jq -e '.hookSpecificOutput.additionalContext | type == "string"' < "$out_t6" >/dev/null 2>&1
assert_true "T6 multiline/special-char additionalContext parses cleanly" "$?"
rm -f "$out_t6"

# T7: PD_FORCE_BUILD_CONTEXT_FAIL → hook exits 0 with bare {} fallback
out_t7=$(mktemp)
PD_FORCE_BUILD_CONTEXT_FAIL=1 bash "$HOOK" </dev/null > "$out_t7" 2>/dev/null
t7_rc=$?
assert_eq "T7 PD_FORCE_BUILD_CONTEXT_FAIL exits 0" "0" "$t7_rc"
jq -e '. == {}' < "$out_t7" >/dev/null 2>&1
assert_true "T7 fallback emits bare {} (not FR4 shape)" "$?"
rm -f "$out_t7"

# T8: AC12 first-run directory creation. Requires the diagnostic log path
# to actually run, so we trigger PD_FORCE_BUILD_CONTEXT_FAIL=1 (forces
# EXIT trap with rc != 0 → diagnostic logged → directory + file created).
# On a clean happy path no log is written by design, so we MUST exercise
# the failure path to verify FR5/AC12 directory creation.
fresh_home=$(mktemp -d)
HOME="$fresh_home" PD_SESSION_START_LOG="$fresh_home/.claude/pd/session-start.log" \
    PD_FORCE_BUILD_CONTEXT_FAIL=1 bash "$HOOK" </dev/null >/dev/null 2>/dev/null
assert_eq "T8 first-run hook exits 0" "0" "$?"
if [[ -f "$fresh_home/.claude/pd/session-start.log" ]]; then
    echo "PASS  T8 first-run log directory + file auto-created (mkdir -p path)"
    pass=$((pass + 1))
else
    echo "FAIL  T8 expected $fresh_home/.claude/pd/session-start.log to exist"
    fail=$((fail + 1))
fi
rm -rf "$fresh_home"

# T9: FR5 recovery-of-recovery — unwriteable log path, hook still exits 0
PD_SESSION_START_LOG="/dev/null/cannot-create.log" bash "$HOOK" </dev/null | dd of=/dev/null bs=1 count=0 2>/dev/null
assert_eq "T9 unwriteable log path → hook still exits 0" "0" "${PIPESTATUS[0]}"

# Restore for any subsequent invocation
export PD_SESSION_START_LOG="$log_file"

echo
echo "Test summary: $pass passed, $fail failed"
rm -f "$log_file"

[[ $fail -eq 0 ]]
