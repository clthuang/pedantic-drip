# Design: MCP Stale Lock Prevention

## Prior Art Research

### Codebase Patterns
- **PID file management** already exists in `entity_server.py:37-70` and `workflow_state_server.py:69-104` — duplicated `_write_pid()`/`_remove_pid()` using `os.kill(pid, 0)` for stale detection. Gap: never kills live orphans, just logs a warning. `memory_server.py` has no PID management.
- **Bootstrap lock pattern** in `bootstrap-venv.sh:207-267` — uses `mkdir` atomicity + `find -mmin +2` for 2-minute staleness, then rmdir + retry. Only existing stale-lock pattern in codebase.
- **Doctor lock check** in `doctor/checks.py:35-215` — `BEGIN IMMEDIATE` with `busy_timeout=2000ms` to probe lock state. Returns issue with fix hint but cannot identify holder.
- **session-start.sh** runs doctor autofix (10s timeout) + MCP health check (error log). No stale-process cleanup.
- **backfill.py** directly calls `db._conn.execute()` and `db._conn.commit()` at lines 145, 149, 224, 247, 256, 336, 347 — encapsulation violations.
- **sqlite_retry.py** provides `with_retry()` decorator with `is_transient()` matching "locked" OperationalError, backoff (0.1, 0.5, 2.0), max 3 attempts.
- **Degraded mode** in `workflow_state_server.py` is phase-engine level (`meta_json_fallback`), not server-startup DB unavailability.

### External Research
- **os.getppid()** reliably detects orphaning on macOS — returns 1 when reparented to launchd (POSIX standard).
- **PID file best practice**: `os.kill(pid, 0)` with `errno.ESRCH` (no process) vs `errno.EPERM` (access denied) is more reliable than `pid_exists()`.
- **SQLite WAL + BEGIN IMMEDIATE** prevents read-to-write upgrade failures that bypass busy_timeout entirely.
- **SIGTERM→SIGKILL sequence** is industry standard. Python's default SIGTERM handler does NOT trigger `atexit` — need custom handler calling `sys.exit()`.
- **MCP stdio transport**: process IS the session. When Claude Code exits, server's stdin gets EOF. Stale lock prevention must be process-lifecycle, not protocol-level.

## Architecture Overview

### Component Map

