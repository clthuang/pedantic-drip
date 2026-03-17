# RCA: MCP Servers Fail on Marketplace Installation

**Date:** 2026-03-17
**Severity:** Critical (all 3 MCP servers non-functional)
**Status:** Root causes identified, fixes not yet implemented

## Problem Statement

When the iflow plugin is installed via the Claude Code marketplace on a fresh machine, all 3 MCP servers (memory-server, entity-registry, workflow-engine) fail to connect. The plugin works correctly in the dev workspace where a pre-existing `.venv` is available.

## Root Causes

### RC-1: Venv Bootstrap Race Condition (Critical)

**Evidence:** Experimental reproduction confirmed 2 of 3 servers crash.

All 3 MCP servers are configured in `plugin.json` and launched concurrently by Claude Code on startup. Each server's bootstrap script (`run-*.sh`) targets the same venv directory:

```
VENV_DIR="$PLUGIN_DIR/.venv"
```

On a fresh install, no `.venv` exists. All 3 scripts reach the bootstrap path simultaneously. When multiple `python3 -m venv` (or `uv venv`) commands target the same directory concurrently, the later ones fail with:

```
Error: [Errno 17] File exists: '.venv/include/python3.12'
```

With `set -euo pipefail` in each script, this error is fatal -- the script exits and the MCP server never starts.

**Affected files:**
- `plugins/iflow/mcp/run-memory-server.sh` (lines 29-31)
- `plugins/iflow/mcp/run-entity-server.sh` (lines 31-33 or 38-40)
- `plugins/iflow/mcp/run-workflow-server.sh` (lines 31-33 or 38-40)

**Why it works in dev:** The dev workspace already has `.venv` from `uv sync`, so all 3 servers take the fast-path (`if [[ -x "$VENV_DIR/bin/python" ]]`).

### RC-2: Dependency Gap in Shared Venv (Critical)

**Evidence:** Experimental reproduction confirmed memory-server crashes with `ModuleNotFoundError: No module named 'numpy'`.

Even if the race condition is resolved (e.g., servers start sequentially), the bootstrap logic has a design flaw:

1. Each server's fast-path checks only `if [[ -x "$VENV_DIR/bin/python" ]]`
2. It does NOT verify that its specific dependencies are installed
3. Different servers install different dependency sets:
   - memory-server: `mcp`, `numpy`, `python-dotenv`
   - entity-server: `mcp` (only)
   - workflow-engine: `mcp` (only)

If entity-server or workflow-engine bootstraps first, it creates the venv with only `mcp`. When memory-server starts and sees the existing venv, it skips bootstrap and immediately fails trying to import `numpy`.

**Affected files:**
- `plugins/iflow/mcp/run-memory-server.sh` (line 18-20: fast-path skips dependency check)
- `plugins/iflow/mcp/run-entity-server.sh` (line 19-21: installs only `mcp`)
- `plugins/iflow/mcp/run-workflow-server.sh` (line 19-21: installs only `mcp`)

### RC-3: No Python Version Guard (Contributing)

**Evidence:** Code inspection, no experimental reproduction (requires Python < 3.12 environment).

`pyproject.toml` declares `requires-python = ">=3.12"` but none of the bootstrap scripts check the Python version before creating the venv or running servers. On machines with Python 3.10 or 3.11 (common on older macOS/Ubuntu LTS), the venv is created successfully but the server may fail at runtime due to 3.12+ syntax features or stdlib changes.

**Affected files:**
- All 3 `run-*.sh` scripts (none check Python version)
- `plugins/iflow/pyproject.toml` (declares requirement not enforced at runtime)

## Hypotheses Considered and Rejected

### H4: Execute Permission Stripping

**Hypothesis:** Marketplace installation might strip execute bits from shell scripts.
**Evidence against:** Git stores file mode 100755 in the index, and `git clone` preserves it. All 3 run scripts are committed with mode 100755. Claude Code marketplace uses git-based cloning. Rejected as unlikely, though non-git distribution (tarball via GitHub API) could theoretically strip permissions.

### H5: Plugin Cache Directory Write Restrictions

**Hypothesis:** The `~/.claude/plugins/cache/` directory might be read-only, preventing venv creation.
**Evidence against:** Local inspection shows the cache directory is writable (drwxr-xr-x). Claude Code documentation confirms plugins are copied to this directory during install, implying write access. Rejected.

### H6: PYTHONPATH / hooks/lib Missing

**Hypothesis:** The `hooks/lib/` directory with `semantic_memory`, `entity_registry`, etc. might not be included in the marketplace install.
**Evidence against:** These are regular tracked files in the git repo (not gitignored). Marketplace clone would include them. Verified all 4 packages exist in the cloned copy. Rejected.

## Interaction Effects

RC-1 and RC-2 compound each other:
- If the race condition (RC-1) is partially resolved (e.g., only 1 server fails), the surviving server creates a venv with incomplete deps, triggering RC-2 for servers that restart later.
- If all servers are retried after RC-1 failure, the venv may be in a corrupted/partial state.

## Reproduction

Experiments are in `agent_sandbox/20260317/rca-mcp-marketplace/`:
- `reproduction/simulate_marketplace_install.sh` -- end-to-end simulation
- `experiments/test_race_condition.sh` -- confirms RC-1 (2/3 servers fail)
- `experiments/test_dep_gap.sh` -- confirms RC-2 (numpy missing after entity-server bootstrap)

## Scope of Impact

- **All fresh marketplace installs:** 100% failure rate on first launch
- **After manual venv creation:** Works if user runs `uv sync` manually in plugin dir
- **Dev workspace:** Unaffected (pre-existing venv from development)
