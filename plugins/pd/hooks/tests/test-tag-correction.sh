#!/bin/bash
# Feature 104 FR-4: integration tests for plugins/pd/hooks/tag-correction.sh
# Requires: jq.
# Reuses log_test/log_pass/log_fail/log_skip from test-hooks.sh:32-51.
set -uo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
HOOKS_DIR=$(dirname "$SCRIPT_DIR")
HOOK="${HOOKS_DIR}/tag-correction.sh"
FIXTURES_DIR="${SCRIPT_DIR}/fixtures"
CORPUS="${FIXTURES_DIR}/correction-corpus.jsonl"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

log_test() {
    TESTS_RUN=$((TESTS_RUN + 1))
    echo -e "TEST: $1"
}
log_pass() {
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}"
}
log_fail() {
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL: $1${NC}"
}
log_skip() {
    TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
    TESTS_RUN=$((TESTS_RUN - 1))
    echo -e "  ${YELLOW}SKIP: $1${NC}"
}

cleanup_buffers() {
    rm -f ~/.claude/pd/correction-buffer-test*.jsonl 2>/dev/null
}

invoke_hook() {
    local prompt="$1"
    local session_id="$2"
    local stdin
    stdin=$(jq -nc \
        --arg p "$prompt" \
        --arg s "$session_id" \
        '{prompt:$p, session_id:$s, hook_event_name:"UserPromptSubmit", transcript_path:"/tmp/x"}')
    printf '%s' "$stdin" | "$HOOK" 2>/dev/null
}

# AC-4.1: stdin parse — buffer file created with 1 line on match
test_stdin_parse_match() {
    log_test "AC-4.1: stdin parse → buffer file with 1 JSONL line on match"
    cleanup_buffers
    local sid="test1"
    local out
    out=$(invoke_hook "no, don't do that" "$sid")
    local buffer="$HOME/.claude/pd/correction-buffer-${sid}.jsonl"
    if [[ "$out" == "{}" ]] && [[ -f "$buffer" ]] && [[ "$(wc -l < "$buffer" | tr -d ' ')" == "1" ]]; then
        log_pass
    else
        log_fail "out='$out' buffer_exists=$([[ -f "$buffer" ]] && echo y || echo n)"
    fi
    cleanup_buffers
}

# AC-4.2: no-match — no buffer file created
test_no_match_no_buffer() {
    log_test "AC-4.2: no-match → no buffer file"
    cleanup_buffers
    local sid="testNoMatch"
    local out
    out=$(invoke_hook "hello world" "$sid")
    local buffer="$HOME/.claude/pd/correction-buffer-${sid}.jsonl"
    if [[ "$out" == "{}" ]] && [[ ! -f "$buffer" ]]; then
        log_pass
    else
        log_fail "out='$out' buffer_exists=$([[ -f "$buffer" ]] && echo y || echo n)"
    fi
    cleanup_buffers
}

# AC-4.3: JSONL schema has all 4 expected keys
test_jsonl_schema() {
    log_test "AC-4.3: buffer JSONL has {ts, prompt_excerpt, matched_pattern, prompt_full}"
    cleanup_buffers
    local sid="test3"
    invoke_hook "no, don't do that" "$sid" >/dev/null
    local buffer="$HOME/.claude/pd/correction-buffer-${sid}.jsonl"
    if jq -e '.ts and .prompt_excerpt and .matched_pattern and .prompt_full' < "$buffer" >/dev/null 2>&1; then
        log_pass
    else
        log_fail "JSONL schema check failed; line: $(cat "$buffer")"
    fi
    cleanup_buffers
}

# AC-4.4: 5 negative-correction prompts all match
test_negative_correction_5() {
    log_test "AC-4.4: 5 negative-correction prompts all match"
    cleanup_buffers
    local prompts=(
        "no, don't do that"
        "stop doing that"
        "revert that"
        "that's wrong"
        "not what I meant"
    )
    local i=0 fail=0
    for p in "${prompts[@]}"; do
        i=$((i+1))
        local sid="testNeg$i"
        invoke_hook "$p" "$sid" >/dev/null
        if [[ ! -f "$HOME/.claude/pd/correction-buffer-${sid}.jsonl" ]]; then
            fail=$((fail+1))
            echo "    FAIL on: $p"
        fi
    done
    cleanup_buffers
    if [[ $fail -eq 0 ]]; then
        log_pass
    else
        log_fail "$fail/5 negative-correction prompts did not match"
    fi
}

