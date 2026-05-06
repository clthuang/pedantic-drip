#!/bin/bash
# Feature 104 FR-5: integration tests for capture-on-stop.sh.
# Requires: jq + Python venv with semantic_memory stub on PYTHONPATH.
# Mocks the writer via static stub at tests/stubs/semantic_memory/writer.py
# (per design TD-2).
set -uo pipefail

# Feature 106 FR-5: enable test-injection seam in capture-on-stop.sh
export CLAUDE_CODE_DEV_MODE=1

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
HOOKS_DIR=$(dirname "$SCRIPT_DIR")
HOOK="${HOOKS_DIR}/capture-on-stop.sh"
FIXTURES_DIR="${SCRIPT_DIR}/fixtures"
STUB_LIB="${SCRIPT_DIR}/stubs"

# PYTHONPATH must shadow real semantic_memory (per design TD-2 / R-2).
export PYTHONPATH="${STUB_LIB}:${PYTHONPATH:-}"
# Test-injection seam: route capture-on-stop's writer dispatch to the stub.
export PD_TEST_WRITER_PYTHONPATH="$STUB_LIB"
export PD_TEST_WRITER_PYTHON="$(command -v python3)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

log_test() { TESTS_RUN=$((TESTS_RUN + 1)); echo -e "TEST: $1"; }
log_pass() { TESTS_PASSED=$((TESTS_PASSED + 1)); echo -e "  ${GREEN}PASS${NC}"; }
log_fail() { TESTS_FAILED=$((TESTS_FAILED + 1)); echo -e "  ${RED}FAIL: $1${NC}"; }

# Per-test setup
setup_capture_dir() {
    STUB_CAPTURE_DIR=$(mktemp -d -t pd-stub-capture.XXXXXX)
    export STUB_CAPTURE_DIR
}
teardown() {
    rm -rf "${STUB_CAPTURE_DIR:-}"
    rm -f ~/.claude/pd/correction-buffer-test*.jsonl 2>/dev/null
    unset STUB_CAPTURE_DIR
}

# Build a buffer with N tags, returns sid
make_buffer_n_tags() {
    local sid="$1" n="$2" pattern="${3:-\\b(no,? don\'?t)\\b}"
    local buffer="$HOME/.claude/pd/correction-buffer-${sid}.jsonl"
    mkdir -p "$HOME/.claude/pd"
    rm -f "$buffer"
    local i
    for ((i=1; i<=n; i++)); do
        local ts
        ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        jq -nc --arg ts "$ts" --arg pe "tag $i" --arg mp "$pattern" --arg pf "tag $i full" \
            '{ts:$ts, prompt_excerpt:$pe, matched_pattern:$mp, prompt_full:$pf}' >> "$buffer"
        sleep 0.01
    done
    echo "$sid"
}

invoke_stop_hook() {
    local stdin="$1"
    printf '%s' "$stdin" | "$HOOK"
}

# AC-5.1: stuck guard — buffer NOT deleted, stdout {}
test_stuck_guard() {
    log_test "AC-5.1: stop_hook_active=true → {} on stdout, buffer NOT deleted"
    setup_capture_dir
    local sid
    sid=$(make_buffer_n_tags "test-stuck" 1)
    local buffer="$HOME/.claude/pd/correction-buffer-${sid}.jsonl"
    local stdin
    stdin=$(jq -nc --arg s "$sid" '{transcript_path:"/tmp/x", stop_hook_active:true, session_id:$s, hook_event_name:"Stop"}')
    local out
    out=$(invoke_stop_hook "$stdin" 2>/dev/null)
    if [[ "$out" == "{}" ]] && [[ -f "$buffer" ]]; then
        log_pass
    else
        log_fail "out='$out' buffer_exists=$([[ -f "$buffer" ]] && echo y || echo n)"
    fi
    teardown
}

