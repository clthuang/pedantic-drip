# RCA: Workflow MCP Tools Return SQL Errors During Feature 055

**Date:** 2026-03-24
**Feature:** 055-memory-feedback-loop
**Severity:** Medium (workflow continues via split-commit, but errors are confusing)
**Status:** Root causes identified

## Problem Statement

During feature 055-memory-feedback-loop development, `transition_phase` and `complete_phase` MCP tools consistently returned:

```json
{
  "error": true,
  "error_type": "db_unavailable",
  "message": "Database error: OperationalError: SQL logic error",
  "recovery_hint": "Check database file permissions and disk space"
}
```

Yet `get_phase` worked correctly, and phases auto-advanced despite the errors.

## Root Causes

### Root Cause 1: Multi-Process Write Lock Contention on Shared SQLite DB

**Evidence:** At time of investigation, 7-9 Python processes held `~/.claude/pd/entities/entities.db` open simultaneously:
- 3 `workflow_state_server.py` instances (one per Claude session)
- 3 `entity_server.py` instances (one per Claude session)
- 1 `ui/__main__.py` (dashboard)

SQLite WAL mode allows concurrent readers, but only ONE writer at a time. When multiple MCP server instances from different Claude sessions attempt writes, they compete for the write lock. The 5-second `busy_timeout` (set in `database.py:2610`) is insufficient under sustained contention from 7+ processes.

**Verification:**
- `lsof ~/.claude/pd/entities/entities.db` showed 7-9 processes
- Read operations (`get_workflow_phase`, `get_entity`, `is_healthy`) succeeded 100% under contention
- Write operations (`update_entity`, `update_workflow_phase`) failed 100% under contention
- Script: `agent_sandbox/20260324/rca-workflow-sql-error/experiments/verify_read_vs_write.py`

### Root Cause 2: Split-Commit Architecture in MCP Tool Handlers

**Evidence:** `transition_phase` and `complete_phase` perform 3 sequential, independently-committed DB writes:

| Step | Location | Operation | Commits |
|------|----------|-----------|---------|
| 1 | `engine.py:100` | `update_workflow_phase(workflow_phase=target)` | Yes (database.py:2163) |
| 2 | `workflow_state_server.py:463` | `update_entity(metadata=...)` | Yes (database.py:1650) |
| 3 | `workflow_state_server.py:468` | `update_workflow_phase(kanban_column=...)` | Yes (database.py:2163) |

If Step 1 commits successfully but Step 2 or 3 fails with `OperationalError`, the `_with_error_handling` decorator (line 322-340) catches the exception and returns `db_unavailable`. But Step 1's commit is already persisted -- the phase HAS advanced in the database.

This directly explains:
- **Q2 (why get_phase works but transition/complete fail):** `get_phase` is read-only; transition/complete require writes that contend for the lock.
- **Q3 (why phases auto-advance despite errors):** Step 1 commits the phase change before Steps 2-3 fail. The next `get_phase` reads the committed phase.

**Verification:** Code trace in `agent_sandbox/20260324/rca-workflow-sql-error/experiments/verify_split_commit.py`

### Root Cause 3: No Error Recovery or Retry in MCP Write Path

**Evidence:** The `_with_error_handling` decorator is a catch-all that converts any `sqlite3.Error` into a terminal error response. There is no:
- Retry logic with backoff for `SQLITE_BUSY` (database locked)
- Distinction between transient errors (lock contention) and permanent errors (corruption)
- Compensation logic to rollback Step 1 if Steps 2-3 fail

The frozen engine (`engine.py`) has better error handling -- it catches `sqlite3.Error` on writes and returns `degraded=True`, allowing the caller to continue. But the MCP layer's additional writes (`update_entity` for metadata, `update_workflow_phase` for kanban) lack this resilience.

## "SQL Logic Error" vs "Database is Locked"

The user-reported error message was "SQL logic error" (SQLite error code `SQLITE_ERROR = 1`), while reproduction consistently shows "database is locked" (SQLite error code `SQLITE_BUSY = 5`). Both are `OperationalError` subtypes. Possible explanations for the discrepancy:

1. **Stale implicit transaction:** Python's sqlite3 default `isolation_level=""` starts implicit transactions on DML. If a prior operation on the same connection left a half-committed transaction and a new operation begins before cleanup, SQLite can return `SQLITE_ERROR` instead of `SQLITE_BUSY`.
2. **FTS index operation during contention:** The `update_entity` method does `DELETE FROM entities_fts` + `INSERT INTO entities_fts` (lines 1640-1649 in database.py). FTS virtual tables can surface different error codes under concurrent access than regular tables.
3. **Python/SQLite version interaction:** The MCP servers run Python 3.14 with sqlite 3.52.0, where error code mapping may differ slightly from older versions.

Regardless of the exact error text, the root cause is the same: write lock contention across multiple processes on a single SQLite database file.

## Why get_phase is Immune

`get_phase` calls `_process_get_phase` -> `engine.get_state()`. The engine's `get_state` method:
1. Calls `is_healthy()` (SELECT 1) -- always succeeds in WAL mode
2. Calls `get_workflow_phase()` (SELECT) -- always succeeds in WAL mode
3. On any `sqlite3.Error`, falls back to `.meta.json` file read

No writes are attempted. In WAL mode, reads never block on concurrent writers. Additionally, `_process_get_phase` is NOT wrapped with `@_with_error_handling`, so any error goes through the engine's internal fallback rather than becoming `db_unavailable`.

## Side Effects of the Split-Commit Problem

When the error occurs, the database is left in an inconsistent state:
- `workflow_phases.workflow_phase` is updated (correct next phase)
- `workflow_phases.kanban_column` is stale (not updated)
- `entities.metadata.phase_timing` is stale (no started/completed timestamps)
- `.meta.json` is stale (not projected from DB)

This means kanban board views and phase timing data may be incomplete for phases that transitioned during contention periods.

## Hypotheses Considered

| # | Hypothesis | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | Write lock contention from multiple MCP servers | **Confirmed** | 7-9 processes on lsof, writes fail, reads succeed |
| 2 | Split-commit allows partial success | **Confirmed** | Code trace shows 3 independent commits |
| 3 | No retry/recovery in MCP write path | **Confirmed** | _with_error_handling is catch-all, no retry |
| 4 | FTS index corruption causing SQL logic error | **Rejected** | FTS integrity check shows 177/177 rows in sync |
| 5 | CHECK constraint violation on workflow_phase | **Rejected** | Schema v7 includes all 5D phases; "design" is valid |
| 6 | Foreign key violations causing writes to fail | **Rejected** | FK violations exist (22 orphans) but on entities self-refs, not workflow_phases |
| 7 | Schema version mismatch between servers | **Rejected** | All servers use same plugin version (4.13.26), schema is v7 |

## Reproduction

Reproduction is reliable when multiple Claude sessions are active:

```bash
# Verify contention exists
lsof ~/.claude/pd/entities/entities.db | wc -l

# Run verification
plugins/pd/.venv/bin/python agent_sandbox/20260324/rca-workflow-sql-error/experiments/verify_read_vs_write.py
```

## Artifacts

- `agent_sandbox/20260324/rca-workflow-sql-error/reproduction/reproduce_lock.py` -- concurrent reader/writer test
- `agent_sandbox/20260324/rca-workflow-sql-error/experiments/verify_read_vs_write.py` -- read vs write asymmetry
- `agent_sandbox/20260324/rca-workflow-sql-error/experiments/verify_split_commit.py` -- split-commit code trace
- `agent_sandbox/20260324/rca-workflow-sql-error/experiments/verify_stale_transaction.py` -- stale transaction state
