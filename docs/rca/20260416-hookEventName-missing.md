# RCA: hookSpecificOutput missing required field hookEventName

**Date:** 2026-04-16
**Severity:** Medium (non-blocking errors displayed to user, no data loss)
**Status:** Root cause identified, fix not yet applied

## Problem Statement

Recurring hook errors across multiple workflows:
- Primary: `PreToolUse:Bash hook error -- Hook JSON output validation failed -- hookSpecificOutput is missing required field "hookEventName"`
- Secondary: `SessionStart:resume hook error -- Failed with non-blocking status code: No stderr output`

## Root Causes

### RC-1: post-enter-plan.sh and post-exit-plan.sh missing hookEventName (CONFIRMED)

**Files:**
- `plugins/pd/hooks/post-enter-plan.sh` (line 46-50)
- `plugins/pd/hooks/post-exit-plan.sh` (line 84-89)

**What:** Both PostToolUse hooks output `hookSpecificOutput` with only `additionalContext`, omitting the required `hookEventName` field.

**Current (broken):**
```json
{
  "hookSpecificOutput": {
    "additionalContext": "..."
  }
}
```

**Expected (correct):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "..."
  }
}
```

**Why it wasn't caught earlier:** Claude Code previously accepted `hookSpecificOutput` without `hookEventName` validation. A recent Claude Code update began enforcing the schema, surfacing this latent bug.

**Why it appears as "PreToolUse:Bash":** The error message format may be misleading. The actual failing hooks are PostToolUse:EnterPlanMode/ExitPlanMode, but Claude Code may report the validation error in the context of the next tool use (Bash), or the error message format conflates event types.

**Introduced:** Commit `bbfc63a` (initial plugin creation). Never modified since.

**Affected versions:** All (4.14.16 through 4.15.4 cached, plus current develop).

### RC-2: SessionStart resume transient failure (LIKELY TRANSIENT)

**File:** `plugins/pd/hooks/session-start.sh`

**What:** After `/compact`, the SessionStart:resume hook fails with "No stderr output". The hook itself produces valid JSON output. The error likely originates from a subprocess timeout or database lock during one of: doctor autofix, reconciliation, memory decay, or memory injection.

**Why no diagnostics:** All subprocess stderr is suppressed (`2>/dev/null`) to prevent corrupting JSON hook output. When a subprocess fails, the `|| true` guard swallows the error silently.

**Mitigation:** This is a non-blocking error and self-recovers on the next session start.

## Hypotheses Considered

| # | Hypothesis | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | post-enter-plan.sh / post-exit-plan.sh missing hookEventName | CONFIRMED | Verification script reproduced the bug |
| 2 | Old pre-push-guard.sh cached version | REJECTED | Fix present in all versions >= 4.14.17; old bug had different error pattern |
| 3 | Claude Code stricter validation | CONFIRMED (contributing factor) | These hooks have existed since day one without errors |
| 4 | Hook output merging race condition | REJECTED | Hooks run independently |
| 5 | RTK rewrite hook bug | REJECTED | Outputs correct hookEventName in all code paths |
| 6 | Hookify plugin interference | REJECTED | No hookify rules match Bash commands; no hookSpecificOutput emitted |

## Fix Required

Add `"hookEventName": "PostToolUse"` to `hookSpecificOutput` in both:
1. `plugins/pd/hooks/post-enter-plan.sh` (line 47)
2. `plugins/pd/hooks/post-exit-plan.sh` (line 87)

## Reproduction

```bash
bash agent_sandbox/20260416/rca-hookEventName-missing/experiments/verify-post-hooks-bug.sh
```

## Artifacts

- Reproduction: `agent_sandbox/20260416/rca-hookEventName-missing/reproduction/test-hook-outputs.sh`
- Verification: `agent_sandbox/20260416/rca-hookEventName-missing/experiments/verify-post-hooks-bug.sh`
- Experiment: `agent_sandbox/20260416/rca-hookEventName-missing/experiments/test-empty-vs-json.sh`
