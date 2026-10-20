# RCA: MCP Servers Fail to Start on Fresh Install Due to Python Discovery and Silent Failure

**Date:** 2026-03-18
**Severity:** Critical
**Status:** Root causes identified, fixes not yet applied
**Triggered by:** External report from fresh install on another machine

---

## Problem Statement

On a fresh iflow installation, all three MCP servers (memory-server, entity-registry, workflow-engine) fail to start silently. The agent loses access to `transition_phase`, `complete_phase`, `store_memory`, and all other MCP tools. Feature `.meta.json` files cannot be updated through the workflow, and the user receives no clear indication of what went wrong.

---

## Root Causes (5 confirmed, 1 partially mitigated)

### RC-1: No Intelligent Python Discovery (PRIMARY)

**File:** `plugins/iflow/mcp/bootstrap-venv.sh` lines 26-35
**Evidence:** `check_python_version()` calls bare `python3` from PATH. No search for versioned interpreters (`python3.12`, `python3.13`, `python3.14`) in common locations (`/opt/homebrew/bin`, `/usr/local/bin`).

When macOS system Python 3.9 at `/usr/bin/python3` shadows a Homebrew Python 3.13+ at `/opt/homebrew/bin/python3.13` due to PATH ordering, the version check fails and the server exits.

**Impact:** Direct cause of all MCP servers failing to start.

### RC-2: Version Requirement Inconsistency Between Doctor and Bootstrap

**File:** `plugins/iflow/scripts/doctor.sh` line 149 vs `plugins/iflow/mcp/bootstrap-venv.sh` line 31
**Evidence:**
- `doctor.sh` (used by `setup.sh`): passes if Python >= 3.10
- `bootstrap-venv.sh` (used by MCP servers): requires Python >= 3.12

**Impact:** A user with Python 3.10 or 3.11 passes all setup diagnostics, creates a working venv, then has MCP servers silently fail at runtime. The setup process gives a false "all clear" signal.

### RC-3: Bootstrap Failures Are Invisible to the Agent

**File:** `plugins/iflow/mcp/bootstrap-venv.sh` line 32-33, all `run-*.sh` scripts
**Evidence:**
- Error messages go exclusively to stderr (`>&2`)
- Failure mode is `exit 1` -- the process terminates
- No structured error response in MCP protocol format
- No error handling wrappers in `run-*.sh` scripts (0 trap statements, 0 error handlers)
- Claude Code sees the MCP server simply not register -- tools silently disappear

**Impact:** The agent has no way to know WHY tools are missing. It cannot self-diagnose or suggest fixes.

### RC-4: Session-Start Does Not Validate MCP Server Health

**File:** `plugins/iflow/hooks/session-start.sh`
**Evidence:**
- No reference to `bootstrap-complete`, `mcp`, or any server health probe
- Session starts and injects context without knowing if MCP tools will be available
- The first-run detection (lines 272-275) checks for `.venv` existence but NOT for the bootstrap sentinel
- First-run message is a soft `additionalContext` note, not a hard warning or block

**Impact:** Even when MCP servers are completely non-functional, the session starts normally. The agent discovers missing tools only when it tries to use them, well into a workflow.

### RC-5: setup.sh Is Never Automatically Invoked

**File:** `plugins/iflow/hooks/session-start.sh` lines 272-275, `plugins/iflow/.claude-plugin/plugin.json`
**Evidence:**
- `plugin.json` defines MCP servers but has no `postInstall` or setup hook
- Session-start emits a soft "First run detected" note buried in `additionalContext`
- The note competes with feature status, memory context, and other information
- No mechanism forces or strongly prompts the user to run setup before using the plugin

**Impact:** Users start using iflow without running setup, leading to RC-1 through RC-4 compounding.

### RC-6: meta-json-guard Deadlock (PARTIALLY MITIGATED)

**File:** `plugins/iflow/hooks/meta-json-guard.sh` lines 40-41, 76-81
**Evidence:**
- The guard DOES check for `.bootstrap-complete` sentinel via glob
- When sentinel is absent, it allows direct writes (`permit-degraded`)
- This was likely added as feature 041 (commit e38725c, visible in recent history)

**Mitigation status:** The deadlock described in the external report appears to be resolved in the current codebase. However, there is a subtle interaction: `setup.sh` does NOT create the bootstrap sentinel (confirmed by grep). The sentinel only appears after a successful MCP server launch via `bootstrap_venv()`. So the guard's degradation check is correctly keyed to actual MCP availability, not just venv existence.

