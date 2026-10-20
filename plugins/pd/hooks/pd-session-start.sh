#!/usr/bin/env bash
# SessionStart hook: a short summary of the current project (plan Part B §9, §12).
# - adopted (or configured) project: active and blocked items with their ## Now lines, each roadmap's
#   next ready item and the retros owed, from pd-status; on every matcher;
# - old layout (docs/features/ without `sop: 1`): "run /pd:adopt"; on every matcher;
# - no .claude/pd.local.md: one /pd:init offer, on startup and resume only.
# With a config or the offer, the {pd_artifacts_root}, {pd_base_branch} and {pd_release_script}
# values the skills and commands use.
# Nothing outside git, and no prompt for a repository listed in ~/.claude/pd/init-declined.
set -uo pipefail
trap '' PIPE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/session-start-helpers.sh"
source "${SCRIPT_DIR}/lib/common.sh"
install_session_start_traps

input=$(cat)
source=$(printf '%s' "$input" | jq -r '.source // ""' 2>/dev/null)
cwd=$(printf '%s' "$input" | jq -r '.cwd // ""' 2>/dev/null)
[ -n "$cwd" ] && [ -d "$cwd" ] && cd "$cwd"
top=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cfg="$top/.claude/pd.local.md"
# The init-declined key: the origin URL, or the path when there is none (§12).
key=$(git -C "$top" config --get remote.origin.url 2>/dev/null || true)
declined=0
grep -qxF "${key:-$top}" "$HOME/.claude/pd/init-declined" 2>/dev/null && declined=1
adopted=0
[ -f "$cfg" ] && awk 'NR==1 && !/^---$/ {exit 1} NR>1 && /^---$/ {exit 1} /^sop:[[:space:]]*"?1"?[[:space:]]*$/ {f=1; exit} END {exit !f}' "$cfg" && adopted=1

# The skills' {pd_*} values, defaults as in pd_common.py; base_branch auto: origin's HEAD, else main.
art=$(read_local_md_field "$cfg" artifacts_root docs/dev_artifacts)
base=$(read_local_md_field "$cfg" base_branch auto)
[ "$base" = auto ] && base=$(git -C "$top" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)
vars="pd_artifacts_root: ${art:-docs/dev_artifacts}"$'\n'"pd_base_branch: ${base:-main}"
release=$(read_local_md_field "$cfg" release_script "" 1)
[ -n "$release" ] && vars+=$'\n'"pd_release_script: $release"

if [ -d "$top/docs/features" ] && [ "$adopted" = 0 ]; then
    [ "$declined" = 1 ] && exit 0
    text="pd: run /pd:adopt: this project still uses the old layout (docs/features/ without \`sop: 1\` in .claude/pd.local.md)."
elif [ -f "$cfg" ]; then
    # Keep pd-status's Migrate warning, active and blocked rows, unfinished plans' roadmap lines and retros owed.
    summary=$(cd "$top" && "${SCRIPT_DIR}/../scripts/pd-status" 2>/dev/null | awk '
        /^$/ {sec = ""; next}
        sec == "" {sec = $0; keep = (sec == "Migrate" || sec == "Plans" || sec == "Retros owed"); shown = 0; next}
        sec == "Items" && ($1 == "active" || $1 == "blocked") {print; next}
        sec == "Plans" && / plan done$/ {next}
        keep {if (!shown) {print sec; shown = 1}; print}')
    text="$vars"
    [ -n "$summary" ] && text+=$'\n'"pd: active and blocked items, next ready, retros owed (pd-status prints the rest)"$'\n'"$summary"
else
    case "$source" in startup|resume) ;; *) exit 0 ;; esac
    [ "$declined" = 1 ] && exit 0
    text="pd: this repository has no .claude/pd.local.md. Offer /pd:init through AskUserQuestion: run it now, not now, or never for this repository (never: append the line \`${key:-$top}\` to ~/.claude/pd/init-declined)."$'\n'"$vars"
fi
safe_emit_hook_json "$(jq -nc --arg ctx "$text" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}')"
exit 0
