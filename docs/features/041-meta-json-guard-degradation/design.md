# Design: meta-json-guard Degradation Path

## Prior Art Research

### Codebase Patterns
- **Global safety net:** `install_err_trap` in `common.sh` emits `{}` (permit) on uncaught ERR — already provides crash-level degradation
- **Sentinel file pattern:** `bootstrap-venv.sh` uses `${venv_dir}/.bootstrap-complete` (touch-created), checked via `[ -f "$sentinel" ]`
- **Conditional permit/deny:** `yolo-guard.sh` reads state files to decide permit vs deny; `pre-exit-plan-review.sh` uses counter-based state gates
- **Service availability checks:** `session-start.sh` uses `compgen -G` against cache dir globs to detect plugin presence — degrades to advisory, never blocks
- **log function pattern:** `log_blocked_attempt` is local to meta-json-guard.sh, writes JSONL via `>>` to `~/.claude/iflow/meta-json-guard.log`

### External Research
- **Fail-open principle:** Hook systems should default to allow when dependency checks fail (exit 0 + stderr warning, not hard block)
- **Dependency presence check:** `ls <glob> 2>/dev/null` or `compgen -G <glob>` are the idiomatic POSIX/bash patterns for glob-based file existence
- **AWS graceful degradation:** Transform hard dependencies into soft ones — a guard against a soft-dependency service should degrade to warning, not block

## Architecture Overview

Single-file change to `plugins/iflow/hooks/meta-json-guard.sh`. No new files, no new dependencies.

### Control Flow (Modified)

```
Input (stdin JSON)
    │
    ├─ Fast path: no ".meta.json" in input → permit ({})
    │
    ├─ Python3 parse: extract file_path + tool_name
    │   └─ file_path not *.meta.json → permit ({})
    │
    ├─ NEW: Sentinel check
    │   └─ ls ~/.claude/plugins/cache/*/iflow*/*/.venv/.bootstrap-complete 2>/dev/null
    │       ├─ Exit 0 (found) → MCP available → continue to deny
    │       └─ Exit non-0 (not found) → MCP unavailable → log permit-degraded → permit ({})
    │
    ├─ Log blocked attempt (existing)
    │
    └─ Deny with enriched message
```

### Components

**C1: Sentinel Check Function** (`check_mcp_available`)
- New function, ~5 lines
- Uses `ls` with stderr suppressed (per spec R1 implementation idiom)
- Returns 0 if sentinel found (MCP available), 1 if not found (MCP unavailable)

**C2: Logging Function** (`log_guard_event`)
- Renamed from `log_blocked_attempt`
- Added optional `action` parameter (default: no action field for backward compat)
- When `action` is provided, includes `"action": "$action"` in JSONL entry

**C3: Enriched Deny Message**
- Updated REASON string with `feature_type_id` format and fallback instruction
- No structural change to the deny JSON output block

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Detection method | `ls` glob + exit code | Spec mandates this idiom; consistent with `session-start.sh` pattern using `compgen -G` |
| Sentinel check placement | After python3 parse, before log+deny | Minimizes overhead — only runs for confirmed .meta.json targets |
| Function rename | `log_blocked_attempt` → `log_guard_event` | Semantically covers both deny and permit-degraded events |
| Action field | Optional parameter, omitted for deny | Backward compatibility — existing deny entries unchanged per R3 |
| Test sentinel path | `$HOME/.claude/plugins/cache/test-org/iflow-test/1.0/.venv/.bootstrap-complete` | Matches the glob pattern while being clearly synthetic |

## Risks

| Risk | Mitigation |
|------|-----------|
| Glob expansion slow with many cache dirs | `ls` exits on first match; typical installs have 1-3 cache dirs |
| Sentinel exists but MCP actually broken | SKILL.md degradation handles this (documented in spec Known Limitation) |
| Cache layout changes break glob | Tracked as known coupling in spec; single grep finds all references |
| Renaming function breaks grep-based tooling | Function is local to one file; no external callers |

## Interfaces

### C1: `check_mcp_available()`

Define this function near the top of the file, grouped with `log_guard_event` (around line 40), before the sentinel check call site.

```bash
# Returns 0 if MCP sentinel found (available), 1 if not (unavailable)
# Both stdout and stderr suppressed — stdout must not leak into hook JSON output.
# Stderr suppressed per spec R1 idiom.
check_mcp_available() {
    ls "$HOME"/.claude/plugins/cache/*/iflow*/*/.venv/.bootstrap-complete >/dev/null 2>/dev/null
}
```