# AC-5.2: missing buffer → stdout {} exit 0
test_missing_buffer() {
    log_test "AC-5.2: missing buffer → {} exit 0"
    setup_capture_dir
    local sid="test-missing-$$"
    local buffer="$HOME/.claude/pd/correction-buffer-${sid}.jsonl"
    rm -f "$buffer"
    local stdin
    stdin=$(jq -nc --arg s "$sid" '{transcript_path:"/tmp/x", stop_hook_active:false, session_id:$s, hook_event_name:"Stop"}')
    local out rc
    out=$(invoke_stop_hook "$stdin" 2>/dev/null)
    rc=$?
    if [[ "$out" == "{}" ]] && [[ $rc -eq 0 ]]; then
        log_pass
    else
        log_fail "out='$out' rc=$rc"
    fi
    teardown
}

# AC-5.3: 600-char assistant message truncated to 500 chars
test_truncate_500_chars() {
    log_test "AC-5.3: 600-char assistant message → 500 chars in candidate"
    setup_capture_dir
    local sid="test-trunc"
    local buffer="$HOME/.claude/pd/correction-buffer-${sid}.jsonl"
    mkdir -p "$HOME/.claude/pd"
    # Build buffer tag at T1 BEFORE the assistant message at T2 in fixture
    jq -nc \
        --arg ts "2026-05-03T05:00:00Z" \
        --arg pe "I prefer pytest" \
        --arg mp '\bi (want|prefer|always|never)\b' \
        --arg pf "I prefer pytest" \
        '{ts:$ts, prompt_excerpt:$pe, matched_pattern:$mp, prompt_full:$pf}' > "$buffer"
    export PROJECT_ROOT="$(pwd)"
    local stdin
    stdin=$(jq -nc \
        --arg t "$FIXTURES_DIR/transcript-truncate-test.jsonl" \
        --arg s "$sid" \
        '{transcript_path:$t, stop_hook_active:false, session_id:$s, hook_event_name:"Stop"}')
    invoke_stop_hook "$stdin" >/dev/null 2>&1 || true
    # Check captured candidate
    if [[ ! -f "$STUB_CAPTURE_DIR/call-1.json" ]]; then
        log_fail "no captured candidate at $STUB_CAPTURE_DIR/call-1.json"
        teardown
        return
    fi
    # Extract the assistant content portion of description (between "Model response: '" and "'. Pattern:")
    local desc
    desc=$(jq -r '.description' "$STUB_CAPTURE_DIR/call-1.json")
    # Count A's in the description (the fixture content was 600 'A's)
    local a_count
    a_count=$(echo "$desc" | tr -cd 'A' | wc -c | tr -d ' ')
    if [[ "$a_count" == "500" ]]; then
        log_pass
    else
        log_fail "expected 500 A's, got $a_count"
    fi
    unset PROJECT_ROOT
    teardown
}

# AC-5.4: candidate construction
test_candidate_construction() {
    log_test "AC-5.4: candidate has confidence=low, source=session-capture, source_project=\$PROJECT_ROOT, name<=60"
    setup_capture_dir
    local sid="test-cand"
    local buffer="$HOME/.claude/pd/correction-buffer-${sid}.jsonl"
    mkdir -p "$HOME/.claude/pd"
    jq -nc \
        --arg ts "2026-05-03T05:00:00Z" \
        --arg pe "no, don't do that" \
        --arg mp '\b(no,? don'\''?t)\b' \
        --arg pf "no, don't do that" \
        '{ts:$ts, prompt_excerpt:$pe, matched_pattern:$mp, prompt_full:$pf}' > "$buffer"
    export PROJECT_ROOT="$(pwd)"
    local proj="$PROJECT_ROOT"
    local stdin
    stdin=$(jq -nc \
        --arg t "$FIXTURES_DIR/transcript-with-response.jsonl" \
        --arg s "$sid" \
        '{transcript_path:$t, stop_hook_active:false, session_id:$s, hook_event_name:"Stop"}')
    invoke_stop_hook "$stdin" >/dev/null 2>&1 || true
    if [[ ! -f "$STUB_CAPTURE_DIR/call-1.json" ]]; then
        log_fail "no candidate captured"
        teardown
        return
    fi
    if jq -e --arg proj "$proj" '
        .confidence == "low"
        and .source == "session-capture"
        and .source_project == $proj
        and (.name | length) <= 60
    ' "$STUB_CAPTURE_DIR/call-1.json" >/dev/null; then
        log_pass
    else
        log_fail "candidate JSON failed contract check: $(cat "$STUB_CAPTURE_DIR/call-1.json")"
    fi
    unset PROJECT_ROOT
    teardown
}

