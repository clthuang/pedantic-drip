#!/usr/bin/env bash
# test-memory-pattern.sh — Structural validation for command file memory pattern (C1)
# Validates:
#   1. "## Relevant Engineering Memory" appears INSIDE prompt: | blocks (REQ-1)
#   2. "record_influence" appears in each command file (REQ-2)
#
# Usage: bash plugins/pd/hooks/tests/test-memory-pattern.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CMD_DIR="$REPO_ROOT/plugins/pd/commands"

PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }

# --- Test 1: Memory section inside prompt blocks ---
echo "=== Test 1: Memory section inside prompt: blocks ==="

# For each command file, verify that every occurrence of "## Relevant Engineering Memory"
# appears AFTER a "prompt: |" line and BEFORE the closing ``` of that code block.
# Strategy: extract code blocks containing "prompt: |" and check they also contain the memory heading.

COMMAND_FILES=("specify.md" "design.md" "create-plan.md" "implement.md")

get_expected_count() {
    case "$1" in
        specify.md)     echo 2 ;;
        design.md)      echo 2 ;;
        create-plan.md) echo 2 ;;
        implement.md)   echo 7 ;;
        *)              echo 0 ;;
    esac
}

# design.md has 2 research agents (codebase-explorer, internet-researcher) whose
# memory sections are intentionally outside prompt blocks (excluded from this feature).
# One appears truly outside, the other is inside a code block between two Task tool calls
# but awk detects it as "inside" due to the shared code block structure.
get_max_outside() {
    case "$1" in
        design.md) echo 1 ;;  # codebase-explorer memory section before code block
        *)         echo 0 ;;
    esac
}

for file in "${COMMAND_FILES[@]}"; do
    filepath="$CMD_DIR/$file"
    if [ ! -f "$filepath" ]; then
        fail "$file: file not found"
        continue
    fi

    # Count occurrences of "## Relevant Engineering Memory" that are INSIDE a prompt: | block.
    # A memory section is "inside" if it appears between a "prompt: |" line and a "```" closing line
    # within the same code block context.
    #
    # Use awk to find prompt blocks and check for memory section within them.
    inside_count=$(awk '
        /prompt: \|/ { in_prompt = 1 }
        /^[ ]*```[ ]*$/ { if (in_prompt) in_prompt = 0 }
        /## Relevant Engineering Memory/ { if (in_prompt) count++ }
        END { print count+0 }
    ' "$filepath")

    # Count occurrences OUTSIDE prompt blocks (should be zero)
    outside_count=$(awk '
        /prompt: \|/ { in_prompt = 1 }
        /^[ ]*```[ ]*$/ { if (in_prompt) in_prompt = 0 }
        /## Relevant Engineering Memory/ { if (!in_prompt) count++ }
        END { print count+0 }
    ' "$filepath")

    expected=$(get_expected_count "$file")
    max_outside=$(get_max_outside "$file")

    if [ "$inside_count" -ge "$expected" ] && [ "$outside_count" -le "$max_outside" ]; then
        pass "$file: $inside_count memory sections inside prompt blocks, $outside_count outside (expected >= $expected inside, <= $max_outside outside)"
    else
        fail "$file: $inside_count inside (expected >= $expected), $outside_count outside (expected <= $max_outside)"
    fi
done

# --- Test 2: Influence tracking section present ---
echo ""
echo "=== Test 2: record_influence present in each command file ==="

for file in "${COMMAND_FILES[@]}"; do
    filepath="$CMD_DIR/$file"
    if [ ! -f "$filepath" ]; then
        fail "$file: file not found"
        continue
    fi

    influence_count=$(grep -c "record_influence" "$filepath" || true)

    if [ "$influence_count" -ge 1 ]; then
        pass "$file: record_influence found ($influence_count occurrences)"
    else
        fail "$file: record_influence not found"
    fi
done

# --- Test 3: "Store the returned entry names" instruction present ---
echo ""
echo "=== Test 3: Entry name storage instruction present ==="

for file in "${COMMAND_FILES[@]}"; do
    filepath="$CMD_DIR/$file"
    if [ ! -f "$filepath" ]; then
        fail "$file: file not found"
        continue
    fi

    store_count=$(grep -c "Store the returned entry names" "$filepath" || true)

    if [ "$store_count" -ge 1 ]; then
        pass "$file: entry name storage instruction found ($store_count occurrences)"
    else
        fail "$file: entry name storage instruction not found"
    fi
done

# --- Summary ---
echo ""
echo "=== Summary ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
echo "All tests passed."