**`set -e` interaction:** The call site uses `if ! check_mcp_available; then`, which per POSIX suppresses errexit for the function body. The ERR trap (`install_err_trap`) will NOT fire when `ls` returns non-zero inside this `if` context.

### Degraded Permit Path (call site)

```bash
# Placed after python3 parse, before existing log+deny block
if ! check_mcp_available; then
    log_guard_event "$FILE_PATH" "$TOOL_NAME" "permit-degraded"
    echo '{}'
    exit 0
fi
```

### Deny Path (updated call site)

```bash
# Existing line 63, just function name change (no action param for deny)
log_guard_event "$FILE_PATH" "$TOOL_NAME"
```

### C2: `log_guard_event(file_path, tool_name [, action])`

```bash
# Logs a guard event to ~/.claude/iflow/meta-json-guard.log
# $1: file_path being guarded
# $2: tool_name attempting the write
# $3: action (optional) - "permit-degraded" for degraded permits, omit for deny
log_guard_event() {
    local file_path="$1"
    local tool_name="$2"
    local action="${3:-}"
    local log_dir="$HOME/.claude/iflow"
    local log_file="$log_dir/meta-json-guard.log"
    local timestamp feature_id action_field

    mkdir -p "$log_dir"
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Extract feature_id from path
    if [[ "$file_path" =~ features/([^/]+)/\.meta\.json ]]; then
        feature_id="${BASH_REMATCH[1]}"
    elif [[ "$file_path" =~ projects/([^/]+)/\.meta\.json ]]; then
        feature_id="${BASH_REMATCH[1]}"
    else
        feature_id="unknown"
    fi

    # Build optional action field
    if [[ -n "$action" ]]; then
        action_field=",\"action\":\"$(escape_json "$action")\""
    else
        action_field=""
    fi

    echo "{\"timestamp\":\"$timestamp\",\"tool\":\"$tool_name\",\"path\":\"$(escape_json "$file_path")\",\"feature_id\":\"$feature_id\"${action_field}}" >> "$log_file"
}
```

### C3: Enriched Deny Message

```bash
REASON="Direct .meta.json writes are blocked. Use MCP workflow tools instead: transition_phase(feature_type_id, target_phase) to enter a phase, complete_phase(feature_type_id, phase) to finish a phase, or init_feature_state(...) to create a new feature. The feature_type_id format is \"feature:{id}-{slug}\" (e.g., \"feature:041-meta-json-guard-degradation\"). If MCP workflow tools are not available in this session, the guard will allow direct writes as a fallback."
```

## Test Strategy

### Existing Tests (Updated)

All existing tests that use a temp HOME and expect deny behavior must create the sentinel. These tests currently use inline `HOME="$(mktemp -d)"` — they must be refactored to use the `setup_meta_guard_test`/`teardown_meta_guard_test` helper pattern (already used by log tests), then create the sentinel inside `META_GUARD_TMPDIR`.

**Tests requiring sentinel creation (5 total):**
1. `test_meta_json_guard_denies_write` — deny test, needs sentinel + refactor to helpers
2. `test_meta_json_guard_denies_edit` — deny test, needs sentinel + refactor to helpers
3. `test_meta_json_guard_denies_project_meta` — deny test, needs sentinel + refactor to helpers
4. `test_meta_json_guard_logs_blocked_attempt` — log test, already uses helpers, just add sentinel
5. `test_meta_json_guard_extracts_feature_id` — log test, already uses helpers, just add sentinel

**Sentinel creation (add to setup or before hook invocation):**
```bash
mkdir -p "$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/iflow-test/1.0/.venv"
touch "$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/iflow-test/1.0/.venv/.bootstrap-complete"
```

Without sentinel, log tests would hit the degraded-permit path instead of deny, silently changing the log entry schema (adding `"action"` field) and the hook exit decision.

### New Tests
1. **test_meta_json_guard_permits_when_no_sentinel** — No sentinel in temp HOME → hook returns `{}`
2. **test_meta_json_guard_logs_permit_degraded** — No sentinel → verify JSONL log has `"action": "permit-degraded"`
3. **test_meta_json_guard_deny_message_has_feature_type_id** — Sentinel present → deny message contains `feature:{id}-{slug}`
4. **test_meta_json_guard_deny_message_has_fallback** — Sentinel present → deny message contains fallback instruction
