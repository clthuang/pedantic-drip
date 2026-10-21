# Design: MCP Bootstrap Python Discovery and Silent Failure

**Feature:** 042-mcp-bootstrap-python-discovery
**Spec:** [spec.md](spec.md)

## Prior Art Research

### Codebase Patterns
- **bootstrap-venv.sh**: Uses bare `python3` for version check and venv creation. `uv venv`/`uv pip install` preferred over python3-m-venv/pip. All output to stderr (MCP stdio safety). Sentinel at `${venv_dir}/.bootstrap-complete`.
- **doctor.sh**: Threshold at 3.10 using bash arithmetic. `check_python3()` reusable via sourcing.
- **meta-json-guard.sh**: JSONL logging to `~/.claude/iflow/meta-json-guard.log` (append-only, no rotation). Sentinel check via glob `ls *.bootstrap-complete`.
- **session-start.sh**: First-run detection checks `.venv` existence and `~/.claude/iflow/memory`. Has `gtimeout`/`timeout` discovery pattern. Python resolver pattern: prefer venv python, fallback to system python3.
- **test_bootstrap_venv.sh**: Existing mock python3 pattern creates stub scripts in `$MOCK_DIR`, overrides PATH.

### External Findings
- **`uv python find`**: uv exposes a command that applies its full resolution algorithm and returns the interpreter path. Correct syntax: `uv python find --system '>=3.12' 2>/dev/null` — returns absolute path on stdout. The `--system` flag skips virtual environments, discovering only system-installed interpreters (important for bootstrap where we're creating a new venv).
- **MCP error handling**: stdout is strictly JSON-RPC. All diagnostics must go to stderr. Fatal startup failures should exit 1 with clear stderr message.
- **macOS Python pitfall**: `/usr/bin/python3` is often a stub that prompts Xcode CLT install. Homebrew paths (`/opt/homebrew/bin`, `/usr/local/bin`) should be checked first.

## Architecture Overview

### Design Decision: Two-Tier Python Discovery

**Decision:** Use `uv python find` as primary discovery when uv is available, fall back to manual PATH search when uv is not installed.

**Rationale:**
- uv is already the preferred tool in bootstrap-venv.sh (used for venv creation and dep install)
- `uv python find` handles pyenv, asdf, mise, Homebrew, system Python — more robust than hardcoded paths
- Manual fallback ensures the feature works even without uv (though uv is the happy path)
- Avoids reinventing interpreter resolution that uv already does well

**Trade-off:** Adds a dependency on uv's `python find` subcommand availability. If uv changes this interface, we'd need to update. Acceptable because: (a) uv is already a dependency, (b) `python find` is a stable subcommand, (c) manual fallback exists.

### Components

```
┌─────────────────────────────────────────────────────────┐
│                  bootstrap-venv.sh                       │
│                                                          │
│  ┌──────────────────┐   ┌─────────────────────────────┐ │
│  │ discover_python() │   │ log_bootstrap_error()       │ │
│  │                   │   │                             │ │
│  │ 1. uv python find │   │ Write JSONL to              │ │
│  │ 2. Manual search  │   │ ~/.claude/iflow/            │ │
│  │ 3. Bare python3   │   │   mcp-bootstrap-errors.log  │ │
│  │                   │   │                             │ │
│  │ Exports:          │   │ Called on any fatal error    │ │
│  │   PYTHON_FOR_VENV │   │ before exit 1               │ │
│  └──────────────────┘   └─────────────────────────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │ write_sentinel()                                     ││
│  │ Writes interpreter path:version to sentinel file     ││
│  └──────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                  session-start.sh                         │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │ check_mcp_health()                                   ││
│  │ Reads mcp-bootstrap-errors.log for recent errors     ││
│  │ Returns warning text or empty string                 ││
│  │ Truncates entries > 1 hour                           ││
│  └──────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                  meta-json-guard.sh                       │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │ check_mcp_available() (enhanced)                     ││
│  │ Reads sentinel content, validates interpreter        ││
│  │ Fallback: mtime check for legacy empty sentinels     ││
│  └──────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                  doctor.sh                                │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │ check_python3() (updated threshold)                  ││
│  │ Minimum version: 3.10 → 3.12                        ││
│  └──────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

### Technical Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| TD-1 | Use `uv python find` as primary discovery | Already a dependency; handles pyenv/asdf/mise/Homebrew natively |
| TD-2 | Manual fallback searches `/opt/homebrew/bin` then `/usr/local/bin` | Covers macOS Apple Silicon and Intel Homebrew paths |
| TD-3 | Error log at `~/.claude/iflow/mcp-bootstrap-errors.log` | Follows existing log path convention (`~/.claude/iflow/`) |
| TD-4 | Session-start truncates error log on every invocation | Simple rotation; no separate cron/cleanup needed |
| TD-5 | Sentinel file stores `<interpreter_path>:<version>` | Enables stale detection without separate metadata file |
| TD-6 | Bash 3.2 compatibility maintained | macOS ships Bash 3.2; bootstrap-venv.sh header states this |

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `uv python find` interface changes | Low | Manual fallback as safety net; uv is stable |
| Sentinel format change breaks old sentinels | Low | Legacy (empty) sentinel handled via mtime fallback |
| Error log concurrent writes | Low | JSONL lines < PIPE_BUF; atomic on POSIX |
| Python upgrade between sessions with stale sentinel | Medium | Sentinel stores interpreter path+version; guard validates |

## Interface Design

### `discover_python()` — bootstrap-venv.sh

```bash
# Discovers a Python >= 3.12 interpreter and sets PYTHON_FOR_VENV (module-level variable).
# Search order:
#   1. uv python find --system '>=3.12' 2>/dev/null (if uv available)
#   2. python3.14, python3.13, python3.12 in /opt/homebrew/bin
#   3. python3.14, python3.13, python3.12 in /usr/local/bin
#   4. Bare python3 from PATH
# For each candidate (tiers 2-4), verify version >= 3.12 via:
#   $candidate -c "import sys; print('{0}.{1}'.format(...))" and bash arithmetic check.
# On failure: calls log_bootstrap_error() and exits 1.
# On success: sets PYTHON_FOR_VENV=<absolute path>
#
# Arguments: none
# Sets: PYTHON_FOR_VENV (module-level, NOT exported — only used within bootstrap-venv.sh)
# Side effects: may call log_bootstrap_error() on failure
# Requires: SERVER_NAME must be set before calling (for error logging)
discover_python()
```

**Note on PYTHON_FOR_VENV vs PYTHON:** `PYTHON_FOR_VENV` is a module-level variable used only during bootstrap (for venv creation and system-python check). `PYTHON` remains the final exported variable for server scripts — set to either `$PYTHON_FOR_VENV` (system python path) or `$venv_dir/bin/python` (venv python) by `bootstrap_venv()`.

**Replaces:** `check_python_version()` (deleted entirely)

**Callers:** `bootstrap_venv()` Step 1 (was `check_python_version`). Called BEFORE the fast-path checks (Step 2 system python, Step 3 venv fast-path) so `PYTHON_FOR_VENV` is always available for sentinel writes.

**Downstream updates:**
- `check_system_python()`: `check_venv_deps python3` → `check_venv_deps "$PYTHON_FOR_VENV"`. Also: `export PYTHON=python3` → `export PYTHON="$PYTHON_FOR_VENV"`. When system python path succeeds, call `write_sentinel "$sentinel" "$PYTHON_FOR_VENV"` to signal MCP availability to meta-json-guard (sentinel written even without venv).
- `create_venv()`: `python3 -m venv` → `"$PYTHON_FOR_VENV" -m venv`; `uv venv "$venv_dir"` → `uv venv --python "$PYTHON_FOR_VENV" "$venv_dir"`
- Sentinel recovery path (Step 3 fast-path): `touch "$sentinel"` → `write_sentinel "$sentinel" "$PYTHON_FOR_VENV"` (safe because `discover_python()` now runs first)

### `log_bootstrap_error()` — bootstrap-venv.sh

```bash
# Writes a JSONL error entry to ~/.claude/iflow/mcp-bootstrap-errors.log
# Called before exit 1 on any fatal bootstrap error.
# All output to stderr (MCP stdio safety).
#
# Arguments:
#   $1 - server_name: which server failed (e.g., "memory-server", "entity-registry", "workflow-engine")
#   $2 - error_type: one of "python_version", "venv_creation", "dep_install", "lock_timeout"
#   $3 - message: human-readable error description
#   $4 - extra_json: optional additional JSON fields (e.g., '"found":"3.9","required":"3.12"')
#                    Callers are few and controlled (3 callsites in bootstrap_venv + discover_python).
#                    Format: pre-escaped key:value pairs separated by commas.
#
# Log entry format (JSONL):
#   {"timestamp":"2026-03-18T12:00:00Z","server":"memory-server","error":"python_version",
#    "message":"...","found":"3.9","required":"3.12","searched":[...]}
#
# Server name values: "memory-server", "entity-registry", "workflow-engine"
# (matching the server identifiers passed to bootstrap_venv() from run-*.sh)
log_bootstrap_error()
```

### `write_sentinel()` — bootstrap-venv.sh

```bash
# Writes the sentinel file with interpreter metadata.
# Format: <absolute_path>:<major.minor>
# Example: /opt/homebrew/bin/python3.13:3.13
#
# Arguments:
#   $1 - sentinel_path: path to the sentinel file
#   $2 - python_path: absolute path to the Python interpreter used
#
# Replaces all existing `touch "$sentinel"` calls.
write_sentinel()
```

### `check_mcp_health()` — session-start.sh

```bash
# Reads ~/.claude/iflow/mcp-bootstrap-errors.log for entries < 10 minutes old.
# Returns warning text (prepended to additionalContext) or empty string.
# Truncates entries > 1 hour from the log file on every invocation.
#
# Timestamp parsing: uses BSD date on macOS:
#   date -jf '%Y-%m-%dT%H:%M:%SZ' "$ts" +%s
# Falls back to Python one-liner if BSD date fails (Linux compat):
#   python3 -c "from datetime import datetime; print(int(datetime.fromisoformat('$ts'.replace('Z','+00:00')).timestamp()))"
#
# Truncation mechanism: while-read loop filters entries by timestamp,
# writes recent entries to a temp file, then mv (atomic rename) replaces the log.
# Runs on every invocation regardless of whether errors were found.
#
# Arguments: none
# Returns: warning text via stdout, or empty string
# Side effects: truncates old entries from the log file
check_mcp_health()
```

**Called from:** `main()` before `build_context()`, result prepended to `full_context`.

### `check_mcp_available()` (enhanced) — meta-json-guard.sh

```bash
# Enhanced sentinel validation. Current behavior:
#   ls ~/.claude/plugins/cache/*/iflow*/*/.venv/.bootstrap-complete
#
# New behavior:
#   1. Find sentinel via existing glob
#   2. Read sentinel content (format: <path>:<version>)
#   3. If content present:
#      a. Check interpreter path exists: [ -x "$path" ]
#      b. Check version >= 3.12: parse major.minor from sentinel content,
#         compare with bash arithmetic (same pattern as doctor.sh — no Python process spawn)
#      c. Both OK → return 0; either fails → return 1
#   4. If content empty (legacy): check mtime < 24h via find -mmin -1440
#   5. If no sentinel: return 1 (MCP unavailable)
#
# Returns: 0 if MCP available, 1 if unavailable
check_mcp_available()
```

### `check_python3()` (updated) — doctor.sh

```bash
# Existing function, only threshold change:
#   (( major < 3 || (major == 3 && minor < 10) ))
# becomes:
#   (( major < 3 || (major == 3 && minor < 12) ))
# Error message: "python3 version ${version} < 3.12 required"
check_python3()
```

### Data Flow

```
Session start:
  main()
    ├── check_mcp_health() → reads error log → returns warning or ""
    ├── check first-run (moved earlier) → returns setup prompt or ""
    ├── prepend warnings to full_context
    └── build_context() → build_memory_context() → output JSON

MCP server launch (per server):
  run-*.sh
    └── bootstrap_venv()
          ├── Step 1: discover_python() → sets PYTHON_FOR_VENV
          │     ├── uv python find --system '>=3.12' (if uv available)
          │     ├── manual search (/opt/homebrew/bin, /usr/local/bin)
          │     └── bare python3 fallback
          │     └── (on failure) log_bootstrap_error(SERVER_NAME, ...) → exit 1
          ├── Step 2: check_system_python() → uses PYTHON_FOR_VENV
          │     └── (on success) write_sentinel() + export PYTHON → return 0
          ├── Step 3: venv fast-path → check deps importable
          │     └── (on success) write_sentinel() + export PYTHON → return 0
          ├── Step 4: locked bootstrap
          │     ├── create_venv() → uses PYTHON_FOR_VENV
          │     ├── install_all_deps()
          │     └── write_sentinel() → writes path:version

Hook (meta-json-guard):
  check_mcp_available()
    ├── find sentinel via glob
    ├── read content → parse path:version
    ├── verify interpreter exists + version OK → return 0
    ├── legacy empty sentinel → check mtime → return 0 or 1
    └── no sentinel → return 1
```

### File Change Summary

| File | Changes |
|------|---------|
| `plugins/iflow/mcp/bootstrap-venv.sh` | Replace `check_python_version()` with `discover_python()`. Add `log_bootstrap_error()`, `write_sentinel()`. Update `check_system_python()`, `create_venv()` to use `$PYTHON_FOR_VENV`. Replace `touch "$sentinel"` calls with `write_sentinel()`. |
| `plugins/iflow/scripts/doctor.sh` | Change version threshold in `check_python3()` from 3.10 to 3.12. Update error message. |
| `plugins/iflow/hooks/session-start.sh` | Add `check_mcp_health()`. Move first-run detection earlier in `main()`. Call `check_mcp_health()` before `build_context()`. |
| `plugins/iflow/hooks/meta-json-guard.sh` | Enhance `check_mcp_available()` to read sentinel content, validate interpreter, handle legacy sentinels. |
