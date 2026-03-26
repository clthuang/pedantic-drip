# PRD: Stale Dependency Cleanup

## Status
- Created: 2026-03-27
- Status: Draft
- Problem Type: Bug Fix / Reliability
- Backlog: #00047

## Problem Statement
When an entity completes, `cascade_unblock()` in Phase B removes its `blocked_by` edges from the `entity_dependencies` table and promotes dependent entities from `blocked` to `planned`. If Phase B fails (e.g., SQLite contention during concurrent MCP server startup), stale `blocked_by` edges persist — completed entities remain in other entities' dependency lists, preventing those dependents from unblocking.

### Evidence
- Feature 062 implementation log (Task 1.4): "Reconciliation gap found — `blocked_by` does NOT appear in reconciliation.py. Phase B complete-failure recovery is unverified."
- `_recover_pending_cascades()` in reconciliation.py:521-626 calls `cascade_unblock` but only for completed entities that have a parent AND whose parent shows a progress mismatch. Completed entities without parents, or those whose parent progress happens to be correct, retain stale `blocked_by` edges.
- Doctor `check_referential_integrity` (checks.py:1699-1729) catches orphaned UUIDs but NOT stale edges where both entities exist and the blocker is completed
- No code path directly queries: "Are there dependency edges pointing to completed entities?"

## Goals
1. Detect stale `blocked_by` edges at session start (reconciliation) and on-demand (doctor)
2. Automatically remove stale edges and unblock dependents — no LLM involvement
3. Zero new dependencies — uses existing `DependencyManager.cascade_unblock()` and doctor check patterns

## Success Criteria
- [ ] Doctor check detects stale `blocked_by` edges (completed blockers)
- [ ] Doctor `--fix` removes stale edges and promotes dependents
- [ ] Reconciliation orchestrator cleans stale edges at session start
- [ ] All operations are code-based (Python), no LLM dispatch

## Scope

### In Scope
- New doctor check: `check_stale_dependencies`
- New doctor fix action: `_fix_stale_dependency`
- New reconciliation task: `dependency_freshness.py`
- Tests for all three

### Out of Scope
- Changing the Phase A/B separation in entity_engine.py (that's feature 062's domain)
- Adding blocked_by to .meta.json (it's DB-only by design)
- LLM-based dependency analysis

## Requirements

### Functional

- FR-1: New doctor check `check_stale_dependencies` — queries `entity_dependencies` joined with `entities` to find edges where `blocked_by_uuid` points to a completed entity:
  ```sql
  SELECT ed.entity_uuid, ed.blocked_by_uuid, e_blocker.type_id AS blocker_type_id
  FROM entity_dependencies ed
  JOIN entities e_blocker ON ed.blocked_by_uuid = e_blocker.uuid
  WHERE e_blocker.status = 'completed'
  ```
  Only `completed` status is considered terminal for unblocking purposes (abandoned entities retain blocking role by design — they may be resumed). Stale dependency cleanup operates globally across all projects since `entity_dependencies` does not carry `project_id`.
  Each result is an Issue with severity `warning` and fix_hint `"Remove stale dependency on completed '<blocker_type_id>'"`. The prefix `"Remove stale dependency"` must match the `_SAFE_PATTERNS` entry exactly.

- FR-2: New doctor fix action `_fix_stale_dependency` — for each stale edge:
  1. Instantiate `dep_mgr = DependencyManager()`
  2. Call `dep_mgr.cascade_unblock(ctx.db, blocked_by_uuid)` which removes the edge AND promotes dependents
  3. Return description of what was fixed
  Note: `cascade_unblock` is an instance method, not static. It is idempotent — safe to call multiple times for same UUID.

- FR-3: New reconciliation task `dependency_freshness.py` with function `cleanup_stale_dependencies(db)`:
  1. Run the same SQL query as FR-1
  2. Collect unique completed blocker UUIDs
  3. Instantiate `dep_mgr = DependencyManager()`
  4. For each, call `dep_mgr.cascade_unblock(db, uuid)`
  5. Return count of cleaned edges
  Runs at session start as Task 5 in the orchestrator, after workflow reconciliation (Task 4). Must be placed inside the existing try block in `__main__.py:run()`, between Task 4 and the except clause. Result key: `"dependency_cleanup"` (integer count of cleaned edges).

- FR-4: Wire into existing infrastructure:
  - `check_stale_dependencies` added to `CHECK_ORDER` in `doctor/__init__.py` and `_ENTITY_DB_CHECKS`
  - `_fix_stale_dependency` registered in `_SAFE_PATTERNS` in `fixer.py` with prefix `"Remove stale dependency"`
  - `dependency_freshness` imported and called in `reconciliation_orchestrator/__main__.py`

### Non-Functional
- NFR-1: Doctor check must be read-only (no mutations). Fix happens only via `--fix` flag.
- NFR-2: Reconciliation task must be fail-open (try/except, append to errors list).
- NFR-3: All operations use existing public `EntityDatabase` and `DependencyManager` APIs — no raw `db._conn` access.

## Technical Analysis

### Existing Code to Reuse
- `DependencyManager.cascade_unblock(db, uuid)` — does the full cleanup (dependencies.py:80-111)
- Doctor check pattern — `check_referential_integrity` as template (checks.py:1699-1729)
- Fix action pattern — `_fix_remove_orphan_dependency` as template (fix_actions.py:247-263)
- Reconciliation task pattern — `entity_status.py` as template for a new task module

### Files to Change
| File | Change |
|------|--------|
| `plugins/pd/hooks/lib/doctor/checks.py` | Add `check_stale_dependencies` |
| `plugins/pd/hooks/lib/doctor/__init__.py` | Add to CHECK_ORDER + _ENTITY_DB_CHECKS |
| `plugins/pd/hooks/lib/doctor/fix_actions.py` | Add `_fix_stale_dependency` |
| `plugins/pd/hooks/lib/doctor/fixer.py` | Add to _SAFE_PATTERNS |
| `plugins/pd/hooks/lib/reconciliation_orchestrator/dependency_freshness.py` | New module |
| `plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py` | Add Task 5 |

### Estimated Size
~100 lines of new code, ~100-150 lines of test code. Small, focused feature.

## Decision
Implement both doctor check AND reconciliation task. The doctor provides on-demand detection with `--fix`, while reconciliation provides automatic cleanup at every session start. Belt and suspenders — either one alone would be sufficient, but together they guarantee no stale edges persist beyond one session start.
