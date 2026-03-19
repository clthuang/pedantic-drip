#!/usr/bin/env bash
# PreToolUse hook: gate ExitPlanMode behind plan-reviewer dispatch
# Uses counter-based state tracking (same pattern as yolo-stop.sh)
#
# Flow:
#   YOLO mode: ALLOW immediately, skip gate
#   attempt=1: DENY with plan-reviewer instructions
#   attempt=2: ALLOW, reset counter
#   attempt>2 (stale): reset counter, ALLOW

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap
PROJECT_ROOT="$(detect_project_root)"

# Consume stdin (required even if unused)
INPUT=$(cat)

STATE_FILE="${PROJECT_ROOT}/.claude/.plan-review-state"
PD_CONFIG="${PROJECT_ROOT}/.claude/pd.local.md"

# Check config — if plan_mode_review disabled, allow through
enabled=$(read_local_md_field "$PD_CONFIG" "plan_mode_review" "true")
if [[ "$enabled" != "true" ]]; then
    exit 0
fi

# YOLO mode: skip plan review gate — autonomous execution should not block
YOLO=$(read_local_md_field "$PD_CONFIG" "yolo_mode" "false")
if [[ "$YOLO" == "true" ]]; then
    # Reset counter to clean state and allow through
    write_hook_state "$STATE_FILE" "attempt" "0"
    exit 0
fi

# Read current attempt counter
attempt=$(read_hook_state "$STATE_FILE" "attempt" "0")
[[ "$attempt" =~ ^[0-9]+$ ]] || attempt=0

next_attempt=$((attempt + 1))

if [[ $next_attempt -eq 1 ]]; then
    # First attempt: deny and instruct to run plan-reviewer
    write_hook_state "$STATE_FILE" "attempt" "$next_attempt"

    reason="PLAN REVIEW REQUIRED: Before exiting plan mode, you must run the plan-reviewer agent. "
    reason+="Dispatch it now:\\n\\n"
    reason+="1. Read the full plan file content you wrote\\n"
    reason+="2. Use the Task tool:\\n"
    reason+="   subagent_type: pd:plan-reviewer\\n"
    reason+="   model: opus\\n"
    reason+="   prompt: |\\n"
    reason+="     Review this plan for failure modes, untested assumptions,\\n"
    reason+="     dependency accuracy, and feasibility.\\n"
    reason+="     ## Plan\\n"
    reason+="     {paste full plan file content here}\\n"
    reason+="     Return JSON: {\\\"approved\\\": bool, \\\"issues\\\": [...], \\\"summary\\\": \\\"...\\\"}\\n"
    reason+="3. If reviewer returns blocker issues: edit the plan to address them, re-review (max 3 iterations)\\n"
    reason+="4. Then call ExitPlanMode again"

    escaped=$(escape_json "$reason")
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "${escaped}"
  }
}
EOF
elif [[ $next_attempt -eq 2 ]]; then
    # Second attempt: allow through, reset counter
    write_hook_state "$STATE_FILE" "attempt" "0"
    exit 0
else
    # Stale counter (>2): reset and allow to prevent stuck state
    write_hook_state "$STATE_FILE" "attempt" "0"
    exit 0
fi