**Residual risk:** If a stale sentinel exists from a previous successful bootstrap but MCP servers are currently failing (e.g., after a Python upgrade that changes the PATH), the guard will DENY writes even though MCP tools are unavailable. The sentinel check (`ls *.bootstrap-complete`) does not verify the servers are currently running.

---

## Causal DAG

```
Fresh install, no setup.sh run
    |
    v
PATH ordering puts system Python 3.9 before Homebrew Python 3.13+ [RC-1]
    |
    v
bootstrap-venv.sh check_python_version() finds 3.9, exits 1
    |                                                        \
    v                                                         v
Error goes to stderr only [RC-3]                 Doctor check passed with 3.10 threshold [RC-2]
    |                                                         |
    v                                                         v
MCP servers silently vanish                      User thinks setup is fine [RC-5]
    |
    v
Session-start injects context without MCP health check [RC-4]
    |
    v
Agent discovers missing tools mid-workflow
    |
    v
meta-json-guard detects missing sentinel, allows degraded writes [RC-6, mitigated]
    (but stale sentinel scenario = still blocks)
```

## Interaction Effects

1. **RC-1 + RC-3:** Python discovery failure is the trigger, but silent failure is what makes it critical. If the error were visible, the user could fix PATH.

2. **RC-2 + RC-5:** The version inconsistency is particularly dangerous because `setup.sh` gives a false "all clear" at 3.10+. Combined with setup never being required, users on 3.10-3.11 are completely blindsided.

3. **RC-4 + RC-3:** Session-start's lack of MCP validation means the silent failure from RC-3 persists for the entire session. There is no second chance to detect the problem.

4. **RC-6 stale sentinel + RC-1:** If a user previously had a working setup, then upgrades Python or changes PATH, the stale sentinel causes the guard to block writes even though MCP is now broken. This creates the deadlock the external report described.

---

## Verification Scripts

All scripts are at `agent_sandbox/2026-03-18/rca-mcp-bootstrap/experiments/`:

| Script | Tests | Result |
|--------|-------|--------|
| `verify_h1_python_discovery.sh` | Versioned interpreter search in bootstrap | CONFIRMED: bare python3 only |
| `verify_h2_error_visibility.sh` | Error reporting mechanism | CONFIRMED: stderr-only, exit 1 |
| `verify_h3_guard_degradation.sh` | meta-json-guard MCP detection | CONFIRMED: degradation exists |
| `verify_h4_h6_session_start.sh` | Session MCP validation + setup enforcement | CONFIRMED: neither exists |
| `verify_h5_version_mismatch.sh` | Doctor vs bootstrap version thresholds | CONFIRMED: 3.10 vs 3.12 gap |

---

## Recommended Fix Areas (not prescriptive -- for handoff to /create-feature)

1. **Python discovery in bootstrap-venv.sh:** Search for versioned interpreters before falling back to bare `python3`. Consider `python3.14`, `python3.13`, `python3.12` in `/opt/homebrew/bin`, `/usr/local/bin`, then bare `python3`.

2. **Align version requirements:** Update `doctor.sh` `check_python3()` threshold from 3.10 to 3.12 to match `bootstrap-venv.sh`.

3. **Structured error reporting from MCP bootstrap:** When bootstrap fails, emit a diagnostic that Claude Code can surface to the agent (or at minimum, write to a well-known log file that session-start checks).

4. **MCP health check in session-start:** Check for bootstrap sentinel AND optionally probe MCP server responsiveness. Surface a hard warning (not buried in context) if MCP is non-functional.

5. **Stale sentinel handling in meta-json-guard:** Instead of just checking sentinel existence, verify the sentinel is from the current plugin version or that the venv's Python still meets version requirements.

---

## References

| File | Relevance |
|------|-----------|
| `plugins/iflow/mcp/bootstrap-venv.sh` | Python version check and venv bootstrap |
| `plugins/iflow/scripts/doctor.sh` | System health checks (version threshold) |
| `plugins/iflow/scripts/setup.sh` | Interactive installer |
| `plugins/iflow/hooks/meta-json-guard.sh` | Direct write guard with MCP degradation |
| `plugins/iflow/hooks/session-start.sh` | Session initialization and first-run detection |
| `plugins/iflow/.claude-plugin/plugin.json` | MCP server configuration |
| `plugins/iflow/mcp/run-memory-server.sh` | Example MCP server runner |
