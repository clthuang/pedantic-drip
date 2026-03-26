# Design: Stale Dependency Cleanup

## Prior Art Research

- **cascade_unblock pattern:** `dependencies.py:80-111` — removes edges, promotes dependents. Idempotent. Uses only public EntityDatabase API.
- **Doctor check pattern:** `checks.py:1699-1729` (`check_referential_integrity`) — raw SQL on `entities_conn`, returns Issues with fix_hints.
- **Fix action pattern:** `fix_actions.py:247-263` (`_fix_remove_orphan_dependency`) — extracts UUIDs from message, delegates to DB method.
- **Reconciliation task pattern:** `entity_status.py` — module with single function, called from `__main__.py` with try/except isolation.
- **transaction() context manager:** `database.py:1181-1205` — re-entrant safe. `cascade_unblock` calls `update_entity` which opens its own transaction — safe when called outside an existing transaction.

## Architecture Overview

```
Three-layer defense:

Layer 1 (Prevention): database.py update_entity()
  → on status="completed" → DependencyManager().cascade_unblock()
  → catches ALL completion paths at DB layer

Layer 2 (Recovery): reconciliation_orchestrator/dependency_freshness.py
  → at session start → scan for stale edges → cascade_unblock each
  → catches edges that slipped through (contention, pre-existing)

Layer 3 (Audit): doctor/checks.py check_stale_dependencies
  → on-demand → detect + report → --fix auto-repairs
  → manual verification and repair
```

## Technical Decisions

### TD-1: Cascade placement outside transaction block
**Decision:** Place the cascade call AFTER `with self.transaction()` exits in `update_entity()`, before the re-attribution block.
**Rationale:** `cascade_unblock` calls `db.update_entity(status="planned")` for each promoted dependent. If placed inside the transaction, this creates nested transactions. Outside the transaction, each cascade update_entity runs its own independent transaction.

### TD-2: Lazy import to break circular dependency
**Decision:** Import `DependencyManager` inside the function body, not at module level.
**Rationale:** `dependencies.py` imports `EntityDatabase` from `database.py`. A top-level import of `DependencyManager` in `database.py` would create `database.py → dependencies.py → database.py` cycle.

### TD-3: Reuse existing entity_uuid variable
**Decision:** Use the `entity_uuid` already resolved at the top of `update_entity()` (~line 2016).
**Rationale:** Avoids a redundant DB lookup. The UUID is available in scope.

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| cascade_unblock fails during update_entity | Stale edge persists | Low | Layer 2 (reconciliation) and Layer 3 (doctor) catch it |
| Infinite recursion if promoted dependent triggers another cascade | Stack overflow | None | `cascade_unblock` promotes to `planned`, not `completed` — no re-trigger |
| Performance overhead on every completion | Slow completions | Low | One SELECT query returning ~0 rows for common case (no dependents) |

## Interfaces

### I-1: `database.py` — Event-driven cascade in `update_entity()`

```python
# In update_entity(), AFTER the transaction block exits, BEFORE re-attribution:
if status == "completed":
    from entity_registry.dependencies import DependencyManager
    DependencyManager().cascade_unblock(self, entity_uuid)
```

### I-2: `doctor/checks.py` — `check_stale_dependencies`

```python
def check_stale_dependencies(*, entities_conn, **kwargs) -> CheckResult:
    """Detect blocked_by edges pointing to completed entities."""
    # SQL: SELECT ed.entity_uuid, ed.blocked_by_uuid, e_blocker.type_id
    #      FROM entity_dependencies ed
    #      JOIN entities e_blocker ON ed.blocked_by_uuid = e_blocker.uuid
    #      WHERE e_blocker.status = 'completed'
    # Each row → Issue(severity="warning",
    #   message=f"Stale blocked_by edge: entity '{entity_uuid}' blocked by completed '{blocked_by_uuid}' ({blocker_type_id})",
    #   fix_hint=f"Remove stale dependency on completed '{blocker_type_id}'")
```

### I-3: `doctor/fix_actions.py` — `_fix_stale_dependency`

```python
def _fix_stale_dependency(ctx, issue) -> str:
    if ctx.db is None:
        raise ValueError("No entity database")
    uuids = re.findall(r"'([0-9a-f-]{36})'", issue.message)
    if len(uuids) < 2:
        raise ValueError(f"Cannot extract UUIDs from: {issue.message}")
    blocked_by_uuid = uuids[1]  # second UUID is the blocker
    from entity_registry.dependencies import DependencyManager
    DependencyManager().cascade_unblock(ctx.db, blocked_by_uuid)
    return f"Removed stale dependency on {blocked_by_uuid}"
```

### I-4: `reconciliation_orchestrator/dependency_freshness.py`

```python
def cleanup_stale_dependencies(db: EntityDatabase) -> int:
    """Remove stale blocked_by edges and promote unblocked dependents.
    Returns count of unique completed blocker UUIDs processed."""
    # Same SQL as I-2
    # Deduplicate to unique blocker UUIDs
    # For each: DependencyManager().cascade_unblock(db, uuid)
    # Return len(unique_blocker_uuids)
```

### I-5: Wiring

```python
# doctor/__init__.py — add to CHECK_ORDER and _ENTITY_DB_CHECKS
CHECK_ORDER = [..., check_stale_dependencies]
_ENTITY_DB_CHECKS = {..., "check_stale_dependencies"}

# doctor/fixer.py — add to _SAFE_PATTERNS
_SAFE_PATTERNS = [..., ("Remove stale dependency", _fix_stale_dependency)]

# reconciliation_orchestrator/__main__.py — add Task 5
# Inside outer try block, after Task 4, before except:
try:
    result = dependency_freshness.cleanup_stale_dependencies(entity_db)
    results["dependency_cleanup"] = result
except Exception as exc:
    results["errors"].append(f"dependency_freshness: {exc}")
    results["dependency_cleanup"] = 0
```
