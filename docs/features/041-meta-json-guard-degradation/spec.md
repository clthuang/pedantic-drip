# Specification: meta-json-guard Degradation Path

**Source:** RCA report `docs/rca/20260318-meta-json-guard-deadlock.md` (no PRD — bug fix originating from production incident on fresh install)

## Problem Statement

The `meta-json-guard.sh` PreToolUse hook unconditionally blocks all Edit/Write operations targeting `.meta.json` files, directing Claude to use MCP workflow tools instead. When MCP tools are unavailable (server not started, bootstrap failure, venv broken), Claude enters a deadlock loop: the hook blocks the Edit, Claude has no alternative path, and retries the Edit — indefinitely.

This was discovered on a freshly set up machine where iflow was installed via GitHub marketplace (see RCA report).

## Root Cause (from RCA)

1. **Primary:** `meta-json-guard.sh` (line 66-76) has zero degradation logic — unconditional deny regardless of MCP tool availability
2. **Contributing:** Hook deny message lacks `feature_type_id` format, parameter hints, and fallback instructions
3. **Contributing:** MCP bootstrap can silently fail on fresh installs (missing sentinel despite working venv)

## Requirements

### R1: Detect MCP workflow tool availability before blocking

The hook MUST check whether MCP workflow tools are registered in the current session before issuing a deny decision. If MCP tools are NOT available, the hook MUST allow the Edit/Write to proceed (permit decision).

**Detection mechanism:** The hook receives the full tool input JSON on stdin. The `tool_input` field contains the tool call context. However, hooks cannot directly query which tools are registered. Instead, use a proxy signal:

- Check if the workflow-engine MCP server bootstrap has completed by testing for the existence of the bootstrap sentinel file at the expected cache path pattern: `~/.claude/plugins/cache/*/iflow*/*/.venv/.bootstrap-complete`
- **Matching rule:** If ANY path matching the glob exists, MCP tools are considered available → deny as before. If NO path matches → MCP tools are likely unavailable → allow the write (permit).
- The sentinel check MUST NOT increase hook latency beyond the existing 200ms CI threshold (applies to both deny and permit-degraded paths; existing fast-path for non-.meta.json input is unaffected).
- **Implementation idiom:** Use `ls ~/.claude/plugins/cache/*/iflow*/*/.venv/.bootstrap-complete 2>/dev/null` and check exit code, consistent with hook subprocess safety rules (stderr suppression).

**Known limitation:** The sentinel existing does not guarantee the MCP server connected successfully this session. Scenarios where sentinel exists but MCP is broken (e.g., cache version mismatch, server crash) are NOT addressed by this check. These are handled by the existing `workflow-transitions/SKILL.md` degradation logic (lines 116-119, 207-210) once Claude attempts an MCP tool call that returns an error. This is acceptable because the primary deadlock trigger — fresh installs where bootstrap never completed — is the scenario where no sentinel exists.

**Cache layout coupling:** The glob pattern `~/.claude/plugins/cache/*/iflow*/*/.venv/.bootstrap-complete` is coupled to the current plugin cache directory structure. If the cache layout changes, this glob must be updated. This is tracked as a known coupling.

### R2: Enrich deny message with actionable guidance

When the hook denies a write (MCP tools believed available), the deny reason MUST include:

1. The MCP tool names (existing): `transition_phase()`, `complete_phase()`, `init_feature_state()`
2. The `feature_type_id` format: `"feature:{id}-{slug}"` (e.g., `"feature:041-meta-json-guard-degradation"`)
3. A fallback instruction: "If MCP workflow tools are not available in this session, the guard will allow direct writes as a fallback."

### R3: Log degradation events

When the hook permits a write due to MCP unavailability (degraded mode), it MUST log the event to `~/.claude/iflow/meta-json-guard.log` using the same JSONL schema as existing deny log entries, plus an `"action"` field:

- **Degraded permit entry:** `{"timestamp": "...", "tool": "...", "path": "...", "feature_id": "...", "action": "permit-degraded"}`
- The `timestamp` field MUST use the same format as existing deny entries: ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`).
- **Existing deny entries:** Remain unchanged (no `"action"` field added to preserve backward compatibility with any log consumers).
- Implementation note: The existing `log_blocked_attempt` function in `meta-json-guard.sh` should be renamed or extended to accept an optional action parameter (default: current deny behavior). The function name should reflect that it covers both deny and permit-degraded events.

### R4: No changes to existing deny behavior when MCP is available

When MCP tools are detected as available (sentinel exists), the hook MUST continue to deny Edit/Write to `.meta.json` exactly as it does today. This fix only adds a degradation path, not a behavior change for the happy path.

## Acceptance Criteria

- AC1: Given no `.bootstrap-complete` sentinel file exists at any `~/.claude/plugins/cache/*/iflow*/*/.venv/.bootstrap-complete` path, when Claude attempts to Edit a `.meta.json` file, then the hook returns a permit decision (empty JSON `{}`).
- AC2: Given a sentinel file exists at any matching path, when Claude attempts to Edit a `.meta.json` file, then the hook returns a deny decision (same as current behavior).
- AC3: The deny message includes `feature_type_id` format guidance: `"feature:{id}-{slug}"`.
- AC4: The deny message includes the fallback instruction about MCP unavailability.
- AC5: When a write is permitted due to degradation, a JSONL log entry with `"action": "permit-degraded"` is appended to `~/.claude/iflow/meta-json-guard.log`, including `timestamp`, `tool`, `path`, and `feature_id` fields.
- AC6: Existing hook deny tests are updated to create a sentinel file in their temp HOME directory (e.g., `$TEMP_HOME/.claude/plugins/cache/test-plugin/iflow-test/1.0.0/.venv/.bootstrap-complete` — any path matching the glob `$HOME/.claude/plugins/cache/*/iflow*/*/.venv/.bootstrap-complete`) so they continue testing the deny path. All updated tests pass (`bash plugins/iflow/hooks/tests/test-hooks.sh`).
- AC7: When the sentinel file exists, the hook behavior is identical to the current implementation (no regression).
- AC8: Given no `.bootstrap-complete` sentinel file exists at any matching cache path AND `HOME` is set to a temp directory, when Claude attempts to Write to a `.meta.json` file, then the hook returns a permit decision (`{}`) AND a JSONL entry with `"action": "permit-degraded"` is appended to `$HOME/.claude/iflow/meta-json-guard.log`.

## Scope

### In Scope
- Modify `plugins/iflow/hooks/meta-json-guard.sh` to add sentinel-based degradation check
- Enrich the deny reason message
- Add degradation logging
- Update existing deny tests to create sentinel file in temp HOME
- Add new test coverage for the degradation path

### Out of Scope
- Bootstrap sentinel reliability improvements (separate feature — Contributing Cause 2, to be added to backlog)
- Cache directory version mismatch fix (separate feature — Contributing Cause 3, to be added to backlog)
- Changes to `workflow-transitions/SKILL.md` degradation logic (already correct)
- Changes to MCP server code
- Adding `"action": "deny"` to existing deny log entries (backward compatibility)
