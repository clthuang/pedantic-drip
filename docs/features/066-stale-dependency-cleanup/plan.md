# Plan: Stale Dependency Cleanup

## Implementation Order

3 phases, ~8 tests. Small, focused feature.

## Phase 1: Event-Driven Cascade (no dependencies)

### 1.1 Add cascade trigger to update_entity
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Design ref:** I-1, TD-1, TD-2, TD-3
**Why:** Primary prevention layer — catches all completion paths at DB layer.

- After `with self.transaction()` block exits, before re-attribution block
- `if status == "completed":` → lazy import DependencyManager → `cascade_unblock(self, entity_uuid)`
- Wrapped in try/except (fail-open: log to stderr, then continue). `except Exception as exc: print(f"cascade_unblock failed: {exc}", file=sys.stderr)`
- Reuse existing `entity_uuid` variable (no additional lookup)

**Tests:** 4 tests in `test_database.py`:
- completed triggers cascade (add dependency edge, complete blocker, assert edge removed + dependent promoted)
- non-completed status doesn't trigger
- no dependents = no-op (common hot path)
- idempotent (complete twice, no error)

**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "cascade_on_complete"`

## Phase 2: Doctor Check + Fix (depends on Phase 1 for test fixtures)

### 2.1 Add check_stale_dependencies
**File:** `plugins/pd/hooks/lib/doctor/checks.py`
**Design ref:** I-2
**Why:** On-demand detection layer.

- SQL JOIN on entity_dependencies + entities WHERE status='completed'
- Returns Issue per stale edge with message containing both UUIDs
- Wired into CHECK_ORDER + _ENTITY_DB_CHECKS in `__init__.py`

### 2.2 Add _fix_stale_dependency
**File:** `plugins/pd/hooks/lib/doctor/fix_actions.py`
**Design ref:** I-3
**Why:** Auto-repair via `--fix`.

- Guard: `if ctx.db is None: raise ValueError`
- Extract UUIDs from issue.message (second match = blocker)
- Guard: `if len(uuids) < 2: raise ValueError`
- Call `DependencyManager().cascade_unblock(ctx.db, blocked_by_uuid)`
- Wired into _SAFE_PATTERNS in `fixer.py` with prefix "Remove stale dependency"

**Tests:** 3 tests across 2 files:
- `doctor/test_checks.py`: 2 tests — stale edge detected as warning, clean state passes
- `doctor/test_fixer.py`: 1 test — fix removes edge and promotes dependent

**Verification:** `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v -k "stale"`

## Phase 3: Reconciliation Task (depends on nothing, but logically after Phase 1)

### 3.1 Create dependency_freshness.py
**File:** `plugins/pd/hooks/lib/reconciliation_orchestrator/dependency_freshness.py` (new)
**Design ref:** I-4
**Why:** Automatic cleanup at session start.

- `cleanup_stale_dependencies(db)` → query_dependencies() + get_entity_by_uuid() per edge (public API, NFR-3)
- Collect unique completed blocker UUIDs → cascade_unblock each
- Return count of unique blockers processed

### 3.2 Wire into __main__.py
**File:** `plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py`
**Design ref:** I-5
**Why:** Task 5 registration.

- Initialize `"dependency_cleanup": None` in results dict (line ~74) alongside other keys
- Inside outer try block, after Task 4, before except
- Own try/except (fail-open): success sets integer count, failure sets 0
- Update module docstring to include dependency_cleanup key
- **Update test_orchestrator.py**: check for new `dependency_cleanup` key in output assertions

**Note on spec/design divergence:** Spec FS-4 says "same SQL query as FR-1" but design I-4 uses public API (query_dependencies + get_entity_by_uuid). Follow design I-4 (public API) per NFR-3.

**Tests:** 1 test in `reconciliation_orchestrator/test_dependency_freshness.py` (new):
- Given stale edge, cleanup returns 1, edge removed, dependent promoted

**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/reconciliation_orchestrator/ -v -k "dependency_freshness"`

## Dependency Graph

```
Phase 1 (database.py cascade) — no dependencies
    ↓
Phase 2 (doctor check + fix) — can reuse Phase 1 test fixtures
    ↓
Phase 3 (reconciliation task) — independent but logically last
```

## Files Changed Summary

| File | Change |
|------|--------|
| `entity_registry/database.py` | ~10 lines: cascade trigger in update_entity |
| `doctor/checks.py` | ~25 lines: check_stale_dependencies |
| `doctor/__init__.py` | ~2 lines: CHECK_ORDER + _ENTITY_DB_CHECKS |
| `doctor/fix_actions.py` | ~15 lines: _fix_stale_dependency |
| `doctor/fixer.py` | ~1 line: _SAFE_PATTERNS entry |
| `reconciliation_orchestrator/dependency_freshness.py` | ~25 lines: new module |
| `reconciliation_orchestrator/__main__.py` | ~8 lines: Task 5 wiring |

## Final Verification

```
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "cascade_on_complete"
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/reconciliation_orchestrator/ -v
```
