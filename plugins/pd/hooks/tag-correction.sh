#!/bin/bash
# Feature 102 FR-1: UserPromptSubmit hook — regex-tag user prompts as candidate
# corrections, append to per-session JSONL buffer for capture-on-stop.sh.
# Requires: jq (for stdin JSON parsing).
# Output: always {} on stdout, exit 0.
# Latency budget: <10ms p95 (regex + file append; no Python).
set -uo pipefail

# Read stdin JSON
payload=$(cat)
prompt=$(printf '%s' "$payload" | jq -r '.prompt // ""' 2>/dev/null)
session_id=$(printf '%s' "$payload" | jq -r '.session_id // ""' 2>/dev/null)

# Always emit {} regardless of outcome
trap 'printf "{}\n"' EXIT

[[ -z "$prompt" ]] && exit 0
[[ -z "$session_id" ]] && exit 0

# 12-pattern regex set (per design I-1 / spec FR-1)
patterns=(
  '\b(no,? don'\''?t)\b'
  '\bstop( doing| that)?\b'
  '\b(revert|undo) (that|this|it)\b'
  "\b(wrong|that's wrong|incorrect)\b"
  '\bnot (that|this|what i)\b'
  '\bi (want|prefer|always|never)\b'
  '\b(don'\''?t|do not) (use|do|add)\b'
  '\b(use|prefer) .+ instead\b'
)

matched_pattern=""
for pat in "${patterns[@]}"; do
  if printf '%s' "$prompt" | grep -qiE "$pat"; then
    matched_pattern="$pat"
    break
  fi
done

[[ -z "$matched_pattern" ]] && exit 0

# Match: append to buffer
buffer_dir="$HOME/.claude/pd"
mkdir -p "$buffer_dir" 2>/dev/null
buffer_file="$buffer_dir/correction-buffer-${session_id}.jsonl"

# ts format: ISO-8601 with Z suffix (matches CC transcript timestamp format per AC-Setup-2)
# Portable across BSD (macOS) and GNU date.
ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
prompt_excerpt=$(printf '%s' "$prompt" | head -c 200)

jq -nc \
  --arg ts "$ts" \
  --arg pe "$prompt_excerpt" \
  --arg mp "$matched_pattern" \
  --arg pf "$prompt" \
  '{ts: $ts, prompt_excerpt: $pe, matched_pattern: $mp, prompt_full: $pf}' \
  >> "$buffer_file" 2>/dev/null

exit 0
