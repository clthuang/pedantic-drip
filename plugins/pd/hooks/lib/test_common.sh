#!/usr/bin/env bash
# Self-test for lib/common.sh emit_hook_json helper (feature 087).
#
# Run via: bash plugins/pd/hooks/lib/test_common.sh
# Exits 0 on all-pass, non-zero with diagnostic output on failure.

set -uo pipefail

# shellcheck source=./common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

fail=0

assert_contains() {
    local haystack="$1" needle="$2" label="$3"
    if [[ "$haystack" != *"$needle"* ]]; then
        echo "FAIL: $label — expected '$needle' in output, got: $haystack" >&2
        fail=$((fail + 1))
    fi
}

assert_not_contains() {
    local haystack="$1" needle="$2" label="$3"
    if [[ "$haystack" == *"$needle"* ]]; then
        echo "FAIL: $label — did not expect '$needle' in output, got: $haystack" >&2
        fail=$((fail + 1))
    fi
}

# Case 1: basic PreToolUse with payload.
out=$(emit_hook_json "PreToolUse" '{"permissionDecision":"allow"}')
assert_contains "$out" '"hookEventName":"PreToolUse"' "1: hookEventName present"
assert_contains "$out" '"permissionDecision":"allow"' "1: payload preserved"

# Case 2: empty payload (omitted 2nd arg).
out=$(emit_hook_json "SessionStart")
assert_contains "$out" '"hookEventName":"SessionStart"' "2: event-only"

# Case 3: PostToolUse with multi-field payload.
out=$(emit_hook_json "PostToolUse" '{"foo":"bar","baz":42}')
assert_contains "$out" '"hookEventName":"PostToolUse"' "3: event"
assert_contains "$out" '"foo":"bar"' "3: first field"
assert_contains "$out" '"baz":42' "3: second field"

# Case 4: round-trip through python json parser.
tmp=$(mktemp)
emit_hook_json "EnterPlanMode" '{"plan":"test"}' > "$tmp"
if ! python3 -c "
import json
data = json.load(open('$tmp'))
assert data['hookSpecificOutput']['hookEventName'] == 'EnterPlanMode', 'missing hookEventName'
assert data['hookSpecificOutput']['plan'] == 'test', 'missing payload'
" ; then
    echo "FAIL: 4 JSON parse failed" >&2
    fail=$((fail + 1))
fi
rm -f "$tmp"

# Case 5: error on empty event.
if emit_hook_json "" '{}' 2>/dev/null; then
    echo "FAIL: 5 should have errored on empty event" >&2
    fail=$((fail + 1))
fi

# Case 6: error on non-object payload.
if emit_hook_json "PreToolUse" 'not-json' 2>/dev/null; then
    echo "FAIL: 6 should have errored on non-object payload" >&2
    fail=$((fail + 1))
fi

# Case 7: payload containing characters that would break naive string concat.
out=$(emit_hook_json "PreToolUse" '{"msg":"hello \"world\""}')
assert_contains "$out" '"hookEventName":"PreToolUse"' "7: escaped string preserved"

if [[ $fail -eq 0 ]]; then
    echo "all common.sh emit_hook_json tests passed"
    exit 0
else
    echo "common.sh self-test: $fail failure(s)" >&2
    exit 1
fi