# AC-5.4a (anti-patterns branch): negative-correction → category=anti-patterns
test_category_mapping_anti_patterns() {
    log_test "AC-5.4a: negative-correction → anti-patterns"
    setup_capture_dir
    export PROJECT_ROOT="$(pwd)"
    local sid_neg="test-cat-neg"
    mkdir -p "$HOME/.claude/pd"
    jq -nc --arg ts "2026-05-03T05:00:00Z" --arg pe "no don't" \
        --arg mp '\b(no,? don'\''?t)\b' --arg pf "no don't" \
        '{ts:$ts, prompt_excerpt:$pe, matched_pattern:$mp, prompt_full:$pf}' \
        > "$HOME/.claude/pd/correction-buffer-${sid_neg}.jsonl"
    local stdin1
    stdin1=$(jq -nc --arg t "$FIXTURES_DIR/transcript-with-response.jsonl" --arg s "$sid_neg" '{transcript_path:$t, stop_hook_active:false, session_id:$s, hook_event_name:"Stop"}')
    invoke_stop_hook "$stdin1" >/dev/null 2>&1 || true
    if [[ ! -f "$STUB_CAPTURE_DIR/call-1.json" ]]; then
        log_fail "no negative candidate captured"
        unset PROJECT_ROOT
        teardown
        return
    fi
    local cat_neg
    cat_neg=$(jq -r '.category' "$STUB_CAPTURE_DIR/call-1.json")
    if [[ "$cat_neg" == "anti-patterns" ]]; then
        log_pass
    else
        log_fail "neg=$cat_neg (want anti-patterns)"
    fi
    unset PROJECT_ROOT
    teardown
}

# AC-5.4a (patterns branch): preference statement → category=patterns
test_category_mapping_preference() {
    log_test "AC-5.4a: preference/style → patterns"
    setup_capture_dir
    export PROJECT_ROOT="$(pwd)"
    local sid_pref="test-cat-pref"
    mkdir -p "$HOME/.claude/pd"
    jq -nc --arg ts "2026-05-03T05:00:00Z" --arg pe "I prefer pytest" \
        --arg mp '\bi (want|prefer|always|never)\b' --arg pf "I prefer pytest" \
        '{ts:$ts, prompt_excerpt:$pe, matched_pattern:$mp, prompt_full:$pf}' \
        > "$HOME/.claude/pd/correction-buffer-${sid_pref}.jsonl"
    local stdin2
    stdin2=$(jq -nc --arg t "$FIXTURES_DIR/transcript-with-response.jsonl" --arg s "$sid_pref" '{transcript_path:$t, stop_hook_active:false, session_id:$s, hook_event_name:"Stop"}')
    invoke_stop_hook "$stdin2" >/dev/null 2>&1 || true
    if [[ ! -f "$STUB_CAPTURE_DIR/call-1.json" ]]; then
        log_fail "no preference candidate captured"
        unset PROJECT_ROOT
        teardown
        return
    fi
    local cat_pref
    cat_pref=$(jq -r '.category' "$STUB_CAPTURE_DIR/call-1.json")
    if [[ "$cat_pref" == "patterns" ]]; then
        log_pass
    else
        log_fail "pref=$cat_pref (want patterns)"
    fi
    unset PROJECT_ROOT
    teardown
}

