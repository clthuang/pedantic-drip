#!/bin/bash
# Feature 102 FR-2: Stop hook — read correction buffer, join with transcript,
# emit candidate KB entries via semantic_memory.writer. Runs async (timeout 30s).
# Requires: jq, python3 (via venv).
# Output: always {} on stdout, exit 0.
set -uo pipefail

# Read stdin JSON
payload=$(cat)
transcript_path=$(printf '%s' "$payload" | jq -r '.transcript_path // ""' 2>/dev/null)
stop_hook_active=$(printf '%s' "$payload" | jq -r '.stop_hook_active // false' 2>/dev/null)
session_id=$(printf '%s' "$payload" | jq -r '.session_id // ""' 2>/dev/null)

trap 'printf "{}\n"' EXIT

# Stuck-detection guard: do not delete buffer
if [[ "$stop_hook_active" == "true" ]]; then
  exit 0
fi

[[ -z "$session_id" ]] && exit 0

buffer_dir="$HOME/.claude/pd"
buffer_file="$buffer_dir/correction-buffer-${session_id}.jsonl"
overflow_log="$buffer_dir/capture-overflow.log"

# Missing buffer → no-op
[[ ! -f "$buffer_file" ]] && exit 0

# Resolve project root + SESSION_CAP from pd.local.md
project_root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
session_cap=$(grep -E '^memory_capture_session_cap:' "$project_root/.claude/pd.local.md" 2>/dev/null | awk -F': *' '{print $2}' | tr -d ' ' | head -1)
session_cap=${session_cap:-5}

# Resolve plugin root + writer CLI invocation
plugin_root=$(ls -d ~/.claude/plugins/cache/*/pd*/* 2>/dev/null | head -1)
[[ -z "$plugin_root" ]] && plugin_root="$project_root/plugins/pd"
writer_python="$plugin_root/.venv/bin/python"
writer_pythonpath="$plugin_root/hooks/lib"
# Feature 104 test-injection seam: tests can override the writer python module
# path so capture-on-stop.sh routes to a stub instead of the real writer.
# Production behavior unchanged when these env vars are unset.
[[ -n "${PD_TEST_WRITER_PYTHONPATH:-}" ]] && writer_pythonpath="$PD_TEST_WRITER_PYTHONPATH"
[[ -n "${PD_TEST_WRITER_PYTHON:-}" ]] && writer_python="$PD_TEST_WRITER_PYTHON"

# Read buffer tags (preserve insertion order); cap at session_cap
total_tags=$(wc -l < "$buffer_file" 2>/dev/null | tr -d ' ')
total_tags=${total_tags:-0}

skipped_count=0
writer_fail_count=0
first_writer_error=""

# Process up to cap tags
processed=0
while IFS= read -r tag_line; do
  [[ -z "$tag_line" ]] && continue
  if [[ $processed -ge $session_cap ]]; then
    break
  fi

  ts=$(printf '%s' "$tag_line" | jq -r '.ts // ""')
  prompt_excerpt=$(printf '%s' "$tag_line" | jq -r '.prompt_excerpt // ""')
  matched_pattern=$(printf '%s' "$tag_line" | jq -r '.matched_pattern // ""')

  # Locate first assistant message with timestamp > ts in transcript
  model_response=""
  if [[ -f "$transcript_path" ]]; then
    model_response=$(jq -rs --arg cut "$ts" '
      [ .[] | select(.type == "assistant" and (.timestamp // "") > $cut) ]
      | .[0]
      | (.message.content // "")
      | tostring
    ' "$transcript_path" 2>/dev/null | head -c 500)
  fi

  if [[ -z "$model_response" || "$model_response" == "null" ]]; then
    skipped_count=$((skipped_count + 1))
    processed=$((processed + 1))
    continue
  fi

  # Determine category from matched_pattern (match exact regex literal, not substring).
  # Negative-correction patterns → anti-patterns; preference/style → patterns.
  category="patterns"
  case "$matched_pattern" in
    '\b(no,? don'\''?t)\b'|'\bstop( doing| that)?\b'|'\b(revert|undo) (that|this|it)\b'|"\b(wrong|that's wrong|incorrect)\b"|'\bnot (that|this|what i)\b')
      category="anti-patterns"
      ;;
  esac

  # Derive name (≤60 chars, deterministic)
  name=$(printf '%s' "$prompt_excerpt" | head -c 60 | sed 's/[[:space:]]*$//' | sed 's/[.,!?;:]*$//')

  # Construct candidate JSON
  description="User correction: '${prompt_excerpt}'. Model response: '${model_response}'. Pattern: ${matched_pattern}"

  candidate_json=$(jq -nc \
    --arg n "$name" \
    --arg d "$description" \
    --arg c "$category" \
    --arg sp "$project_root" \
    '{name: $n, description: $d, category: $c, confidence: "low", source: "session-capture", source_project: $sp}')

  # Invoke writer
  err_output=$(PYTHONPATH="$writer_pythonpath" "$writer_python" -m semantic_memory.writer \
    --action upsert \
    --entry-json "$candidate_json" 2>&1 >/dev/null) || {
    writer_fail_count=$((writer_fail_count + 1))
    [[ -z "$first_writer_error" ]] && first_writer_error="$err_output"
  }

  processed=$((processed + 1))
done < "$buffer_file"

# Overflow logging
if [[ $total_tags -gt $session_cap ]]; then
  dropped=$((total_tags - session_cap))
  ts_now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Collect dropped tags' prompt_excerpts (lines beyond session_cap)
  dropped_excerpts_json=$(tail -n "+$((session_cap + 1))" "$buffer_file" 2>/dev/null \
    | jq -cs '[.[] | .prompt_excerpt]' 2>/dev/null || echo "[]")

  # Rotate BEFORE append: if existing log already over 1MB, rotate first
  if [[ -f "$overflow_log" ]]; then
    size=$(stat -f%z "$overflow_log" 2>/dev/null || stat -c%s "$overflow_log" 2>/dev/null || echo 0)
    if [[ $size -gt 1048576 ]]; then
      mv -f "$overflow_log" "${overflow_log}.1" 2>/dev/null
    fi
  fi

  jq -nc \
    --arg ts "$ts_now" \
    --arg sid "$session_id" \
    --argjson dc "$dropped" \
    --argjson de "$dropped_excerpts_json" \
    '{ts: $ts, session_id: $sid, dropped_count: $dc, dropped_excerpts: $de}' >> "$overflow_log"
fi

# Stderr diagnostics
if [[ $skipped_count -gt 0 ]]; then
  echo "$skipped_count tags skipped: no assistant response found" >&2
fi
if [[ $writer_fail_count -gt 0 ]]; then
  echo "$writer_fail_count writer failures, first error: $first_writer_error" >&2
fi

# Always delete buffer file on success path (per TD-4)
rm -f "$buffer_file"

exit 0
