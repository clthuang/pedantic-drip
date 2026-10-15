#!/usr/bin/env bash
# SessionStart hook: a short summary of the current project (plan Part B §9, §12).
# - adopted (or configured) project: active and blocked items with their ## Now lines, each roadmap's
#   next ready item and the retros owed, from pd-status; on every matcher;
# - old layout (docs/features/ without `sop: 1`): "run /pd:adopt"; on every matcher;
# - no .claude/pd.local.md: one /pd:init offer, on startup and resume only.
# Nothing outside git, and no prompt for a repository listed in ~/.claude/pd/init-declined.
set -uo pipefail
trap '' PIPE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/session-start-helpers.sh"

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

if [ -d "$top/docs/features" ] && [ "$adopted" = 0 ]; then
    [ "$declined" = 1 ] && exit 0
    text="pd: run /pd:adopt: this project still uses the old layout (docs/features/ without \`sop: 1\` in .claude/pd.local.md)."
elif [ -f "$cfg" ]; then
    # Keep pd-status's active and blocked rows, its roadmap lines and the retros owed.
    summary=$(cd "$top" && "${SCRIPT_DIR}/../scripts/pd-status" 2>/dev/null | awk '
        /^$/ {sec = ""; next}
        sec == "" {sec = $0; if (sec == "Plans" || sec == "Retros owed") print; next}
        sec == "Items" && ($1 == "active" || $1 == "blocked") {print}
        sec == "Plans" || sec == "Retros owed" {print}')
    [ -n "$summary" ] || exit 0
    text="pd: active and blocked items, next ready, retros owed (pd-status prints the rest)"$'\n'"$summary"
else
    case "$source" in startup|resume) ;; *) exit 0 ;; esac
    [ "$declined" = 1 ] && exit 0
    text="pd: this repository has no .claude/pd.local.md. Offer /pd:init through AskUserQuestion: run it now, not now, or never for this repository (never: append the line \`${key:-$top}\` to ~/.claude/pd/init-declined)."
fi
safe_emit_hook_json "$(jq -nc --arg ctx "$text" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}')"
exit 0