# AC-4.5: 4 preference + style prompts all match
test_preference_style_4() {
    log_test "AC-4.5: 4 preference/style prompts all match"
    cleanup_buffers
    local prompts=(
        "I prefer pytest"
        "don't use mocks"
        "do not add comments"
        "use jq instead of python3"
    )
    local i=0 fail=0
    for p in "${prompts[@]}"; do
        i=$((i+1))
        local sid="testPref$i"
        invoke_hook "$p" "$sid" >/dev/null
        if [[ ! -f "$HOME/.claude/pd/correction-buffer-${sid}.jsonl" ]]; then
            fail=$((fail+1))
            echo "    FAIL on: $p"
        fi
    done
    cleanup_buffers
    if [[ $fail -eq 0 ]]; then
        log_pass
    else
        log_fail "$fail/4 preference/style prompts did not match"
    fi
}

# AC-4.8: 20-sample corpus precision (≥9/10 corrections + ≤2/10 noise)
test_corpus_precision() {
    log_test "AC-4.8: 20-sample corpus → ≥9/10 corrections AND ≤2/10 noise"
    if [[ ! -f "$CORPUS" ]]; then
        log_skip "corpus fixture missing: $CORPUS"
        return
    fi
    cleanup_buffers
    local corrections_matched=0 noise_matched=0
    local line_no=0
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        line_no=$((line_no+1))
        local prompt expected
        prompt=$(echo "$line" | jq -r '.prompt')
        expected=$(echo "$line" | jq -r '.expected')
        local sid="testCorp$line_no"
        invoke_hook "$prompt" "$sid" >/dev/null
        if [[ -f "$HOME/.claude/pd/correction-buffer-${sid}.jsonl" ]]; then
            if [[ "$expected" == "correction" ]]; then
                corrections_matched=$((corrections_matched+1))
            else
                noise_matched=$((noise_matched+1))
            fi
        fi
    done < "$CORPUS"
    cleanup_buffers
    echo "    corrections_matched=$corrections_matched (target ≥9), noise_matched=$noise_matched (target ≤2)"
    if [[ $corrections_matched -ge 9 ]] && [[ $noise_matched -le 2 ]]; then
        log_pass
    else
        log_fail "AC-4.8 FAIL: corrections_matched=$corrections_matched, noise_matched=$noise_matched"
    fi
}

# AC-4.9: 20-run p95 latency <50ms (skip on CI or missing jq)
test_p95_latency() {
    log_test "AC-4.9: 20-run p95 latency <50ms (skip on CI or no jq)"
    if [[ -n "${CI:-}" ]]; then
        log_skip "running on CI runner; latency test would be flaky"
        return
    fi
    if ! command -v jq >/dev/null 2>&1; then
        log_skip "jq not available"
        return
    fi
    local prompts=(
        "no don't" "stop" "revert that" "wrong" "not that"
        "I prefer X" "don't use Y" "use Z instead" "do not add W" "I always V"
        "hello world" "what is this" "show me X" "run tests" "add a feature"
        "explain Y" "how does Z work" "what's next" "good morning" "thanks"
    )
    local times=()
    local i=0
    for p in "${prompts[@]}"; do
        i=$((i+1))
        local sid="testLat$i"
        local start_ns end_ns
        start_ns=$(date +%s%N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1e9))')
        invoke_hook "$p" "$sid" >/dev/null
        end_ns=$(date +%s%N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1e9))')
        local elapsed_ns=$((end_ns - start_ns))
        local elapsed_ms=$((elapsed_ns / 1000000))
        times+=("$elapsed_ms")
    done
    cleanup_buffers
    # p95 nearest-rank: sorted index 18 of 20 (0-indexed)
    local p95
    p95=$(printf '%s\n' "${times[@]}" | sort -n | sed -n '19p')
    echo "    p95 = ${p95}ms (target <50ms)"
    if [[ $p95 -lt 50 ]]; then
        log_pass
    else
        log_fail "p95 latency ${p95}ms exceeds 50ms threshold"
    fi
}

# Run all
mkdir -p "$HOME/.claude/pd"
test_stdin_parse_match
test_no_match_no_buffer
test_jsonl_schema
test_negative_correction_5
test_preference_style_4
test_corpus_precision
test_p95_latency

echo ""
echo "Results: $TESTS_PASSED/$TESTS_RUN passed (skipped: $TESTS_SKIPPED, failed: $TESTS_FAILED)"
[[ $TESTS_FAILED -eq 0 ]]
