# Specification: SQLite Concurrency Defense

## Problem Statement
SQLite databases shared across multiple MCP server processes suffer write contention that causes silent partial commits — entity server and memory server lack retry coverage, cascade operations use split-commit patterns, and busy_timeout values are inconsistent across DB modules.

## Success Criteria
- [ ] `with_retry` decorator with `is_transient` predicate extracted into shared module at `plugins/pd/hooks/lib/sqlite_retry.py` (public API — no underscore prefix)
- [ ] Entity server MCP handlers wrapped with `with_retry` (parity with workflow state server)
- [ ] Memory server MCP handlers wrapped with `with_retry` (parity with workflow state server)
- [ ] `_run_cascade()` Phase B operations (`cascade_unblock` + `rollup_parent`) atomic within a single `transaction()` block
- [ ] Multi-step writes in `EntityDatabase` that issue sequential `_commit()` calls outside `BEGIN IMMEDIATE` identified and wrapped in `transaction()`
- [ ] `busy_timeout` standardized to 15000ms across all database modules (entity, memory, workflow)
- [ ] Concurrent-write integration tests validate retry under multi-process contention
- [ ] All existing test suites pass (entity registry 940+, workflow engine 309, memory server, UI)

## Scope

### In Scope
- Extract `_with_retry` and `_is_transient` from `workflow_state_server.py` into `plugins/pd/hooks/lib/sqlite_retry.py` as public `with_retry` and `is_transient` with parameterized server-name log prefix
- Refactor `workflow_state_server.py` to import from `sqlite_retry.py`, removing its local `_with_retry` and `_is_transient` definitions
- Apply `with_retry` (imported from `sqlite_retry.py`) decorator to all write-path MCP handlers in `entity_server.py`
- Apply `with_retry` (imported from `sqlite_retry.py`) decorator to all write-path MCP handlers in `memory_server.py`
- Wrap `cascade_unblock` + `rollup_parent` in `_run_cascade()` in a single `transaction()` block (Phase B atomicity only — Phase A/B separation preserved)
- Audit `EntityDatabase` for multi-step `_commit()` paths outside `BEGIN IMMEDIATE` and wrap in `transaction()`
- Standardize `busy_timeout` to 15000ms in `MemoryDatabase` (currently 5000ms)
- Correct misleading "no concurrent writes possible" comment in `memory_server.py:128`
- Concurrent-write integration tests using `multiprocessing` with real file-backed SQLite

### Out of Scope
- Consolidating MCP servers into a single process
- Connection pooling
- Single-writer proxy architecture
- WAL checkpoint management
- `synchronous=normal` PRAGMA optimization
- Python 3.12+ `autocommit` attribute adoption
- Retry at the Claude Code harness level (MCP call retry)
- Adding external dependencies (e.g., `tenacity`)

## Acceptance Criteria

### Shared Retry Module
- Given `plugins/pd/hooks/lib/sqlite_retry.py` exists
- When imported by any MCP server
- Then provides `with_retry(server_name, max_attempts=3, backoff=(0.1, 0.5, 2.0))` decorator (jitter up to 50ms baked into the decorator) and `is_transient(error)` predicate
- And `is_transient` returns True for `OperationalError` where the message contains "locked" (case-insensitive match). Note: the RCA-documented "SQL logic error" variant is NOT matched — `BEGIN IMMEDIATE` in `transaction()` already prevents the stale implicit transaction root cause (see RCA lines 69-75). Matching "sql logic error" would false-positive on genuine schema/FTS/syntax errors.
- And `is_transient` returns False for all other `OperationalError` messages
- Note: `SQLITE_BUSY_SNAPSHOT` (stale WAL snapshot) is covered because `_with_retry` retries at the MCP handler level, which encompasses the full transaction — each retry starts a fresh transaction with a fresh snapshot, satisfying the PRD's full-transaction-restart requirement

### Entity Server Retry Coverage
- Given entity server MCP handlers processing write operations (`register_entity`, `update_entity`, `delete_entity`, `set_parent`, `add_dependency`, `remove_dependency`)
- When `OperationalError: database is locked` occurs during handler execution
- Then the handler retries with exponential backoff (0.1s, 0.5s, 2.0s + jitter up to 50ms)
- And succeeds transparently if the lock clears within retry window
- And returns a structured MCP error response with "database contention" context if all retries exhaust (no raw `sqlite3.OperationalError` propagates as unhandled MCP exception)

### Memory Server Retry Coverage
- Given memory server MCP handlers processing write operations (`store_memory`, `delete_memory`)
- When `OperationalError: database is locked` occurs during handler execution
- Then the handler retries with identical backoff strategy as entity server
- And the misleading single-threaded safety comment is corrected

