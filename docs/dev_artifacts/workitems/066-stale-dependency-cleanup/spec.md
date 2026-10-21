# Spec: Stale Dependency Cleanup

## Overview
Prevent and clean up stale `blocked_by` edges in `entity_dependencies` where the blocker entity has completed. Three-layer defense: event-driven cascade at DB layer, reconciliation at session start, doctor check on-demand.

**PRD:** `docs/dev_artifacts/workitems/066-stale-dependency-cleanup/prd.md`

## Scope

### In Scope
- Event-driven cascade in `database.py update_entity()` on status→completed
- Doctor check `check_stale_dependencies` with `--fix` auto-repair
- Reconciliation task `dependency_freshness.py` at session start
- Tests for all three

### Out of Scope
- Changing Phase A/B separation in entity_engine.py
- Adding blocked_by to .meta.json
- LLM-based dependency analysis

## Functional Specifications

### FS-1: Event-Driven Cascade (Primary Prevention)

**File:** `plugins/pd/hooks/lib/entity_registry/database.py`

In `update_entity()`, **AFTER the `with self.transaction()` block exits** (after ~line 2100) and **BEFORE the re-attribution block** (~line 2102), if the new status is `"completed"`:
1. Lazily import `DependencyManager` inside the function body — MUST be lazy because `dependencies.py` imports `EntityDatabase` from `database.py` at module level, creating a circular import if done at top level
2. Reuse the `entity_uuid` variable already resolved at the top of `update_entity()` (~line 2016) — no additional DB lookup needed
3. Call `DependencyManager().cascade_unblock(self, entity_uuid)`

**Transaction safety:** The cascade call is OUTSIDE the transaction block, so each `update_entity(status="planned")` call from `cascade_unblock` runs its own independent transaction. No nesting issues.

This fires on every code path that completes an entity — MCP tools, reconciliation, doctor --fix, manual scripts — because it's at the DB layer.

**Idempotency:** If cascade already ran (e.g., entity_engine Phase B succeeded), `cascade_unblock` finds zero edges and is a no-op. For the common case (entity has no dependents), this is one SELECT query returning zero rows — negligible overhead.

**Acceptance Criteria:**
- [ ] AC-1.1: `update_entity(type_id, status="completed")` automatically removes all `blocked_by` edges pointing to that entity
- [ ] AC-1.2: Dependent entities with zero remaining blockers are promoted from `blocked` to `planned`
- [ ] AC-1.3: If no edges exist (cascade already ran), the call is a no-op with no errors
- [ ] AC-1.4: Non-completed status changes do NOT trigger cascade
- [ ] AC-1.5: Entity with no dependents completes without errors (common hot path)

### FS-2: Doctor Check

**File:** `plugins/pd/hooks/lib/doctor/checks.py`

New function `check_stale_dependencies(*, entities_conn, **kwargs) -> CheckResult`:

```sql
SELECT ed.entity_uuid, ed.blocked_by_uuid, e_blocker.type_id AS blocker_type_id
FROM entity_dependencies ed
JOIN entities e_blocker ON ed.blocked_by_uuid = e_blocker.uuid
WHERE e_blocker.status = 'completed'
```

Each row produces an Issue with exact format:
```python
Issue(
    check="stale_dependencies",
    severity="warning",
    entity=None,
    message=f"Stale blocked_by edge: entity '{entity_uuid}' blocked by completed '{blocked_by_uuid}' ({blocker_type_id})",
    fix_hint=f"Remove stale dependency on completed '{blocker_type_id}'"
)
```
Note: `check_stale_dependencies` receives `entities_conn` (raw sqlite3.Connection) consistent with other check functions. It uses only raw SQL for the read-only query. The `EntityDatabase` instance is only needed by the fix action (FS-3), which receives it via `ctx.db`.

**Wiring:**
- Add to `CHECK_ORDER` in `doctor/__init__.py`
- Add to `_ENTITY_DB_CHECKS` set
- Read-only — no mutations in the check itself

**Acceptance Criteria:**
- [ ] AC-2.1: Check returns warning for each `blocked_by` edge pointing to a completed entity
- [ ] AC-2.2: Check returns `passed=True` when no stale edges exist
- [ ] AC-2.3: Check is read-only — no DB mutations

### FS-3: Doctor Fix Action

**File:** `plugins/pd/hooks/lib/doctor/fix_actions.py`

New function `_fix_stale_dependency(ctx, issue) -> str`:
0. Guard: `if ctx.db is None: raise ValueError("No entity database")`
1. Extract UUIDs from `issue.message` via `re.findall(r"'([0-9a-f-]{36})'", issue.message)` — returns `[entity_uuid, blocked_by_uuid]` (second match is the blocker)
2. Call `DependencyManager().cascade_unblock(ctx.db, blocked_by_uuid)`
3. Return description string

**Wiring:** Register in `_SAFE_PATTERNS` in `fixer.py` with prefix `"Remove stale dependency"`.

**Acceptance Criteria:**
- [ ] AC-3.1: `doctor --fix` removes stale edges and promotes unblocked dependents
- [ ] AC-3.2: Fix is idempotent — running twice produces same result

### FS-4: Reconciliation Task

**File:** `plugins/pd/hooks/lib/reconciliation_orchestrator/dependency_freshness.py` (new)

Function `cleanup_stale_dependencies(db: EntityDatabase) -> int`:
1. Run same SQL query as FS-2
2. Collect unique completed blocker UUIDs
3. `dep_mgr = DependencyManager()`
4. For each UUID: `dep_mgr.cascade_unblock(db, uuid)`
5. Return count of cleaned edges

**Wiring in `__main__.py`:**
- Import `dependency_freshness`
- Add as Task 5 inside the outer try block (lines 83-133), after Task 4 and before the outer except clause (line 134) — this ensures `entity_db` is initialized. Own inner try/except for fail-open isolation.
- Result key: `"dependency_cleanup"` (integer)
- Update module docstring to include `dependency_cleanup` in output keys list

**Acceptance Criteria:**
- [ ] AC-4.1: Given: entity A completed with blocked_by edge from B→A. When: `cleanup_stale_dependencies(db)` runs. Then: edge removed, B promoted blocked→planned, returns 1.
- [ ] AC-4.2: Task failure does not block other reconciliation tasks (fail-open)
- [ ] AC-4.3: Result appears in orchestrator JSON output as `dependency_cleanup` key

## Error Handling

| Scenario | Behavior |
|----------|----------|
| cascade_unblock fails mid-update | Transaction rolls back; stale edge preserved for next run |
| No stale edges found | No-op; doctor returns passed, reconciliation returns 0 |
| Circular dependency detected | cascade_unblock doesn't create cycles; only removes edges |
| Entity already unblocked | cascade_unblock checks remaining blockers before promoting |

## Testing Requirements

### Unit Tests (~8 tests)
- `test_database.py`: 4 tests for FS-1 — completed triggers cascade, non-completed doesn't, idempotent, dependent promoted
- `doctor/test_checks.py`: 2 tests for FS-2 — stale edge detected, clean state passes
- `doctor/test_fixer.py`: 1 test for FS-3 — fix removes edge and promotes
- `reconciliation_orchestrator/test_dependency_freshness.py`: 1 test for FS-4 — cleanup returns count

### Verification
```
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "cascade_on_complete"
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v -k "stale"
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/reconciliation_orchestrator/ -v -k "dependency_freshness"
```
