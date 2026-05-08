#!/usr/bin/env bash
# AC1 reproduction driver for feature 107.
# Runs 4 scenarios from spec Key Definitions; asserts hook exit 0 in all.
#
# BEFORE the fix: scenarios 2 and 3 (closed-stdout pre-write, mid-write)
# produce hook exit 1 — this is the regression baseline (RCA reproduction matrix).
# AFTER the fix: all 4 must exit 0.

set -u  # not -e — we capture rcs explicitly
cd "$(git rev-parse --show-toplevel)"
HOOK="plugins/pd/hooks/session-start.sh"
LOG=$(mktemp)
export PD_SESSION_START_LOG="$LOG"

pass=0
fail=0

run_scenario() {
    local name="$1"
    local expected="$2"
    local actual_rc="$3"
    if [[ "$actual_rc" -eq "$expected" ]]; then
        echo "PASS  $name (rc=$actual_rc)"
        pass=$((pass + 1))
    else
        echo "FAIL  $name (rc=$actual_rc, expected $expected)"
        fail=$((fail + 1))
    fi
}

# Scenario 1: happy path
bash "$HOOK" </dev/null >/tmp/repro-happy.out 2>/dev/null
run_scenario "happy path" 0 $?

# Scenario 2: closed-stdout pre-write (FR1)
bash "$HOOK" </dev/null | dd of=/dev/null bs=1 count=0 2>/dev/null
run_scenario "closed-stdout pre-write (FR1)" 0 ${PIPESTATUS[0]}

# Scenario 3: closed-stdout mid-write (FR2)
bash "$HOOK" </dev/null | head -c 1 >/dev/null
run_scenario "closed-stdout mid-write (FR2)" 0 ${PIPESTATUS[0]}

# Scenario 4: closed-stdout AND-stderr (FR3)
bash "$HOOK" </dev/null \
    > >(dd of=/dev/null bs=1 count=0 2>/dev/null) \
    2> >(dd of=/dev/null bs=1 count=0 2>/dev/null)
run_scenario "closed-stdout AND-stderr (FR3)" 0 $?

echo
echo "Repro summary: $pass passed, $fail failed (PD_SESSION_START_LOG=$LOG)"
rm -f /tmp/repro-happy.out

[[ $fail -eq 0 ]]
