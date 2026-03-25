# RCA: Entity MCP Server Connection Failure After v4.13.22 Release

**Date:** 2026-03-25
**Severity:** High (blocks MCP client connections for new sessions)
**Status:** Root causes identified, fixes not yet applied

## Problem Statement

After releasing v4.13.22 (feature 062-sqlite-concurrency-defense), new sessions cannot connect to the entity-registry MCP server. The server appears to start but never becomes ready to accept MCP protocol requests.

## Root Causes

### RC-1 (Primary): Synchronous DB writes in lifespan block MCP server startup indefinitely

**Evidence:** The entity server lifespan function (`entity_server.py:74`) runs `backfill_workflow_phases()` which performs raw `db._conn.execute()` INSERT/UPDATE calls (backfill.py:247-267) against 186 entities. When the global entities.db is write-locked by another process, each operation waits up to 15 seconds (`busy_timeout = 15000`). With 186 entities, the lifespan can block for up to 2,790 seconds (46 minutes).

The lifespan is an `async def` function passed to FastMCP, but the backfill calls are synchronous -- they block the asyncio event loop entirely. The MCP server cannot respond to the `initialize` request from the client while the lifespan is blocked, causing a connection timeout.

**Verified by:** Running `backfill_workflow_phases` against the locked DB -- the process hung indefinitely (two test processes had to be killed).

**Contributing factor from 062:** The `busy_timeout` was increased from 5000ms to 15000ms as part of the concurrency defense feature, making the blocking 3x worse than the pre-existing condition.

### RC-2 (Contributing): Multiple entity server instances hold long-lived DB connections

**Evidence:** At time of investigation, four entity_server processes were running simultaneously:
- PID 98845 (v4.13.26, session s000, started 8:52pm) -- 4 DB file descriptors
- PID 32911 (v4.13.26, session s005, started 6:35pm) -- 4 DB file descriptors
- PID 12612 (v4.13.22, orphaned PPID=1) -- 4 DB file descriptors (killed during investigation)
- PID 13309 (v4.13.22, this session s002)

The old-version servers (v4.13.26) hold persistent open connections to the shared entities.db in WAL mode. When one of them has an uncommitted write transaction (even momentarily for autocommit writes), the `BEGIN IMMEDIATE` calls from the new server's backfill fail with "database is locked".

**Verified by:**
```
$ sqlite3 connect + BEGIN IMMEDIATE -> "database is locked"
$ Simple SELECT -> succeeds (reads OK in WAL mode)
```

### RC-3 (Contributing): backfill.py uses raw `db._conn.execute()` bypassing retry and transaction safety

**Evidence:** `backfill.py:224,247,256` access `db._conn` directly for SELECT, UPDATE, and INSERT operations. This violates the encapsulation documented in CLAUDE.md ("Never access `db._conn` directly") and bypasses:
- The `@with_retry` decorator added in feature 062
- The `transaction()` context manager (for atomic BEGIN IMMEDIATE / COMMIT / ROLLBACK)
- Any centralized error handling

Each raw write is an individual autocommit-mode statement that separately contends for the write lock.

### RC-4 (Minor): No venv in new plugin cache version on first session start

**Evidence:** The plugin cache directory `4.13.22` was created at 11:48:31 but had no `.venv` until 11:50:34 (created by manual test). The bootstrap script creates the venv on demand, taking ~500ms with warm uv cache. Three MCP servers compete for the same venv via file-locking; waiters spin-poll with 1-second intervals, adding 1-3 seconds of startup latency. This alone does not cause the connection failure but extends the window during which the MCP client is waiting.

## Hypotheses Considered and Rejected

1. **Import path failure for sqlite_retry.py** -- REJECTED. The module is present at `hooks/lib/sqlite_retry.py` in the cache, and `PYTHONPATH` set by `run-entity-server.sh` includes `hooks/lib`. Import test succeeds.

2. **mcp library version incompatibility** -- REJECTED. Both v4.13.22 and v4.13.26 caches install mcp 1.26.0 with identical FastMCP API usage.

3. **Stale PID file blocking server startup** -- REJECTED. The PID file mechanism (entity_server.py:49-62) only logs a warning when another instance is detected; it does not prevent startup.

## Interaction Effects

RC-1, RC-2, and RC-3 form a causal chain:
- RC-2 provides the condition (DB write-locked by concurrent servers)
- RC-3 provides the mechanism (unprotected raw writes without retry)
- RC-1 provides the impact (lifespan blocks MCP server indefinitely)
- The 062 busy_timeout increase from 5000 to 15000 amplifies the duration

## Reproduction

```bash
# 1. Ensure an old-version entity server is running (holds DB connection)
# 2. Start new entity server from v4.13.22 cache
# 3. The lifespan blocks on backfill_workflow_phases

# Minimal verification:
python -c "
import sqlite3, os
db = os.path.expanduser('~/.claude/pd/entities/entities.db')
conn = sqlite3.connect(db, timeout=5)
conn.execute('BEGIN IMMEDIATE')  # Raises: database is locked
"
```

## Affected Files

| File | Issue |
|------|-------|
| `plugins/pd/hooks/lib/entity_registry/backfill.py:224,247,256` | Raw `db._conn.execute()` bypasses retry/transaction |
| `plugins/pd/mcp/entity_server.py:73-113` | Synchronous blocking in async lifespan |
| `plugins/pd/hooks/lib/entity_registry/database.py:2679` | `busy_timeout = 15000` (3x increase from 5000) |

## Recommended Investigation for Fix

1. Wrap backfill writes in `db.transaction()` context manager and add `@with_retry` (or catch OperationalError with short timeout)
2. Make backfill non-blocking: either run in a thread pool (`asyncio.to_thread`) or make backfill optional/deferred (run after server is accepting connections)
3. Consider reducing `busy_timeout` back to 5000ms or making it configurable
4. Replace raw `db._conn.execute()` calls in backfill.py with public EntityDatabase API methods

## Sandbox Artifacts

- `/Users/terry/projects/pedantic-drip/agent_sandbox/20260325/rca-entity-mcp-connection/reproduction/test_import_from_cache.py`
- `/Users/terry/projects/pedantic-drip/agent_sandbox/20260325/rca-entity-mcp-connection/experiments/hypotheses.md`
- `/Users/terry/projects/pedantic-drip/agent_sandbox/20260325/rca-entity-mcp-connection/experiments/test_h1_bootstrap_timing.sh`
- `/Users/terry/projects/pedantic-drip/agent_sandbox/20260325/rca-entity-mcp-connection/experiments/test_h1_concurrent.sh`