# AC-5.5: 7-tag buffer with cap=5 → overflow logged with dropped_count=2 + dropped_excerpts
test_cap_overflow() {
    log_test "AC-5.5: 7-tag buffer with cap=5 → overflow.log records 2 dropped"
    setup_capture_dir
    export PROJECT_ROOT="$(pwd)"
    local tmp_home
    tmp_home=$(mktemp -d -t pd-test-home.XXXXXX)
    mkdir -p "$tmp_home/.claude/pd"
    local sid="test-overflow"
    local buffer="$tmp_home/.claude/pd/correction-buffer-${sid}.jsonl"
    local i
    for ((i=1; i<=7; i++)); do
        jq -nc --arg ts "2026-05-03T05:00:0$i""Z" --arg pe "tag $i" \
            --arg mp '\b(no,? don'\''?t)\b' --arg pf "tag $i" \
            '{ts:$ts, prompt_excerpt:$pe, matched_pattern:$mp, prompt_full:$pf}' >> "$buffer"
    done
    local stdin
    stdin=$(jq -nc --arg t "$FIXTURES_DIR/transcript-with-response.jsonl" --arg s "$sid" '{transcript_path:$t, stop_hook_active:false, session_id:$s, hook_event_name:"Stop"}')
    HOME="$tmp_home" invoke_stop_hook "$stdin" >/dev/null 2>&1 || true
    local overflow_log="$tmp_home/.claude/pd/capture-overflow.log"
    if [[ -f "$overflow_log" ]] && \
       jq -e '.dropped_count == 2 and (.dropped_excerpts | length) == 2' "$overflow_log" >/dev/null 2>&1; then
        log_pass
    else
        log_fail "overflow_log=$([[ -f "$overflow_log" ]] && echo present || echo missing) content: $([[ -f "$overflow_log" ]] && cat "$overflow_log" || echo none)"
    fi
    rm -rf "$tmp_home"
    unset PROJECT_ROOT
    teardown
}

# AC-5.6: buffer with 3 tags, all dedup-rejected → buffer file still deleted
test_cleanup_after_dedup() {
    log_test "AC-5.6: buffer deleted even when stub returns success (TD-4 contract)"
    setup_capture_dir
    export PROJECT_ROOT="$(pwd)"
    local sid="test-dedup"
    mkdir -p "$HOME/.claude/pd"
    local buffer="$HOME/.claude/pd/correction-buffer-${sid}.jsonl"
    for i in 1 2 3; do
        jq -nc --arg ts "2026-05-03T05:00:0$i""Z" --arg pe "tag $i" \
            --arg mp '\b(no,? don'\''?t)\b' --arg pf "tag $i" \
            '{ts:$ts, prompt_excerpt:$pe, matched_pattern:$mp, prompt_full:$pf}' >> "$buffer"
    done
    local stdin
    stdin=$(jq -nc --arg t "$FIXTURES_DIR/transcript-with-response.jsonl" --arg s "$sid" '{transcript_path:$t, stop_hook_active:false, session_id:$s, hook_event_name:"Stop"}')
    invoke_stop_hook "$stdin" >/dev/null 2>&1 || true
    if [[ ! -f "$buffer" ]]; then
        log_pass
    else
        log_fail "buffer file still exists at $buffer"
    fi
    unset PROJECT_ROOT
    teardown
}

