# Spec: MCP Bootstrap Race Fix

## Problem Statement

When the iflow plugin is installed via the Claude Code marketplace on a fresh machine, all 4 server bootstrap scripts (3 MCP servers + UI server) share a single `.venv` directory and launch concurrently on session start. Root cause analysis identified three issues: a venv bootstrap race condition, a dependency gap in the shared venv fast-path, and missing Python version guards.

## Affected Scripts

All 4 bootstrap scripts share `$PLUGIN_DIR/.venv` and must participate in the fix:
- `plugins/iflow/mcp/run-memory-server.sh` — launched by plugin.json (MCP)
- `plugins/iflow/mcp/run-entity-server.sh` — launched by plugin.json (MCP)
- `plugins/iflow/mcp/run-workflow-server.sh` — launched by plugin.json (MCP)
- `plugins/iflow/mcp/run-ui-server.sh` — launched by SessionStart hook (concurrent with MCP servers)

Note: The PRD (RCA report) identified 3 MCP servers. The 4th server (`run-ui-server.sh`) shares the same `.venv` directory and launches concurrently via SessionStart hook, making it subject to the identical race condition and dependency gap. It is included in scope because the root cause (shared venv + concurrent bootstrap) applies equally.

## Requirements

### FR-1: Serialized Venv Bootstrap

All 4 server bootstrap scripts must coordinate venv creation so that only one process creates the venv while others wait. Concurrent `python3 -m venv` / `uv venv` calls to the same directory must not occur.

**Acceptance Criteria:**
- AC-1.1: When 4 servers start concurrently on a fresh install, exactly one creates the venv; the other three wait and reuse it.
- AC-1.2: The coordination mechanism must use `mkdir` as an atomic lock on all platforms (macOS and Linux) for implementation simplicity. Do not use `flock` even where available.
- AC-1.3: If the bootstrap process crashes mid-venv-creation, the lock must not permanently block other servers. Staleness detection: if the lock directory exists and its mtime is older than 120 seconds, remove it and retry acquisition once. Mtime check must use a portable method (e.g., `find <lockdir> -mmin +2` or a Python one-liner) that works on both macOS and Linux without GNU coreutils.
- AC-1.4: (Design guidance, not a testable AC) The coordination mechanism should minimize overhead — target < 5 seconds beyond venv creation and pip/uv install time.
- AC-1.5: If a waiting server cannot acquire the lock within 120 seconds, it logs an error to stderr and exits with code 1.

### FR-2: Complete Dependency Installation

The venv bootstrap must install ALL dependencies required by ALL 4 servers, not just the deps of whichever server triggers bootstrap first.

**Acceptance Criteria:**
- AC-2.1: A single canonical dependency list is maintained in one location (not duplicated across scripts). This is the source of truth for all bootstrap paths.
- AC-2.2: After bootstrap completes, all packages in the canonical dependency list are importable in the venv Python. The canonical list is defined in the single source file per AC-2.1; verification must use that file, not a hardcoded subset. The canonical list must include both the pip install name and the Python import name for each dependency, since they may differ. Current known deps: `mcp`→`mcp`, `numpy`→`numpy`, `python-dotenv`→`dotenv`, `fastapi`→`fastapi`, `uvicorn`→`uvicorn`, `jinja2`→`jinja2`, `pydantic`→`pydantic`, `pydantic-settings`→`pydantic_settings`.
- AC-2.3: The fast-path (venv exists) must verify that all canonical deps are importable, not just that `bin/python` exists. Run a Python import check against the canonical list. The import check overhead on the fast-path is acceptable (expected < 1 second).
- AC-2.4: If any canonical dep is missing from an existing venv, the server must install all deps from the canonical list before proceeding (self-healing).

### FR-3: Python Version Guard

Bootstrap scripts must verify the Python version before creating a venv or running servers.

**Acceptance Criteria:**
- AC-3.1: If `python3 --version` reports < 3.12, the script exits with a clear error message to stderr and exit code 1.
- AC-3.2: The error message includes the required version and the detected version.

## Non-Requirements (Out of Scope)

- NR-1: Changing the MCP server architecture (e.g., single process serving all 3).
- NR-2: Removing the shared venv approach (all 4 servers continue sharing one venv).
- NR-3: Supporting Python < 3.12 (the guard rejects it, not accommodates it).
- NR-4: Modifying `plugin.json` MCP server configuration structure.

## Design Constraints

- DC-1: Bootstrap scripts must not write to stdout (corrupts MCP stdio protocol). All output to stderr. Exception: `run-ui-server.sh` is browser-facing, not MCP, but should still use stderr for bootstrap diagnostics.
- DC-2: `set -euo pipefail` must remain in all scripts for safety.
- DC-3: The solution must work on macOS and Linux (the two platforms Claude Code supports).
- DC-4: Use `mkdir` as the atomic lock mechanism on all platforms for implementation simplicity. Do not use `flock` even where available.
- DC-5: The canonical bootstrap logic must use `uv` (preferred) with `pip` fallback for all servers, normalizing the current inconsistency where `run-memory-server.sh` uses pip only.

## Verification Strategy

- **Concurrent launch test:** Spawn all 4 bootstrap scripts as background processes with `&`, then `wait` for all. Assert venv exists and all deps importable. Adapt existing reproduction scripts from `agent_sandbox/20260317/rca-mcp-marketplace/`.
- **Stale lock test:** Pre-create a lock directory with an old mtime (>120s), launch a server, assert it detects staleness, removes the lock, and bootstraps successfully.
- **Missing dep test:** Create a venv with only `mcp` installed, launch memory-server, assert it detects missing `numpy` and self-heals by installing all canonical deps.
- **Python version test:** Mock `python3 --version` to report 3.10, assert exit code 1 and error message on stderr.
- **uv-absent fallback test:** Remove `uv` from PATH, launch any server on a fresh install, assert pip fallback is used and bootstrap succeeds with all deps installed.

## Success Criteria

1. Fresh marketplace install: all 4 servers start successfully on first session.
2. Dev workspace: existing venv with all deps installed continues to work without re-bootstrapping (fast-path still applies when deps are present).
3. Concurrent launch: no race conditions or partial venv states.
4. Missing deps: self-healing — server installs missing deps before starting.
5. Python < 3.12: clear error message, no silent failure.

## Design Notes

- The existing "system python3" fallback path is unified to check ALL canonical deps (not per-server subsets). This eliminates the RC-2 dependency gap at the system-python level. The path runs before venv bootstrap and does not participate in the locking protocol.
- The bootstrap path must attempt `uv` first; if `uv` is not available, fall back to `pip`. This check happens once per bootstrap invocation.

## Open Questions

None — all root causes are confirmed via RCA experimentation.
