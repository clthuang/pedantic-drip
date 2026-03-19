#!/usr/bin/env bash
# inject-secretary-context.sh - Inject secretary awareness at session start (aware mode only)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap

# detect_project_root returns PWD if no project markers found
PROJECT_ROOT="$(detect_project_root)"
PD_CONFIG="${PROJECT_ROOT}/.claude/pd.local.md"

# Check YOLO mode from pd config
YOLO=$(read_local_md_field "$PD_CONFIG" "yolo_mode" "false")
if [ "$YOLO" = "true" ]; then
  STATE_FILE="${PROJECT_ROOT}/.claude/.yolo-hook-state"
  YOLO_PAUSED=$(read_hook_state "$STATE_FILE" "yolo_paused" "false")

  if [ "$YOLO_PAUSED" = "true" ]; then
    YOLO_PAUSED_AT=$(read_hook_state "$STATE_FILE" "yolo_paused_at" "0")
    [[ "$YOLO_PAUSED_AT" =~ ^[0-9]+$ ]] || YOLO_PAUSED_AT="0"
    USAGE_WAIT=$(read_local_md_field "$PD_CONFIG" "yolo_usage_wait" "true")
    USAGE_COOLDOWN=$(read_local_md_field "$PD_CONFIG" "yolo_usage_cooldown" "18000")
    [[ "$USAGE_COOLDOWN" =~ ^[0-9]+$ ]] || USAGE_COOLDOWN="18000"

    if [ "$USAGE_WAIT" = "true" ]; then
      NOW=$(date +%s)
      ELAPSED=$((NOW - YOLO_PAUSED_AT))
      if [ "$ELAPSED" -ge "$USAGE_COOLDOWN" ]; then
        # Cooldown elapsed — auto-resume
        write_hook_state "$STATE_FILE" "yolo_paused" "false"
        write_hook_state "$STATE_FILE" "stop_count" "0"
        cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Secretary in YOLO MODE (resumed — usage cooldown elapsed). Use: /secretary orchestrate <desc> for full autonomous workflow, or /secretary <request> for intelligent routing."
  }
}
EOF
        exit 0
      else
        # Still cooling down
        REMAINING=$((USAGE_COOLDOWN - ELAPSED))
        REMAINING_MIN=$((REMAINING / 60))
        cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "YOLO mode paused (usage limit). Resuming in ${REMAINING_MIN}m — or /yolo on to force resume."
  }
}
EOF
        exit 0
      fi
    else
      # No auto-wait — stay paused until manual /yolo on
      cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "YOLO mode paused (usage limit). Run /yolo on to re-enable."
  }
}
EOF
      exit 0
    fi
  fi

  cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Secretary in YOLO MODE. Use: /secretary orchestrate <desc> for full autonomous workflow, or /secretary <request> for intelligent routing."
  }
}
EOF
  exit 0
fi

# Check secretary aware mode from unified config
MODE=$(read_local_md_field "$PD_CONFIG" "activation_mode" "manual")
if [ "$MODE" != "aware" ]; then
  exit 0
fi

# Output hook context
cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Secretary available for orchestrating complex requests. For vague or multi-step tasks, use: /pd:secretary <request>"
  }
}
EOF