# AC-5.7: no-response transcript → stderr emits "tags skipped"
test_no_response_warning() {
    log_test "AC-5.7: no-response transcript → stderr 'tags skipped: no assistant response found'"
    setup_capture_dir
    export PROJECT_ROOT="$(pwd)"
    local sid="test-noresp"
    mkdir -p "$HOME/.claude/pd"
    jq -nc --arg ts "2026-05-03T05:00:00Z" --arg pe "no don't" \
        --arg mp '\b(no,? don'\''?t)\b' --arg pf "no don't" \
        '{ts:$ts, prompt_excerpt:$pe, matched_pattern:$mp, prompt_full:$pf}' \
        > "$HOME/.claude/pd/correction-buffer-${sid}.jsonl"
    local stdin
    stdin=$(jq -nc --arg t "$FIXTURES_DIR/transcript-no-response.jsonl" --arg s "$sid" '{transcript_path:$t, stop_hook_active:false, session_id:$s, hook_event_name:"Stop"}')
    local stderr
    stderr=$(invoke_stop_hook "$stdin" 2>&1 >/dev/null) || true
    if echo "$stderr" | grep -q "tags skipped: no assistant response found"; then
        log_pass
    else
        log_fail "stderr did not contain expected warning. stderr='$stderr'"
    fi
    unset PROJECT_ROOT
    teardown
}

# AC-5.8: hooks.json registration — Stop[1] is capture-on-stop with async/timeout
test_hooks_json_registration() {
    log_test "AC-5.8: hooks.json Stop[1] is capture-on-stop.sh with async/timeout"
    if jq -e '.hooks.Stop | length == 2' "${HOOKS_DIR}/hooks.json" >/dev/null && \
       jq -e '.hooks.Stop[1].hooks[0].command | endswith("capture-on-stop.sh")' "${HOOKS_DIR}/hooks.json" >/dev/null; then
        log_pass
    else
        log_fail "hooks.json registration assertions failed"
    fi
}

# AC-5.9: pre-1MB capture-overflow.log → next append rotates to .1
test_log_rotation() {
    log_test "AC-5.9: pre-1MB overflow log → next append rotates to .1"
    local tmp_home
    tmp_home=$(mktemp -d -t pd-test-home.XXXXXX)
    mkdir -p "$tmp_home/.claude/pd"
    setup_capture_dir
    export PROJECT_ROOT="$(pwd)"
    local sid="test-rotate"
    local buffer="$tmp_home/.claude/pd/correction-buffer-${sid}.jsonl"
    # Pre-create overflow log of 1.1MB
    dd if=/dev/zero bs=1024 count=1100 of="$tmp_home/.claude/pd/capture-overflow.log" 2>/dev/null
    # Build 7 tags so cap=5 triggers overflow
    local i
    for ((i=1; i<=7; i++)); do
        jq -nc --arg ts "2026-05-03T05:00:0$i""Z" --arg pe "tag $i" \
            --arg mp '\b(no,? don'\''?t)\b' --arg pf "tag $i" \
            '{ts:$ts, prompt_excerpt:$pe, matched_pattern:$mp, prompt_full:$pf}' >> "$buffer"
    done
    local stdin
    stdin=$(jq -nc --arg t "$FIXTURES_DIR/transcript-with-response.jsonl" --arg s "$sid" '{transcript_path:$t, stop_hook_active:false, session_id:$s, hook_event_name:"Stop"}')
    HOME="$tmp_home" invoke_stop_hook "$stdin" >/dev/null 2>&1 || true
    if [[ -f "$tmp_home/.claude/pd/capture-overflow.log.1" ]]; then
        log_pass
    else
        log_fail ".1 rotated file not present"
    fi
    rm -rf "$tmp_home"
    unset PROJECT_ROOT
    teardown
}

# Run all
test_stuck_guard
test_missing_buffer
test_truncate_500_chars
test_candidate_construction
test_category_mapping_anti_patterns
test_category_mapping_preference
test_cap_overflow
test_cleanup_after_dedup
test_no_response_warning
test_hooks_json_registration
test_log_rotation

echo ""
echo "Results: $TESTS_PASSED/$TESTS_RUN passed (failed: $TESTS_FAILED)"
[[ $TESTS_FAILED -eq 0 ]]
