#!/usr/bin/env bash
# PostToolUse hook: inject post-approval workflow after ExitPlanMode

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

# Read artifacts_root from config
artifacts_root=$(read_local_md_field "$config_file" "artifacts_root" "docs")

# Detect active pd feature (affects section 4 guidance)
has_active=$(python3 -c "
import os, json, glob
features = glob.glob(os.path.join('$PROJECT_ROOT', '${artifacts_root}/features/*/.meta.json'))
for f in features:
    try:
        with open(f) as fh:
            if json.load(fh).get('status') == 'active':
                print('yes')
                raise SystemExit
    except SystemExit:
        raise
    except:
        pass
print('no')
" 2>/dev/null) || has_active="no"

# Inject post-approval workflow instructions
context="## Post-Approval Workflow\n\n"
context+="The user has approved your plan. Now follow this workflow:\n\n"
context+="### 1. Task Breakdown\n"
context+="Use TaskCreate for each task from the plan:\n"
context+="- Each task should be 5-15 min of work\n"
context+="- Subject format: \`{Verb} + {Object} + {Context}\` (e.g., \"Add validation to user input handler\")\n"
context+="- Include acceptance criteria in the description\n"
context+="- Set activeForm to present continuous (e.g., \"Adding validation\")\n"
context+="- Use TaskUpdate to set dependencies (addBlockedBy) between tasks\n\n"
context+="### 2. Task Review\n"
context+="After creating all tasks, dispatch the task-reviewer agent:\n"
context+="   \`\`\`\n"
context+="   Task tool:\n"
context+="     subagent_type: pd:task-reviewer\n"
context+="     model: sonnet\n"
context+="     prompt: |\n"
context+="       Review this task breakdown for quality and executability.\n"
context+="       ## Plan\n"
context+="       {plan content}\n"
context+="       ## Tasks\n"
context+="       {list all tasks with IDs, subjects, descriptions, dependencies}\n"
context+="       Return JSON: {\"approved\": bool, \"issues\": [...], \"summary\": \"...\"}\n"
context+="   \`\`\`\n"
context+="If blocker issues found: fix tasks and re-review (max 3 iterations)\n\n"
context+="### 3. Implement\n"
context+="Work through tasks in dependency order:\n"
context+="- Mark each task in_progress before starting\n"
context+="- Mark completed when done\n"
context+="- Use TaskList to find the next available task\n"
context+="- After completing each task, commit the changes:\n"
context+="  \`\`\`\n"
context+="  git add <changed files>\n"
context+="  git commit -m \"task: {task subject}\"\n"
context+="  \`\`\`\n"
context+="- Do NOT push until all tasks are done\n\n"
context+="### 4. Finish\n"
context+="When all tasks are complete:\n"
context+="1. Push all commits: \`git push\`\n"
if [[ "$has_active" == "yes" ]]; then
    context+="2. Continue with the feature workflow. Run \`/pd:show-status\` to see the current phase and next steps.\n"
else
    context+="2. Run \`/pd:wrap-up\` for code review and finishing.\n"
fi

escaped=$(escape_json "$context")
cat <<EOF
{
  "hookSpecificOutput": {
    "additionalContext": "${escaped}"
  }
}
EOF
