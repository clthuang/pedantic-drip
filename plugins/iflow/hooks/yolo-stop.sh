#!/usr/bin/env bash
# Stop hook: Enforce YOLO mode phase transitions (Ralph Wiggum pattern)
# Control 1: Sends Claude back if reviews aren't approved yet
# Control 2: Forces phase transition when reviews pass but Claude stops

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap
PROJECT_ROOT="$(detect_project_root)"

IFLOW_CONFIG="${PROJECT_ROOT}/.claude/iflow.local.md"
STATE_FILE="${PROJECT_ROOT}/.claude/.yolo-hook-state"

# Read stdin
INPUT=$(cat)

# Check YOLO mode
YOLO=$(read_local_md_field "$IFLOW_CONFIG" "yolo_mode" "false")
if [[ "$YOLO" != "true" ]]; then
    exit 0
fi

# If YOLO is paused (usage limit hit), allow stop (don't block)
YOLO_PAUSED=$(read_hook_state "$STATE_FILE" "yolo_paused" "false")
if [[ "$YOLO_PAUSED" == "true" ]]; then
    exit 0
fi

# Usage limit check: count tokens from transcript
USAGE_LIMIT=$(read_local_md_field "$IFLOW_CONFIG" "yolo_usage_limit" "0")
[[ "$USAGE_LIMIT" =~ ^[0-9]+$ ]] || USAGE_LIMIT="0"
if [[ "$USAGE_LIMIT" -gt 0 ]]; then
    TRANSCRIPT_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('transcript_path', ''))
except:
    print('')
