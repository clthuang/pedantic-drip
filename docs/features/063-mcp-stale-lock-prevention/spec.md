# Specification: MCP Stale Lock Prevention

## Background
Identified during feature 062 adversarial audit and confirmed by RCA (`docs/rca/20260325-entity-mcp-connection-failure.md`). Stale PID 1675 (UI server) held `entities.db` write lock for 2+ days, blocking all new entity_server instances. RCA at `docs/rca/20260325-160500-entity-registry-mcp-connection-failure.md` confirmed 7 processes holding the DB simultaneously.

## Problem Statement
Orphaned/stale MCP server processes hold permanent write locks on `~/.claude/pd/entities/entities.db`, blocking new entity_server instances from starting — the server's lifespan backfill requires writes and hangs indefinitely when locked, preventing tool registration.

## Success Criteria
- [ ] Backfill operations use `db.transaction()` with batched commits of max 20 entities per batch (no raw `db._conn.execute()`)
- [ ] 3 MCP servers (entity, memory, workflow) have parent-PID watchdog — exit within 15s of parent death (10s poll interval + 5s exit overhead)
- [ ] UI server has max-lifetime watchdog (24h) since it's intentionally detached via `nohup ... & disown`
- [ ] All 4 server processes write PID files to `~/.claude/pd/run/` with naming: `{entity_server,memory_server,workflow_state_server,ui_server}.pid`
- [ ] Session-start hook kills orphaned MCP servers (PPID=1) via PID files + lsof fallback
- [ ] Entity server and workflow_state_server start in degraded mode when DB is locked — tools register, return structured errors, recover automatically
- [ ] Doctor lock diagnostic includes PID holder info

## Scope

### In Scope
- Refactor `entity_registry/backfill.py` to use `db.transaction()` with batched commits instead of raw `db._conn.execute()`. Note: `semantic_memory/backfill.py` is out of scope — memory_server does not do startup backfill so the lock risk is lower.
- Add parent-PID watchdog daemon thread to entity_server, memory_server, workflow_state_server
- Add max-lifetime watchdog (24h) to UI server (separate from parent-PID — UI server is intentionally detached)
- Add PID file management to memory_server (missing) and UI server (missing)
- Create shared `plugins/pd/mcp/server_lifecycle.py` module with `start_parent_watchdog()`, `start_lifetime_watchdog()`, `write_pid()`, `remove_pid()`
- Add `cleanup_stale_mcp_servers()` to session-start.sh with PID-file + lsof fallback
- Add retry + degraded mode to entity_server and workflow_state_server DB initialization
- Add background recovery thread for degraded-mode servers
- Enhance doctor `_test_db_lock()` to include PID holder info

### Out of Scope
- Per-session or per-project DB isolation (architectural change too large)
- Connection pooling
- Doctor auto-fix for locks (redundant with session-start cleanup)
- Changing Claude Code's process management behavior

## Acceptance Criteria

### Backfill Concurrency Safety
- Given `backfill_workflow_phases()` is called during entity server startup
- When another process holds a write lock on entities.db
- Then backfill completes with partial success (retries between batches) instead of hanging
- And no raw `db._conn.execute()` calls remain in `entity_registry/backfill.py` — verified by `grep -n 'db._conn.execute' plugins/pd/hooks/lib/entity_registry/backfill.py` returning zero matches
- And each batch commits independently with max 20 entities per batch, transaction released between batches (verifiable by code inspection and unit test asserting batch size <= 20)

### Parent-PID Watchdog (entity, memory, workflow servers)
- Given an MCP server process whose parent (Claude Code) has terminated
- When the parent PID changes (orphaned, reparented to PID 1 on macOS/launchd)
- Then the server detects the change within 15s (10s poll interval + overhead) and exits cleanly via `os._exit(0)`
- And entity_server, memory_server, workflow_state_server all have the watchdog
- Note: On macOS Darwin 25.x, orphaned processes are reparented to launchd (PID 1). The watchdog checks `os.getppid() != initial_parent_pid`.

### UI Server Lifetime Watchdog
- Given the UI server is launched via `nohup ... & disown` (intentionally detached, PPID=1 immediately)
- When the server has been running for 24 hours
- Then it exits cleanly, freeing its DB connection
- And the next session-start hook restarts it fresh
- Note: Parent-PID watchdog is NOT used for UI server (would cause immediate exit since PPID is always 1 after disown)

