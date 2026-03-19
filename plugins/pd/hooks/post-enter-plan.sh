#!/usr/bin/env bash
# PostToolUse hook: inject plan review instructions after EnterPlanMode

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap
PROJECT_ROOT="$(detect_project_root)"

# Guard: check config
config_file="${PROJECT_ROOT}/.claude/pd.local.md"
enabled=$(read_local_md_field "$config_file" "plan_mode_review" "true")
if [[ "$enabled" != "true" ]]; then
    echo '{}'; exit 0
fi

# Build context using heredoc to avoid escaping nightmares
context=$(cat <<'CTX'
CRITICAL OVERRIDE — Phase 5 prerequisite:

### Phase 4.5: Plan Review (MANDATORY before ExitPlanMode)

You MUST complete these steps BEFORE calling ExitPlanMode. Do NOT call ExitPlanMode until the reviewer approves.

1. Read the full plan file you wrote
2. Dispatch plan-reviewer:
   ```
   Task tool:
     subagent_type: pd:plan-reviewer
     model: opus
     prompt: |
       Review this plan for failure modes, untested assumptions,
       dependency accuracy, and feasibility.
       ## Plan
       {paste full plan content}
       Return JSON: {"approved": bool, "issues": [...], "summary": "..."}
   ```
3. If blocker issues: edit plan, re-review (max 3 iterations)
4. THEN call ExitPlanMode
CTX
)

escaped=$(escape_json "$context")
cat <<EOF
{
  "hookSpecificOutput": {
    "additionalContext": "${escaped}"
  }
}
EOF
