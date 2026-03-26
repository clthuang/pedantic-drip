# Spec: Stale Dependency Cleanup

## Overview
Prevent and clean up stale `blocked_by` edges in `entity_dependencies` where the blocker entity has completed. Three-layer defense: event-driven cascade at DB layer, reconciliation at session start, doctor check on-demand.

**PRD:** `docs/features/066-stale-dependency-cleanup/prd.md`

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

In `update_entity()`, after the status UPDATE commits and FTS sync completes, if the new status is `"completed"`:
1. Lazily import `DependencyManager` (avoids circular import)
2. Look up the entity's UUID from the resolved type_id
3. Call `DependencyManager().cascade_unblock(self, entity_uuid)`

This fires on every code path that completes an entity — MCP tools, reconciliation, doctor --fix, manual scripts — because it's at the DB layer.

**Idempotency:** If cascade already ran (e.g., entity_engine Phase B succeeded), `cascade_unblock` finds zero edges and is a no-op.

**Acceptance Criteria:**
- [ ] AC-1.1: `update_entity(type_id, status="completed")` automatically removes all `blocked_by` edges pointing to that entity
- [ ] AC-1.2: Dependent entities with zero remaining blockers are promoted from `blocked` to `planned`
- [ ] AC-1.3: If no edges exist (cascade already ran), the call is a no-op with no errors
- [ ] AC-1.4: Non-completed status changes do NOT trigger cascade

### FS-2: Doctor Check

**File:** `plugins/pd/hooks/lib/doctor/checks.py`

New function `check_stale_dependencies(*, entities_conn, **kwargs) -> CheckResult`:

```sql
SELECT ed.entity_uuid, ed.blocked_by_uuid, e_blocker.type_id AS blocker_type_id
FROM entity_dependencies ed
JOIN entities e_blocker ON ed.blocked_by_uuid = e_blocker.uuid
WHERE e_blocker.status = 'completed'
```

Each row produces an `Issue(check="stale_dependencies", severity="warning", entity=None, message="...", fix_hint="Remove stale dependency on completed '<blocker_type_id>'")`.

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
1. Extract blocker UUID from `issue.message` via regex `'([0-9a-f-]{36})'`
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
- Add as Task 5 inside the existing try block, after Task 4 (workflow reconciliation)
- Result key: `"dependency_cleanup"` (integer)
- Wrapped in its own try/except (fail-open)

**Acceptance Criteria:**
- [ ] AC-4.1: Reconciliation cleans stale edges at session start
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