```
┌─────────────────────────────────────────────────────────────┐
│                    Session Lifecycle                         │
│                                                             │
│  session-start.sh                                           │
│  ┌─────────────────────────────────────────┐               │
│  │ cleanup_stale_mcp_servers()             │               │
│  │  1. PID file scan (~/.claude/pd/run/)   │               │
│  │  2. lsof fallback (entities.db, memory) │               │
│  │  3. SIGTERM → wait 5s → SIGKILL         │               │
│  └─────────────────────────────────────────┘               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          Shared: server_lifecycle.py                  │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │  │
│  │  │ write_pid()  │ │ remove_pid() │ │ read_pid()   │ │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ │  │
│  │  ┌───────────────────┐ ┌────────────────────────┐   │  │
│  │  │start_parent_       │ │start_lifetime_         │   │  │
│  │  │  watchdog()        │ │  watchdog()            │   │  │
│  │  │ (PPID monitor,    │ │ (max_seconds timer,    │   │  │
│  │  │  10s poll)         │ │  24h default)          │   │  │
│  │  └───────────────────┘ └────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  MCP Servers (all import server_lifecycle)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ entity   │ │ memory   │ │ workflow │ │ UI       │      │
│  │ _server  │ │ _server  │ │ _state   │ │ server   │      │
│  │          │ │          │ │ _server  │ │          │      │
│  │ parent   │ │ parent   │ │ parent   │ │ lifetime │      │
│  │ watchdog │ │ watchdog │ │ watchdog │ │ watchdog │      │
│  │ +degrade │ │          │ │ +degrade │ │ (24h)    │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│                                                             │
│  Backfill (entity_registry/backfill.py)                     │
│  ┌─────────────────────────────────────────┐               │
│  │ db.transaction() with batched commits   │               │
│  │ (max 20 entities per batch)             │               │
│  └─────────────────────────────────────────┘               │
│                                                             │
│  Doctor (doctor/checks.py)                                  │
│  ┌─────────────────────────────────────────┐               │
│  │ Enhanced _test_db_lock() with PID       │               │
│  │ holder identification via PID files +   │               │
│  │ lsof fallback                           │               │
│  └─────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### Defense-in-Depth Strategy

The design uses three independent layers — any one alone reduces orphan lock risk:

1. **Prevention** — Parent-PID watchdog detects orphaning within 15s, triggers clean exit
2. **Cleanup** — Session-start hook kills leftover orphans before new servers start
3. **Resilience** — Degraded mode lets servers start and serve even when DB is locked

### Components

#### 1. `server_lifecycle.py` (NEW — shared module)

Location: `plugins/pd/mcp/server_lifecycle.py`

Consolidates duplicated PID management from entity_server and workflow_state_server, adds watchdog capabilities.

**Functions:**
- `write_pid(server_name: str) -> Path` — Write PID file to `~/.claude/pd/run/{server_name}.pid`
- `remove_pid(server_name: str) -> None` — Remove PID file on clean shutdown
- `read_pid(server_name: str) -> int | None` — Read PID from file, return None if missing/invalid
- `start_parent_watchdog(poll_interval: float = 10.0) -> threading.Thread` — Daemon thread that polls `os.getppid()`, calls `os._exit(0)` when parent changes
- `start_lifetime_watchdog(max_seconds: int = 86400) -> threading.Thread` — Daemon thread that exits after max lifetime

**Design decisions:**
- `os._exit(0)` instead of `sys.exit()` — avoids hanging on MCP event loop cleanup in daemon threads
- Daemon threads (`thread.daemon = True`) — don't prevent process exit
- No `atexit` handler for PID cleanup — unreliable on SIGKILL; session-start cleanup handles stale files
- No external dependencies (psutil) — `os.getppid()` is sufficient on macOS where orphans always get PPID=1

#### 2. Backfill Refactoring (MODIFY — `entity_registry/backfill.py`)

Replace all `db._conn.execute()` / `db._conn.commit()` calls with `db.transaction()` context manager, batching entities in groups of 20.

Two distinct refactoring targets with different structures:

**`run_backfill()` (lines 145-149):** Scanner-based — UPDATE + COMMIT on entity metadata. Wrap in single `db.transaction()` call (typically one entity at a time, no batching needed).

**`backfill_workflow_phases()` (lines 224-347):** Per-entity branching with 3 SQL paths (brainstorm/backlog INSERT OR IGNORE, feature INSERT OR IGNORE, feature UPDATE). Currently collects all work then calls `db._conn.commit()` once at line 347. Refactor: chunk the entity list into batches of 20, wrap each batch in `db.transaction()`, replace `db._conn.execute()` with public API equivalents (`db.insert_workflow_phase()`, `db.update_workflow_phase()`).

**Pattern for `backfill_workflow_phases()`:**
```python
# Before (single commit for all entities):
for entity in entities:
    if brainstorm_or_backlog:
        db._conn.execute("INSERT OR IGNORE INTO workflow_phases ...", ...)
    elif feature:
        db._conn.execute("INSERT OR IGNORE INTO workflow_phases ...", ...)
        db._conn.execute("UPDATE workflow_phases ...", ...)
db._conn.commit()

# After (batched with lock release between batches):
for batch in _chunked(entities, 20):
    with db.transaction():
        for entity in batch:
            if brainstorm_or_backlog:
                db.insert_workflow_phase(...)
            elif feature:
                db.insert_workflow_phase(...)
                db.update_workflow_phase(...)
