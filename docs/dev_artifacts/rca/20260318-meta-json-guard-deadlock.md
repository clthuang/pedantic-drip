# RCA: meta-json-guard Deadlock and Multi-System Errors

**Date:** 2026-03-18
**Severity:** Critical (Error 1), Low (Errors 2-5)
**Affected systems:** iflow plugin workflow on newly set up machines
**Investigator:** RCA Agent

---

## Problem Statement

On a newly set up computer with iflow installed via GitHub marketplace, Claude Code repeatedly attempts to Edit `.meta.json` files, gets blocked by the `meta-json-guard` PreToolUse hook, and enters a deadlock loop. The hook tells Claude to use MCP workflow tools, but Claude continues using Edit. Additionally, several secondary errors were observed across multiple systems.

## Error Classification

| Error | Severity | Status | Related? |
|-------|----------|--------|----------|
| 1: meta-json-guard deadlock | Critical | Investigated | Primary |
| 2: Gateway allowlist unknowns | Low | Investigated | Independent |
| 3: Subagent orphan pruned | Low | Investigated | Independent |
| 4: Missing cognee-sidecar .env | Low | Investigated | Independent |
| 5: Discord gateway startup | Informational | N/A | Independent |

---

## Error 1: meta-json-guard Deadlock (CRITICAL)

### Root Cause: Unconditional block with no degradation path

**File:** `plugins/iflow/hooks/meta-json-guard.sh` (line 66-76)

The `meta-json-guard.sh` hook unconditionally denies all Edit/Write operations targeting `.meta.json` files. It directs Claude to use MCP workflow tools (`transition_phase()`, `complete_phase()`, `init_feature_state()`). However, the hook has **zero degradation logic** -- it blocks regardless of whether MCP tools are actually available in the current session.

**The deadlock chain:**
1. Claude wants to update `.meta.json` (normal workflow operation)
2. `meta-json-guard.sh` blocks the Edit with deny decision
3. If MCP tools are unavailable (server not started, connection failed, venv broken), Claude has no path forward
4. Claude reads `workflow-transitions/SKILL.md` for guidance
5. SKILL.md says to use MCP tools, which are unavailable
6. Claude retries Edit -- blocked again
7. Loop continues indefinitely