### PID File Management
- Given any server process starts
- When it writes its PID file to `~/.claude/pd/run/{server_name}.pid`
- Then the PID file contains the correct process ID
- And the PID file is removed in the server's finally/cleanup block. Note: On unclean termination (SIGKILL), PID files will be stale — this is expected and handled by session-start cleanup (no atexit handlers needed).
- And PID file naming follows: `entity_server.pid`, `memory_server.pid`, `workflow_state_server.pid`, `ui_server.pid`

### Session-Start Stale Process Cleanup
- Given stale MCP server PID files exist in `~/.claude/pd/run/`
- When a new Claude Code session starts (session-start.sh runs)
- Then orphaned processes (PPID=1) are killed and their PID files removed
- And non-orphaned processes (PPID matches a live Claude Code parent) are NOT killed
- And a lsof fallback kills any Python process holding entities.db or memory.db whose PPID=1, regardless of PID file presence (workflow_state_server shares entities.db, covered by this scan)
- And if lsof is not available, the fallback step is skipped with a stderr warning (PID-file cleanup still operates)

### Non-Blocking Server Startup (entity_server + workflow_state_server)
- Given the entities.db write lock is held by another process
- When entity_server or workflow_state_server starts and cannot initialize EntityDatabase after 3 retries (2s backoff each)
- Then the server starts in degraded mode — tools are registered and visible in Claude Code
- And write tools return `{"error": "database temporarily unavailable"}` (structured JSON, not crash). All tools that call EntityDatabase write methods (register_entity, update_entity, delete_entity, add_dependency, etc.) return the error. Read-only tools (get_entity, search_entities, get_lineage) that don't require `_db` write access may still operate if the connection exists for reads, or return the same error if `_db is None`.
- And a background recovery thread retries DB initialization every 30s
- And recovery occurs on the next successful retry after the lock clears (for testing: mock sleep interval to 1s, verify recovery within 2 poll intervals)
- Thread safety: CPython GIL guarantees atomic `_db = new_value` pointer swap. If free-threaded Python (PEP 703) is adopted, a `threading.Lock` would be needed.
- Note: workflow_state_server already uses "degraded" for meta_json_fallback (different meaning). Use a distinct flag name (e.g., `_db_unavailable`) for DB-lock degraded mode to avoid confusion.

### Shared Server Lifecycle Module
- Given `plugins/pd/mcp/server_lifecycle.py` exists
- When imported by any of the 4 servers
- Then `start_parent_watchdog()`, `start_lifetime_watchdog()`, `write_pid()`, `remove_pid()` are each callable
- And each function has at least one unit test

### Doctor Lock Diagnostic Enhancement
- Given entities.db is write-locked
- When `pd doctor` runs the `db_readiness` check
- Then the issue message includes the PID of the lock holder (from `~/.claude/pd/run/*.pid` files and/or lsof). If holder PID cannot be determined, message includes "lock holder unknown — check ~/.claude/pd/run/ for stale PID files or run: lsof ~/.claude/pd/entities/entities.db"

## Feasibility Assessment

### Assessment
**Overall:** Confirmed
**Reasoning:** All proposed fixes use standard POSIX mechanisms (`os.getppid()`, PID files, `lsof`, daemon threads). The backfill refactoring uses existing `db.transaction()` infrastructure from feature 062. Non-blocking startup is a standard pattern (retry + degraded mode).
**Key Assumptions:**
- `os.getppid()` reliably detects orphaning on macOS — Status: Verified (POSIX standard, returns 1 when reparented to launchd on macOS Darwin 25.x)
- CPython GIL makes `_db = new_value` assignment atomic — Status: Verified (single pointer swap is GIL-atomic; note PEP 703 constraint for future)
- EntityDatabase migrations are idempotent — Status: Verified (all use CREATE TABLE IF NOT EXISTS)
- `backfill.py` 3-way branching can use `db.transaction()` per branch — Status: Verified (transaction() is re-entrant per feature 062)

## Dependencies
- Feature 062 (sqlite-concurrency-defense) — provides `transaction()` re-entrancy and `sqlite_retry.py` shared module (completed)

## Open Questions
- None — all resolved during planning and adversarial review
