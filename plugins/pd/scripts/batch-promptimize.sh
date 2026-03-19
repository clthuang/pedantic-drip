#!/usr/bin/env bash
# batch-promptimize — fleet-wide promptimize scoring for all component files
# Iterates all component files under plugins/pd/ and scores each against
# the 10-dimension scoring rubric using claude -p with inline scoring prompt.
# Score computation uses bash arithmetic — no LLM math.
# Exit code: 0 if all files pass threshold, 1 if any fail/error/timeout.
set -euo pipefail

# Slash commands not available in headless mode (as of 2026-02). If this
# changes, consider using /pd:promptimize directly.

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Disable colors when not on a terminal
if [[ ! -t 1 ]]; then
    RED="" GREEN="" YELLOW="" CYAN="" BOLD="" NC=""
fi

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
MAX_PARALLEL=5
THRESHOLD=80
TIMEOUT_SECS=120
RUBRIC_PATH="plugins/pd/skills/promptimize/references/scoring-rubric.md"

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Score all pd component files against the 10-dimension promptimize rubric.

Options:
  --max-parallel N   Max concurrent scoring processes (default: $MAX_PARALLEL)
  --threshold N      Minimum passing score 0-100 (default: $THRESHOLD)
  --help             Show this help message

Output:
  Per-file line with [PASS], [FAIL], [ERROR], or [TIMEOUT] tag, score, and path.
  Aggregate summary at end with total, pass/fail/error/timeout counts, and mean score.

Exit code:
  0  All files pass threshold
  1  Any file fails, errors, or times out

Examples:
  $(basename "$0")
  $(basename "$0") --max-parallel 3 --threshold 85
EOF
    exit 0
}

# ---------------------------------------------------------------------------
# Parse CLI arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --max-parallel)
            MAX_PARALLEL="${2:?--max-parallel requires a number}"
            shift 2
            ;;
        --threshold)
            THRESHOLD="${2:?--threshold requires a number}"
            shift 2
            ;;
        --help)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Run $(basename "$0") --help for usage." >&2
            exit 1
            ;;
    esac
done

# Validate numeric arguments
if ! [[ "$MAX_PARALLEL" =~ ^[0-9]+$ ]] || [[ "$MAX_PARALLEL" -lt 1 ]]; then
    echo "Error: --max-parallel must be a positive integer, got '$MAX_PARALLEL'" >&2
    exit 1
fi
if ! [[ "$THRESHOLD" =~ ^[0-9]+$ ]] || [[ "$THRESHOLD" -gt 100 ]]; then
    echo "Error: --threshold must be an integer 0-100, got '$THRESHOLD'" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Working directory guard
# ---------------------------------------------------------------------------
if [[ ! -f "$RUBRIC_PATH" ]]; then
    echo "Error: Scoring rubric not found at $RUBRIC_PATH" >&2
    echo "This script must be run from the project root (where plugins/pd/ exists)." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Discover component files
# ---------------------------------------------------------------------------
FILES=()
while IFS= read -r line; do
    FILES+=("$line")
done < <(
    # Skills: */SKILL.md
    find plugins/pd/skills -name "SKILL.md" -type f 2>/dev/null | sort
    # Agents: agents/*.md
    find plugins/pd/agents -maxdepth 1 -name "*.md" -type f 2>/dev/null | sort
    # Commands: commands/*.md
    find plugins/pd/commands -maxdepth 1 -name "*.md" -type f 2>/dev/null | sort
)