**Contrast with SKILL.md design:** The `workflow-transitions/SKILL.md` has explicit degradation (lines 116-119, 207-210): "If the call fails for any reason... output a note... Do NOT block -- proceed regardless." But this degradation only activates AFTER Claude successfully calls an MCP tool that returns an error. If Claude never gets to call MCP tools (because they aren't in the tool list), the degradation is never reached.

### Contributing Cause 1: Hook error message lacks actionable recovery guidance

**File:** `plugins/iflow/hooks/meta-json-guard.sh` (line 66)

The deny message tells Claude WHAT to use but not HOW to use it or WHAT TO DO IF UNAVAILABLE:
- Names the tools (good): `transition_phase()`, `complete_phase()`, `init_feature_state()`
- Missing: `feature_type_id` format (`"feature:{id}-{slug}"`)
- Missing: Required parameters and types
- Missing: Fallback instructions if MCP tools are not available

When MCP tools ARE registered in the session, Claude can discover parameters from the tool schema. But the message provides no diagnostic path for the case where tools are absent.

### Contributing Cause 2: MCP server bootstrap fragility on fresh installations

**File:** `plugins/iflow/mcp/bootstrap-venv.sh`

Evidence from this machine:
- The `.bootstrap-complete` sentinel file is **MISSING** at `~/.claude/plugins/cache/my-local-plugins/iflow/4.13.1-dev/.venv/.bootstrap-complete`
- The venv exists and all deps are importable (the server works when tested manually)
- This indicates the original bootstrap process either crashed after installing deps but before writing the sentinel, or the sentinel was cleaned up

On a brand new machine, the bootstrap sequence must:
1. Check Python >= 3.12
2. Check if system python has all deps (unlikely on fresh install)
3. Create venv if needed
4. Install all deps (requires network, `uv` or `pip`)
5. Write sentinel

If step 4 fails (network issues, `uv` not installed, pip timeout), the MCP server won't start. The 120-second lock timeout means other server instances waiting will also fail.

### Contributing Cause 3: Plugin cache version mismatch

**File:** `plugins/iflow/hooks/sync-cache.sh`

The `sync-cache.sh` SessionStart hook runs `rsync --delete --exclude='.venv'` from the source project to the cache directory. This updates file contents but **cannot rename the cache directory**. Result:

| Cache Directory Name | plugin.json Version |
|---------------------|-------------------|
| 4.12.4-dev | 4.13.0-dev |
| 4.13.1-dev | 4.13.3-dev |

The user's error screenshot references version `4.13.4` which doesn't exist on this machine's cache. This suggests the new machine has a different cache state, potentially with a plugin version that has different tool definitions than what the hooks expect.

If Claude Code uses the directory name for any version-based logic (tool registration, capability discovery), the mismatch could cause tools to not be registered or to be registered under wrong capabilities.

### Evidence Summary

| Hypothesis | Verdict | Evidence |
|-----------|---------|----------|
| H1: MCP servers not connecting | Plausible (not reproducible locally) | Server starts and exposes 15 tools when tested manually; but missing sentinel suggests bootstrap issues on fresh install |
| H2: Hook error message insufficient | Confirmed (contributing) | Message lacks feature_type_id format, parameters, and fallback instructions |
| H3: Version mismatch in cache | Confirmed (contributing) | All 3 cache directories show directory-vs-plugin.json version mismatch |
| H4: No degradation path in guard | Confirmed (primary) | Guard has zero bypass/fallback logic; unconditional deny on all .meta.json writes |
| H5: PROJECT_ROOT not set for MCP | Mitigated | Server falls back to `os.getcwd()`, which Claude Code sets to project dir |

---

## Error 2: Gateway Allowlist Unknown Entries

**System:** knowsy remote server
**Log:** `tools.profile (coding) allowlist contains unknown entries (apply_patch, cron, image)`

### Root Cause

The knowsy project's tools profile references Claude Code core tools (`apply_patch`, `cron`, `image`) that are not available in the specific runtime/provider/model configuration being used. These tools exist in some Claude Code environments but are platform-specific.

**Impact:** Informational warning. The tools are silently ignored; other tools work normally.

---

## Error 3: Subagent Orphan Run Pruned

**System:** knowsy
**Log:** `Subagent orphan run pruned source=resume run=ec5f68fb... reason=missing-session-entry`

### Root Cause

A parent session was terminated or lost connectivity while a subagent was running. On session resume, Claude Code detected the orphaned subagent (child reference exists but parent session entry is missing) and pruned it.

**Impact:** Low. Expected behavior during session recovery. The subagent's work may be lost but no data corruption occurs.

---

## Error 4: Missing cognee-sidecar .env

**System:** knowsy remote server (user: terry_agent)
**Log:** `ls: /Users/terry_agent/.openclaw-scripts/cognee-sidecar/.env: No such file or directory`

### Root Cause

Incomplete deployment of the cognee-sidecar component. The `cognee-data/.env` exists (with ollama-local configuration) but `cognee-sidecar/.env` was never created. This is a deployment gap -- the sidecar setup script either wasn't run or doesn't create the `.env` file.

**Impact:** cognee-sidecar will fail to start/configure properly. Requires manual `.env` creation or running the sidecar setup procedure.

---

## Error 5: Discord Gateway Startup

Normal startup log. Not an error.

---

## Relationship Between Errors

Errors 2-5 are **independent** of Error 1. They occur on different systems (knowsy remote server) and different components (Discord bot, cognee sidecar, gateway tools profile). Error 1 is specific to the iflow plugin's hook/MCP interaction model.

The user's hypothesis of "no clear prioritisation amongst all entities" and "data not properly syncing" is partially validated by Error 1's root cause: the hook enforces MCP-only writes but doesn't verify MCP availability first. The "data not properly syncing" concern maps to Contributing Cause 3 (cache version mismatch via sync-cache.sh).

---

## Recommended Investigation Areas (not fixes)

These are areas that warrant attention based on the root causes identified. Actual fixes should be planned separately.

1. **meta-json-guard.sh degradation path** -- The guard needs awareness of whether MCP tools are actually available before unconditionally blocking
2. **Hook error message enrichment** -- Include feature_type_id format and fallback instructions in the deny reason
3. **Bootstrap sentinel reliability** -- Investigate why the sentinel is missing on a machine where deps are fully installed
4. **Cache directory naming** -- The sync-cache.sh rsync approach creates permanent version mismatches between directory names and actual content
5. **cognee-sidecar deployment** -- Add .env template or setup script for the sidecar component on knowsy

---

## Files Investigated

| File | Relevance |
|------|-----------|
| `plugins/iflow/hooks/meta-json-guard.sh` | Primary: the unconditional block |
| `plugins/iflow/hooks/hooks.json` | Hook registration (PreToolUse matcher) |
| `plugins/iflow/.claude-plugin/plugin.json` | MCP server definitions |
| `plugins/iflow/mcp/run-workflow-server.sh` | Server bootstrap entry point |
| `plugins/iflow/mcp/bootstrap-venv.sh` | Venv creation and dep management |
| `plugins/iflow/mcp/workflow_state_server.py` | MCP tool definitions and PROJECT_ROOT resolution |
| `plugins/iflow/skills/workflow-transitions/SKILL.md` | Degradation logic (exists but unreachable in deadlock) |
| `plugins/iflow/skills/workflow-state/SKILL.md` | State schema and MCP tool usage |
| `plugins/iflow/hooks/sync-cache.sh` | Cache sync causing version mismatch |
| `plugins/iflow/hooks/lib/common.sh` | Shared hook utilities |
| `~/.claude/settings.json` | Plugin enablement config |

## Sandbox Artifacts

All investigation artifacts at: `agent_sandbox/20260318/rca-meta-json-guard-deadlock/`
- `reproduction/simulate-hook-block.sh` -- Reproduces the hook block behavior
- `experiments/test-h1-mcp-connectivity.sh` -- Verified MCP server tool discovery works
- `experiments/test-h2-error-message.sh` -- Analyzed error message deficiencies
- `experiments/test-h4-no-degradation.sh` -- Confirmed zero degradation in guard
- `experiments/test-h5-project-root.sh` -- Verified PROJECT_ROOT resolution
- `experiments/hypothesis-analysis.md` -- Initial hypothesis list
- `experiments/root-cause-synthesis.md` -- Cross-cause analysis