" 2>/dev/null)
    if [[ -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
        TOTAL_TOKENS=$(python3 -c "
import json, sys
total = 0
for line in open(sys.argv[1]):
    try:
        entry = json.loads(line)
        u = entry.get('usage', {})
        total += u.get('input_tokens', 0) + u.get('output_tokens', 0)
        total += u.get('cache_creation_input_tokens', 0) + u.get('cache_read_input_tokens', 0)
    except: pass
print(total)
" "$TRANSCRIPT_PATH" 2>/dev/null)
        [[ "$TOTAL_TOKENS" =~ ^[0-9]+$ ]] || TOTAL_TOKENS="0"
        if [[ -n "$TOTAL_TOKENS" && "$TOTAL_TOKENS" -ge "$USAGE_LIMIT" ]]; then
            write_hook_state "$STATE_FILE" "yolo_paused" "true"
            write_hook_state "$STATE_FILE" "yolo_paused_at" "$(date +%s)"
            REASON=$(escape_json "[YOLO_MODE] Usage limit reached: ${TOTAL_TOKENS}/${USAGE_LIMIT} tokens. YOLO paused.")
            cat <<EOF
{
  "decision": "block",
  "reason": "${REASON}"
}
EOF
            exit 0
        fi
    fi
fi

# Read artifacts_root from config
ARTIFACTS_ROOT=$(read_local_md_field "$IFLOW_CONFIG" "artifacts_root" "docs")

# Find active feature: scan {artifacts_root}/features/*/.meta.json for status="active"
FEATURES_DIR="${PROJECT_ROOT}/${ARTIFACTS_ROOT}/features"
if [[ ! -d "$FEATURES_DIR" ]]; then
    exit 0
fi

ACTIVE_META=""
ACTIVE_META_MTIME=0
declare -a SKIP_REASONS=()

for meta_file in "${FEATURES_DIR}"/*/.meta.json; do
    [[ -f "$meta_file" ]] || continue

    # Combined status + dependency check (Feature 038)
    # Output format: "status|dep_result" where dep_result is ELIGIBLE or SKIP:dep_ref:dep_status
    IFS='|' read -r status dep_result <<< "$(PYTHONPATH="${SCRIPT_DIR}/lib" python3 -c "
import json, sys, os
try:
    from yolo_deps import check_feature_deps
except ImportError:
    check_feature_deps = None

meta_path = sys.argv[1]
features_dir = sys.argv[2]

try:
    with open(meta_path) as f:
        d = json.load(f)
    status = d.get('status', '')
except Exception:
    status = ''

if check_feature_deps is None:
    print(f'{status}|ELIGIBLE')
    sys.exit(0)

eligible, reason = check_feature_deps(meta_path, features_dir)
if eligible:
    print(f'{status}|ELIGIBLE')
else:
    print(f'{status}|SKIP:{reason}')
" "$meta_file" "$FEATURES_DIR" 2>/dev/null)"

    if [[ "$status" == "active" ]]; then
        if [[ "$dep_result" == SKIP:* ]]; then
            # Extract feature ref from directory name
            feature_dir=$(dirname "$meta_file")
            feature_ref=$(basename "$feature_dir")
            # Parse SKIP:dep_ref:dep_status
            skip_info="${dep_result#SKIP:}"
            dep_ref="${skip_info%%:*}"
            dep_status="${skip_info#*:}"
            SKIP_REASONS+=("[YOLO_MODE] Skipped ${feature_ref}: depends on ${dep_ref} (status: ${dep_status}).")
            continue
        fi

        # Get mtime for most-recently-modified tiebreak
        mtime=$(stat -f "%m" "$meta_file" 2>/dev/null || stat -c "%Y" "$meta_file" 2>/dev/null || echo "0")
        if [[ "$mtime" -gt "$ACTIVE_META_MTIME" ]]; then
            ACTIVE_META="$meta_file"
            ACTIVE_META_MTIME="$mtime"
        fi
    fi
done

# Emit skip diagnostics to stderr for visibility (FR-2)
if [[ ${#SKIP_REASONS[@]} -gt 0 ]]; then
    for reason in "${SKIP_REASONS[@]}"; do
        echo "$reason" >&2
    done
fi

# All-skipped check: active features exist but none are eligible due to unmet deps
if [[ -z "$ACTIVE_META" && ${#SKIP_REASONS[@]} -gt 0 ]]; then
    echo "[YOLO_MODE] No eligible active features. Allowing stop." >&2
    exit 0
fi

if [[ -z "$ACTIVE_META" ]]; then
    exit 0
fi

# Read feature state
FEATURE_STATE=$(python3 -c "
import json, sys
try:
    with open('$ACTIVE_META') as f:
        d = json.load(f)
    feature_id = d.get('id', '???')
    slug = d.get('slug', 'unknown')
    status = d.get('status', '')
    last_phase = d.get('lastCompletedPhase', 'null')
    if last_phase is None:
        last_phase = 'null'
    print(f'{feature_id}|{slug}|{status}|{last_phase}')
except Exception as e:
    print('|||')
" 2>/dev/null)

IFS='|' read -r FEATURE_ID FEATURE_SLUG FEATURE_STATUS LAST_COMPLETED_PHASE <<< "$FEATURE_STATE"

if [[ -z "$FEATURE_ID" ]]; then
    exit 0
fi

# Completion check: workflow is done
if [[ "$LAST_COMPLETED_PHASE" == "finish" ]] || [[ "$FEATURE_STATUS" == "completed" ]]; then
    exit 0
fi

# Check stop_hook_active from stdin
STOP_HOOK_ACTIVE=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(str(data.get('stop_hook_active', False)).lower())
except:
    print('false')
" 2>/dev/null)

# Stuck detection: if stop_hook_active (we blocked before), check for progress
if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
    PREV_PHASE=$(read_hook_state "$STATE_FILE" "last_phase" "null")
    if [[ "$PREV_PHASE" == "$LAST_COMPLETED_PHASE" ]]; then
        # No progress since last block -- stuck, let user take over
        exit 0
    fi
fi

# Update last_phase in state
write_hook_state "$STATE_FILE" "last_phase" "$LAST_COMPLETED_PHASE"

# Max iterations check
STOP_COUNT=$(read_hook_state "$STATE_FILE" "stop_count" "0")
[[ "$STOP_COUNT" =~ ^[0-9]+$ ]] || STOP_COUNT="0"
STOP_COUNT=$((STOP_COUNT + 1))
write_hook_state "$STATE_FILE" "stop_count" "$STOP_COUNT"

MAX_BLOCKS=$(read_local_md_field "$IFLOW_CONFIG" "yolo_max_stop_blocks" "50")
[[ "$MAX_BLOCKS" =~ ^[0-9]+$ ]] || MAX_BLOCKS="50"
if [[ "$STOP_COUNT" -gt "$MAX_BLOCKS" ]]; then
    exit 0
fi

# Determine next phase
NEXT_PHASE=$(PYTHONPATH="${SCRIPT_DIR}/lib" python3 -c "
try:
    from transition_gate.constants import PHASE_SEQUENCE
    from workflow_engine.engine import WorkflowStateEngine
    from entity_registry.database import EntityDatabase
    import os

    _PHASE_VALUES = tuple(p.value for p in PHASE_SEQUENCE)
    db_path = os.environ.get('ENTITY_DB_PATH',
        os.path.expanduser('~/.claude/iflow/entities/entities.db'))
    db = EntityDatabase(db_path)
    engine = WorkflowStateEngine(db, '${PROJECT_ROOT}/${ARTIFACTS_ROOT}')
    state = engine.get_state('feature:${FEATURE_ID}-${FEATURE_SLUG}')

    if state is not None:
        last = state.last_completed_phase or ''
    else:
        last = '${LAST_COMPLETED_PHASE}'

    # 'null' (from .meta.json) and '' (from engine None->or fallback) both map to specify
    if last in ('null', ''):
        print(PHASE_SEQUENCE[1].value)  # specify — first command phase
    elif last in _PHASE_VALUES:
        idx = _PHASE_VALUES.index(last)
        print(_PHASE_VALUES[idx + 1] if idx < len(_PHASE_VALUES) - 1 else '')
    else:
        print('')
except Exception:
    phase_map = {
        'null': 'specify', 'brainstorm': 'specify', 'specify': 'design',
        'design': 'create-plan', 'create-plan': 'create-tasks',
        'create-tasks': 'implement', 'implement': 'finish',
    }
    last = '${LAST_COMPLETED_PHASE}'
    print(phase_map.get(last, ''))
" 2>/dev/null)

if [[ -z "$NEXT_PHASE" ]]; then
    # Unknown phase -- allow stop
    exit 0
fi

FEATURE_REF="${FEATURE_ID}-${FEATURE_SLUG}"
REASON=$(escape_json "[YOLO_MODE] Feature ${FEATURE_REF} in progress. Last completed: ${LAST_COMPLETED_PHASE}. Invoke /iflow:${NEXT_PHASE} --feature=${FEATURE_REF} with [YOLO_MODE].")

cat <<EOF
{
  "decision": "block",
  "reason": "${REASON}"
}
EOF
exit 0