TOTAL=${#FILES[@]}
if [[ "$TOTAL" -eq 0 ]]; then
    echo "Error: No component files found under plugins/pd/" >&2
    exit 1
fi

echo -e "${BOLD}Batch Promptimize${NC}"
echo "Files discovered: $TOTAL"
echo "Max parallel: $MAX_PARALLEL"
echo "Threshold: $THRESHOLD"
echo "Timeout per file: ${TIMEOUT_SECS}s"
echo "============================================"

# ---------------------------------------------------------------------------
# Portable timeout wrapper (macOS lacks GNU timeout)
# ---------------------------------------------------------------------------
if command -v gtimeout &>/dev/null; then
    TIMEOUT_CMD="gtimeout"
elif command -v timeout &>/dev/null 2>&1 && timeout --version &>/dev/null 2>&1; then
    TIMEOUT_CMD="timeout"
else
    # Fallback: background + kill approach with temp file for stdout capture
    _portable_timeout() {
        local secs="$1"; shift
        local _pt_out
        _pt_out=$(mktemp)
        "$@" > "$_pt_out" &
        local cmd_pid=$!
        # Watcher subshell: background sleep so we can kill it on TERM
        ( _spid=0; trap 'kill $_spid 2>/dev/null; exit' TERM
          sleep "$secs" & _spid=$!; wait $_spid
          kill "$cmd_pid" 2>/dev/null ) &
        local watcher_pid=$!
        if wait "$cmd_pid" 2>/dev/null; then
            kill "$watcher_pid" 2>/dev/null
            wait "$watcher_pid" 2>/dev/null || true
            cat "$_pt_out"
            rm -f "$_pt_out"
            return 0
        else
            local ec=$?
            kill "$watcher_pid" 2>/dev/null
            wait "$watcher_pid" 2>/dev/null || true
            cat "$_pt_out"
            rm -f "$_pt_out"
            # 143 = killed by SIGTERM (timeout fired), map to 124 for compat
            [[ "$ec" -eq 143 ]] && return 124
            return "$ec"
        fi
    }
    TIMEOUT_CMD="_portable_timeout"
fi

# ---------------------------------------------------------------------------
# Allow headless claude -p to run from within a Claude Code session
# ---------------------------------------------------------------------------
unset CLAUDECODE 2>/dev/null || true

# ---------------------------------------------------------------------------
# Temp directory for results
# ---------------------------------------------------------------------------
RESULTS_DIR=$(mktemp -d)
trap 'rm -rf "$RESULTS_DIR"' EXIT

# ---------------------------------------------------------------------------
# Scoring prompt template
# ---------------------------------------------------------------------------
build_prompt() {
    local filepath="$1"
    cat <<PROMPT_EOF
Read the file at ${filepath} and the scoring rubric at ${RUBRIC_PATH}. Evaluate the file against all 10 dimensions in the rubric. For each dimension, assign Pass(3), Partial(2), or Fail(1). Return ONLY a JSON object: {"scores": {"structure_compliance": N, "token_economy": N, "description_quality": N, "persuasion_strength": N, "technique_currency": N, "prohibition_clarity": N, "example_quality": N, "progressive_disclosure": N, "context_engineering": N, "cache_friendliness": N}}
PROMPT_EOF
}

# ---------------------------------------------------------------------------
# Score a single file
# ---------------------------------------------------------------------------
score_file() {
    local filepath="$1"
    local result_file="$2"
    local prompt
    prompt=$(build_prompt "$filepath")

    local output
    local exit_code=0
    output=$($TIMEOUT_CMD "$TIMEOUT_SECS" claude -p "$prompt" \
        --allowedTools 'Read,Grep,Glob' \
        --model sonnet 2>/dev/null) || exit_code=$?

    # timeout returns 124 on timeout
    if [[ "$exit_code" -eq 124 ]]; then
        echo "TIMEOUT|${filepath}|0|exceeded ${TIMEOUT_SECS}s" > "$result_file"
        return
    fi

    # Extract JSON scores via Python — handles code fences, preamble text, etc.
    local sum
    sum=$(echo "$output" | python3 -c "
import json, re, sys
text = sys.stdin.read()
m = re.search(r'\{[^{}]*\"scores\"[^{}]*\{[^}]+\}\s*\}', text, re.DOTALL)
if not m:
    sys.exit(1)
d = json.loads(m.group())
vals = list(d['scores'].values())
if len(vals) != 10:
    sys.exit(1)
for v in vals:
    if v not in (1, 2, 3):
        sys.exit(1)
print(sum(vals))
" 2>/dev/null) || true

    if [[ -z "$sum" ]]; then
        echo "ERROR|${filepath}|0|parse error" > "$result_file"
        return
    fi

    # Score computation: integer rounding via half-divisor addend
    # Formula: percentage = (sum * 100 + 15) / 30
    local score=$(( (sum * 100 + 15) / 30 ))

    if [[ "$score" -ge "$THRESHOLD" ]]; then
        echo "PASS|${filepath}|${score}|" > "$result_file"
    else
        echo "FAIL|${filepath}|${score}|" > "$result_file"
    fi
}

# ---------------------------------------------------------------------------
# Run scoring with concurrency control
# ---------------------------------------------------------------------------
file_idx=0
pids=()

for filepath in "${FILES[@]}"; do
    result_file="${RESULTS_DIR}/result_${file_idx}"
    score_file "$filepath" "$result_file" &
    pids+=($!)
    file_idx=$((file_idx + 1))

    # Wait for a batch to complete when we hit max parallel
    if [[ "${#pids[@]}" -ge "$MAX_PARALLEL" ]]; then
        # Wait for all current pids then start next batch
        for pid in "${pids[@]+"${pids[@]}"}"; do
            wait "$pid" 2>/dev/null || true
        done
        pids=()
    fi
done

# Wait for remaining background jobs
for pid in "${pids[@]+"${pids[@]}"}"; do
    wait "$pid" 2>/dev/null || true
done

# ---------------------------------------------------------------------------
# Collect and display results
# ---------------------------------------------------------------------------
PASS_COUNT=0
FAIL_COUNT=0
ERROR_COUNT=0
TIMEOUT_COUNT=0
SCORE_SUM=0
SCORED_COUNT=0
MIN_SCORE=101
HAS_FAILURE=0

echo ""

for ((i = 0; i < TOTAL; i++)); do
    result_file="${RESULTS_DIR}/result_${i}"
    if [[ ! -f "$result_file" ]]; then
        echo -e "${RED}[ERROR]${NC} (unknown): missing result file"
        ((ERROR_COUNT++)) || true
        HAS_FAILURE=1
        continue
    fi

    IFS='|' read -r status filepath score detail < "$result_file"

    case "$status" in
        PASS)
            echo -e "${GREEN}[PASS]${NC} ${filepath}: ${score}/100"
            ((PASS_COUNT++)) || true
            ((SCORE_SUM += score)) || true
            ((SCORED_COUNT++)) || true
            if [[ "$score" -lt "$MIN_SCORE" ]]; then
                MIN_SCORE=$score
            fi
            ;;
        FAIL)
            echo -e "${RED}[FAIL]${NC} ${filepath}: ${score}/100"
            ((FAIL_COUNT++)) || true
            ((SCORE_SUM += score)) || true
            ((SCORED_COUNT++)) || true
            HAS_FAILURE=1
            if [[ "$score" -lt "$MIN_SCORE" ]]; then
                MIN_SCORE=$score
            fi
            ;;
        ERROR)
            echo -e "${YELLOW}[ERROR]${NC} ${filepath}: ${detail}"
            ((ERROR_COUNT++)) || true
            HAS_FAILURE=1
            ;;
        TIMEOUT)
            echo -e "${YELLOW}[TIMEOUT]${NC} ${filepath}: ${detail}"
            ((TIMEOUT_COUNT++)) || true
            HAS_FAILURE=1
            ;;
        *)
            echo -e "${RED}[ERROR]${NC} ${filepath}: unknown status '${status}'"
            ((ERROR_COUNT++)) || true
            HAS_FAILURE=1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Aggregate summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo -e "${BOLD}Batch Promptimize Summary${NC}"
echo "============================================"
echo "Total files: $TOTAL"
echo -e "Passed (>=${THRESHOLD}): ${GREEN}${PASS_COUNT}${NC}"
echo -e "Failed (<${THRESHOLD}): ${RED}${FAIL_COUNT}${NC}"
echo -e "Errors: ${YELLOW}${ERROR_COUNT}${NC}"
echo -e "Timeouts: ${YELLOW}${TIMEOUT_COUNT}${NC}"

if [[ "$SCORED_COUNT" -gt 0 ]]; then
    MEAN_SCORE=$(( (SCORE_SUM + SCORED_COUNT / 2) / SCORED_COUNT ))
    echo "Mean score: ${MEAN_SCORE} (excludes errors/timeouts)"
    if [[ "$MIN_SCORE" -le 100 ]]; then
        echo "Min score: ${MIN_SCORE}"
    fi
else
    echo "Mean score: N/A (no files scored)"
fi

echo "============================================"

# ---------------------------------------------------------------------------
# Exit code
# ---------------------------------------------------------------------------
if [[ "$HAS_FAILURE" -eq 1 ]]; then
    exit 1
else
    exit 0
fi