### Cascade Atomicity
- Given a phase completion triggers `_run_cascade()` in `entity_engine.py`
- When `cascade_unblock` succeeds but `rollup_parent` would fail under contention
- Then neither operation commits (both roll back together within Phase B transaction) — partial Phase B states are eliminated by the fix
- And Phase A completion remains committed (Phase A/B separation preserved)
- And if reconciliation already detects stale `blocked_by` entries, complete Phase B failure (both rolled back) is recoverable on next invocation — see verification clause below
- Verification (read-only): confirm `reconciliation_orchestrator` already detects stale `blocked_by` entries for completed entities and re-triggers cascade. If detection is absent, document the gap as a backlog item — do not implement during this feature.

### Multi-Step Write Atomicity
- Given the following `EntityDatabase` methods execute multiple write SQL statements before a single `_commit()` outside `BEGIN IMMEDIATE` (upgrading to `transaction()` for eager lock acquisition):
  - `register_entity()` — INSERT entity + INSERT FTS before one `_commit()` (line 1403)
  - `update_entity()` — UPDATE entity + DELETE FTS + INSERT FTS before one `_commit()` (line 1695)
  - Note: `set_parent()` has single UPDATE + `_commit()` — single-statement, skip. `delete_entity()` already uses `BEGIN IMMEDIATE` — skip.
  - Implementation MUST run `grep -n _commit database.py` and document all multi-step sequences found. The above list is preliminary; the audit result is the authoritative list. Expected: 3-5 multi-step sequences. If more than 8 are found, stop and re-evaluate scope before proceeding.
- When these methods execute under contention
- Then all sub-operations within each method are atomic (wrapped in `transaction()`)
- And single-statement writes (e.g., `add_dependency`, `remove_dependency` with one `_commit()`) are NOT wrapped
- Verification: `grep -n '_commit()' database.py` inside non-`_in_transaction` contexts returns zero multi-step sequences

### Timeout Standardization
- Given `MemoryDatabase` in `semantic_memory/database.py`
- When a connection is opened
- Then `PRAGMA busy_timeout = 15000` is set (previously 5000)
- And all other database modules continue to use 15000ms
- And a grep across production DB modules (excluding test files and `doctor/`) confirms no `busy_timeout` value other than 15000 exists. Doctor module uses intentionally short timeouts (2s-5s) for diagnostic purposes — excluded from standardization.
- And the stale comment at `workflow_engine/engine.py:287` (claims "busy_timeout is inherited from EntityDatabase (5s)") is corrected to reflect the actual 15s value

### Concurrent-Write Integration Tests
- Given a test file using `multiprocessing` to spawn multiple writer processes
- When N processes (N >= 3) simultaneously attempt 10+ write operations each on the same DB file
- Then all writes eventually succeed (within retry window)
- And total test completion time is under 30 seconds
- And no `OperationalError: database is locked` propagates as an unhandled error
- And tests cover both entity DB and memory DB contention scenarios
- And at least one test verifies that exhausted retries produce a structured error (not raw OperationalError)
- And a post-test query confirms exactly N*M rows exist in the database (one per write operation), with no duplicates and no missing entries

## Feasibility Assessment

### Assessment Approach
1. **First Principles** - SQLite WAL mode supports concurrent reads + serialized writes; `BEGIN IMMEDIATE` + `busy_timeout` provides the waiting mechanism; application-level retry handles cases where `busy_timeout` alone is insufficient
2. **Codebase Evidence** - `_with_retry` already works in production in `workflow_state_server.py:429-463`; `EntityDatabase.transaction()` already provides `BEGIN IMMEDIATE` context manager at `database.py:1136-1187`
3. **External Evidence** - SQLite documentation confirms WAL + `BEGIN IMMEDIATE` + `busy_timeout` as the standard multi-process concurrency pattern — Source: https://www.sqlite.org/wal.html

### Assessment
**Overall:** Confirmed
**Reasoning:** All required patterns already exist in the codebase. This is a port-and-standardize operation, not new design. The `_with_retry` decorator is proven in production on the workflow state server. The `transaction()` context manager is proven across entity registry operations.
**Key Assumptions:**
- `_with_retry` is safe to apply to entity/memory server handlers — Status: Verified; handlers are idempotent at the transaction level (BEGIN IMMEDIATE ensures atomic retry)
- `_run_cascade()` can be wrapped in `transaction()` without nested transaction conflicts — Status: Verified; `cascade_unblock` uses `remove_dependencies_by_blocker` (calls `_commit()`) and `update_entity` (calls `_commit()`); `rollup_parent` uses `update_entity` (calls `_commit()`). Neither calls `begin_immediate()` or `transaction()`. The `_in_transaction` flag suppresses internal `_commit()` calls.
- `MemoryDatabase` 5000ms → 15000ms has no adverse effects — Status: Verified; higher timeout only means longer wait before failure, no functional change
**Open Risks:** None identified — all key assumptions verified.

## Dependencies
- Feature 056 (sqlite-write-contention-fix) — foundational patterns (completed)
- Feature 058 (sqlite-db-locking-fix) — follow-on fixes (completed)

## Open Questions
- None — all questions resolved during specification.