```

**`db._now_iso()` usage** (lines 250, 262, 334): Out of scope for this refactoring — `_now_iso()` is a lightweight timestamp helper with no lock implications. Acceptable private access.

**Key constraint:** `db.transaction()` is re-entrant (feature 062), so nested calls within public API methods are safe.

#### 3. Session-Start Cleanup (MODIFY — `session-start.sh`)

New function `cleanup_stale_mcp_servers()` called early in session-start, before MCP health checks.

**Algorithm:**
0. If `~/.claude/pd/run/` does not exist, return early (no orphans possible on first-ever session)
1. Scan `~/.claude/pd/run/*.pid` files
2. For each PID file: read PID, check if process exists AND has PPID=1 (orphaned)
3. If orphaned: `kill -TERM $pid`, wait 5s, `kill -9 $pid` if still alive, remove PID file
4. If process not running: remove stale PID file
5. If process alive with real parent: skip (not orphaned)
6. **lsof fallback**: `lsof ~/.claude/pd/entities/entities.db ~/.claude/pd/memory/memory.db 2>/dev/null` — find any Python process with PPID=1 holding these files, kill if not covered by PID files
7. If `lsof` not available: skip with stderr warning

**Ordering:** cleanup runs BEFORE `run_doctor_autofix()` and `check_mcp_health()`.

**Testing:** Integration test: spawn a Python process that writes a PID file, kill its parent (or set PPID=1 via double-fork), verify `cleanup_stale_mcp_servers()` terminates it and removes the PID file. Supplement with manual validation using a deliberately orphaned server process.

#### 4. Degraded Mode Startup (MODIFY — `entity_server.py`, `workflow_state_server.py`)

When DB initialization fails after retries, servers start with `_db = None` and `_db_unavailable = True`.

**Why both servers need this:** `EntityDatabase()` constructor runs migrations (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) which require write access. When the DB is write-locked, the constructor hangs on migration. This affects both entity_server (which additionally runs backfill) and workflow_state_server (which uses EntityDatabase for state queries but whose migration step is the blocking point). Note: workflow_state_server does NOT call backfill — its startup failure mode is strictly the EntityDatabase constructor migration.

**Startup sequence:**
1. Attempt `EntityDatabase()` initialization
2. On `OperationalError` (locked/busy): retry 3 times with 2s backoff
3. If all retries fail: set `_db = None`, `_db_unavailable = True`, start background recovery thread
4. Register all tools normally — they check `_db_unavailable` and return structured error
5. Background thread: retry DB init every 30s; on success, set `_db = new_db`, `_db_unavailable = False`

**Flag naming:** `_db_unavailable` (not `degraded`) to avoid confusion with workflow_state_server's existing `degraded` flag for meta_json_fallback.

#### 5. Doctor Enhancement (MODIFY — `doctor/checks.py`)

Enhance `_test_db_lock()` to identify lock holders when a lock is detected.

**Algorithm:**
1. Existing: `BEGIN IMMEDIATE` with `busy_timeout=2000ms` to detect lock
2. New on lock detected: scan `~/.claude/pd/run/*.pid` for running processes
3. New: attempt `lsof` on DB path to find holders
4. Include holder PID + process info in Issue message
5. Fallback message if holder unknown: "lock holder unknown — check ~/.claude/pd/run/"

#### 6. Server Integration (MODIFY — all 4 servers)

Each server's `lifespan()` function updated to use `server_lifecycle`:

| Server | write_pid | remove_pid | parent_watchdog | lifetime_watchdog | degraded_mode |
|--------|-----------|------------|-----------------|-------------------|---------------|
| entity_server | Yes (migrate from local) | Yes (migrate) | Yes (new) | No | Yes (new) |
| memory_server | Yes (new) | Yes (new) | Yes (new) | No | No |
| workflow_state_server | Yes (migrate from local) | Yes (migrate) | Yes (new) | No | Yes (new) |
| UI server (`__main__.py`) | Yes (new, before `uvicorn.run()`) | Yes (new, via `atexit`) | No | Yes (24h, new) | No |

## Technical Decisions

### TD-1: `os._exit(0)` in watchdog vs `sys.exit()`
**Decision:** Use `os._exit(0)` in the watchdog daemon thread.
**Rationale:** `sys.exit()` only raises `SystemExit` in the calling thread — in a daemon thread this won't terminate the process. `os._exit(0)` terminates immediately. The MCP server's finally block won't run, but PID file cleanup is handled by session-start anyway.
**Trade-off:** Skip finally blocks → acceptable because session-start cleanup handles stale PID files.
**SQLite safety:** SQLite handles process-exit cleanup safely via WAL recovery on next open. The unclosed connection does not corrupt the database or leave permanent locks — the OS releases file locks on process termination, and WAL checkpointing recovers any in-progress transactions.

### TD-2: No psutil dependency
**Decision:** Use only `os.getppid()` for orphan detection, no psutil.
**Rationale:** On macOS Darwin 25.x, orphaned processes are always reparented to launchd (PID 1). `os.getppid() != initial_ppid` is sufficient and avoids adding a dependency. The PID-reuse race (a different process gets the original parent PID) is negligible — Claude Code PIDs are ephemeral and the 10s poll window makes collision near-impossible.

### TD-3: Batch size of 20 for backfill
**Decision:** 20 entities per transaction batch.
**Rationale:** Balances lock hold time (~1-5ms per batch at SQLite speeds) against total backfill overhead. With typical entity counts (50-200), this means 3-10 batches — each releasing the write lock between batches so other processes can acquire it.

### TD-4: SIGTERM → 5s → SIGKILL escalation
**Decision:** Session-start sends SIGTERM, waits 5s, then SIGKILL if process persists.
**Rationale:** SIGTERM allows Python cleanup (finally blocks, PID file removal). 5s is generous for an MCP server shutdown. SIGKILL is the last resort for hung processes. This matches MCP spec's recommended shutdown sequence.

### TD-5: lsof as fallback, not primary
**Decision:** PID files are the primary cleanup mechanism; lsof is a safety net.
**Rationale:** PID file scan is fast and deterministic. lsof may not be available on all systems (unlikely on macOS but defensive). lsof catches processes that crashed before writing PID files or were started by older versions without PID management.

### TD-6: Background recovery thread interval (30s)
**Decision:** Recovery thread polls every 30s for DB availability.
**Rationale:** 30s balances responsiveness against wasted work. Typical lock-holder scenarios resolve in seconds (session-start cleanup) or minutes (manual intervention). For testing, the interval is injectable (mock to 1s).

### TD-7: CPython GIL for `_db` pointer swap
**Decision:** Rely on GIL for atomic `_db = new_value` assignment in recovery thread.
**Rationale:** CPython GIL guarantees single-bytecode-instruction atomicity. `_db = value` is a single `STORE_NAME` instruction. Spec notes PEP 703 (free-threaded Python) would require `threading.Lock` — acceptable since PEP 703 is experimental and pd targets standard CPython.

### TD-8: UI server uses lifetime watchdog, not parent watchdog
**Decision:** UI server gets `start_lifetime_watchdog(86400)` only, no parent watchdog.
**Rationale:** UI server is launched via `nohup ... & disown` — PPID is immediately 1. Parent watchdog would cause immediate exit. 24h lifetime ensures DB connections are released daily; session-start restarts it.

## Risks

### R-1: Race between session-start cleanup and MCP server startup
**Risk:** Session-start kills an orphan right as a new MCP server reads the same PID file.
**Mitigation:** PID file is removed after kill. New servers write their own PID file on startup. The race window is <1s and the worst case is a harmless "PID file not found" log.
**Severity:** Low

### R-2: Watchdog false positive on system sleep/resume
**Risk:** macOS sleep could cause `os.getppid()` to briefly return unexpected values on wake.
**Mitigation:** `os.getppid()` is a kernel call that returns the correct value regardless of sleep state. The parent PID doesn't change during sleep — if the parent died during sleep, PPID=1 is correct (we should exit). No known false positive risk.
**Severity:** Low

### R-3: Backfill partial completion on lock contention
**Risk:** If lock contention occurs mid-backfill, some batches succeed and others fail.
**Mitigation:** Backfill operations are idempotent (INSERT OR IGNORE, UPDATE with WHERE clauses). Partial completion is safe — next startup completes remaining batches.
**Severity:** Low

### R-4: Degraded mode tool calls during recovery
**Risk:** A tool call arrives exactly when the recovery thread is swapping `_db`.
**Mitigation:** GIL guarantees atomic pointer swap. Tool reads `_db` reference once at call start. Either it sees None (returns error) or sees the new DB (succeeds). No torn read possible under GIL.
**Severity:** Low

## Interfaces

### `server_lifecycle.py` API

```python
"""Shared MCP server lifecycle utilities.

Provides PID file management and watchdog threads for all pd MCP servers.
"""

import os
import threading
from pathlib import Path

PID_DIR = Path(os.path.expanduser("~/.claude/pd/run"))

def write_pid(server_name: str) -> Path:
    """Write current process PID to ~/.claude/pd/run/{server_name}.pid.

    Creates PID_DIR if needed. If a PID file already exists:
    - If the PID is not running: overwrites (stale file)
    - If the PID is running: logs warning, overwrites anyway (we're the new instance)

    Args:
        server_name: One of "entity_server", "memory_server",
                     "workflow_state_server", "ui_server"

    Returns:
        Path to the written PID file
    """
    ...

def remove_pid(server_name: str) -> None:
    """Remove PID file for the given server. No-op if file missing."""
    ...

def read_pid(server_name: str) -> int | None:
    """Read PID from file. Returns None if file missing or content invalid."""
    ...

def start_parent_watchdog(
    poll_interval: float = 10.0,
    _exit_fn: callable = os._exit,
) -> threading.Thread:
    """Start daemon thread that monitors parent PID.

    Records os.getppid() at call time. Polls every poll_interval seconds.
    When parent PID changes (orphaned), calls _exit_fn(0).

    Args:
        poll_interval: Seconds between checks (default 10.0)
        _exit_fn: Exit function, injectable for testing (default os._exit)

    Returns:
        The started daemon thread
    """
    ...

def start_lifetime_watchdog(
    max_seconds: int = 86400,
    _exit_fn: callable = os._exit,
) -> threading.Thread:
    """Start daemon thread that exits after max_seconds.

    Args:
        max_seconds: Maximum lifetime in seconds (default 86400 = 24h)
        _exit_fn: Exit function, injectable for testing (default os._exit)

    Returns:
        The started daemon thread
    """
    ...
```

### Degraded Mode Interface (entity_server, workflow_state_server)

```python
# Module-level state
_db: EntityDatabase | None = None
_db_unavailable: bool = False
_recovery_thread: threading.Thread | None = None

def _init_db_with_retry(
    db_path: str,
    max_retries: int = 3,
    backoff_base: float = 2.0,
) -> EntityDatabase | None:
    """Attempt DB initialization with retries.

    Args:
        db_path: Path to SQLite database
        max_retries: Number of retry attempts
        backoff_base: Base seconds for exponential backoff

    Returns:
        EntityDatabase instance, or None if all retries failed
    """
    ...

def _start_recovery_thread(
    db_path: str,
    poll_interval: float = 30.0,
) -> threading.Thread:
    """Start daemon thread that retries DB initialization.

    On success: sets _db to new instance, sets _db_unavailable = False.
    Thread exits after successful recovery.

    Args:
        db_path: Path to SQLite database
        poll_interval: Seconds between retry attempts (injectable for testing)

    Returns:
        The started daemon thread
    """
    ...

# Tool handler pattern:
def handle_tool_call():
    """Pattern for tool handlers in degraded mode."""
    if _db_unavailable:
        return {"error": "database temporarily unavailable"}
    # ... normal tool logic using _db ...
```

### Backfill Batch Interface

```python
def _chunked(iterable, size: int):
    """Yield successive chunks of `size` from iterable."""
    ...

# Pattern used in backfill_workflow_phases():
def backfill_workflow_phases_batched(db: EntityDatabase, entities: list, batch_size: int = 20):
    """Process workflow phase backfill in batched transactions.

    Each batch commits independently. Lock is released between batches,
    allowing other processes to acquire it.
    """
    for batch in _chunked(entities, batch_size):
        with db.transaction():
            for entity in batch:
                # Use public API: db.insert_workflow_phase(), db.update_workflow_phase()
                if is_brainstorm_or_backlog(entity):
                    db.insert_workflow_phase(entity_type_id, ...)
                elif is_feature(entity):
                    db.insert_workflow_phase(entity_type_id, ...)
                    db.update_workflow_phase(entity_type_id, ...)

# Pattern used in run_backfill() (line 145-149):
# Single entity UPDATE — wrap in db.transaction() directly
with db.transaction():
    db.update_entity(entity_type_id, ...)  # replaces db._conn.execute("UPDATE ...")
```

### Session-Start Cleanup Interface

```bash
# In session-start.sh:

cleanup_stale_mcp_servers() {
    # 1. PID file scan
    local pid_dir="$HOME/.claude/pd/run"
    # For each *.pid file:
    #   - Read PID
    #   - Check if running: kill -0 $pid 2>/dev/null
    #   - If running, check if orphaned: ps -o ppid= -p $pid → PPID=1?
    #   - If orphaned: kill -TERM, sleep 5, kill -9 if needed, rm pid file
    #   - If not running: rm stale pid file

    # 2. lsof fallback
    # lsof ~/.claude/pd/entities/entities.db ~/.claude/pd/memory/memory.db
    # Find Python processes with PPID=1 not covered by PID files
    # Kill with same SIGTERM→SIGKILL pattern

    # 3. lsof unavailable: skip with stderr warning
}
```

### Doctor Lock Diagnostic Interface

```python
def _identify_lock_holders(db_path: str) -> list[str]:
    """Identify processes holding the DB lock.

    Checks:
    1. PID files in ~/.claude/pd/run/
    2. lsof on db_path (if available)

    Returns:
        List of holder descriptions: ["PID 1234 (entity_server, PPID=1)", ...]
        Empty list if no holders found.
    """
    ...

# Enhanced issue message:
# "entities.db write lock held by PID 1234 (entity_server, orphaned)"
# or: "entities.db write lock held — holder unknown, check ~/.claude/pd/run/"
```

## File Change Summary

| File | Action | Description |
|------|--------|-------------|
| `plugins/pd/mcp/server_lifecycle.py` | CREATE | Shared lifecycle module |
| `plugins/pd/mcp/test_server_lifecycle.py` | CREATE | Unit tests for lifecycle module |
| `plugins/pd/mcp/entity_server.py` | MODIFY | Remove local PID functions, add watchdog + degraded mode |
| `plugins/pd/mcp/workflow_state_server.py` | MODIFY | Remove local PID functions, add watchdog + degraded mode |
| `plugins/pd/mcp/memory_server.py` | MODIFY | Add PID management + parent watchdog |
| `plugins/pd/ui/__main__.py` | MODIFY | Add PID management + lifetime watchdog (call before `uvicorn.run()`, cleanup via `atexit.register()` since uvicorn handles SIGTERM gracefully) |
| `plugins/pd/hooks/lib/entity_registry/backfill.py` | MODIFY | Replace db._conn with db.transaction() batches |
| `plugins/pd/hooks/session-start.sh` | MODIFY | Add cleanup_stale_mcp_servers() |
| `plugins/pd/hooks/lib/doctor/checks.py` | MODIFY | Enhance lock diagnostic with holder ID |
