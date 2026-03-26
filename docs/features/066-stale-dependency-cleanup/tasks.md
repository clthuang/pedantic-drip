# Tasks: Stale Dependency Cleanup

## Phase 1: Event-Driven Cascade

### T1.1: Add cascade trigger to update_entity + tests
- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`, `test_database.py`
- **Design ref:** I-1, TD-1, TD-2, TD-3
- **AC:** (a) After transaction block exits, before re-attribution: `if status == "completed": try: from entity_registry.dependencies import DependencyManager; DependencyManager().cascade_unblock(self, entity_uuid) except Exception: pass`. (b) 4 tests: completed triggers cascade (edge removed + dependent promoted), non-completed doesn't trigger, no dependents = no-op, idempotent.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "cascade_on_complete"`

## Phase 2: Doctor Check + Fix

### T2.1: Add check_stale_dependencies + _fix_stale_dependency + wiring + tests
- **Files:** `doctor/checks.py`, `doctor/__init__.py`, `doctor/fix_actions.py`, `doctor/fixer.py`, `doctor/test_checks.py`, `doctor/test_fixer.py`
- **Design ref:** I-2, I-3, I-5
- **AC:** (a) SQL JOIN detects stale edges, Issue with UUIDs in message, (b) fix_hint prefix "Remove stale dependency", (c) fix extracts second UUID, calls cascade_unblock via ctx.db, (d) CHECK_ORDER + _ENTITY_DB_CHECKS + _SAFE_PATTERNS wired, (e) 3 tests: stale detected, clean passes, fix removes + promotes.
- **Verify:** `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v -k "stale"`

## Phase 3: Reconciliation Task

### T3.1: Create dependency_freshness.py + wire into __main__.py + tests
- **Files:** `reconciliation_orchestrator/dependency_freshness.py` (new), `reconciliation_orchestrator/__main__.py`, `reconciliation_orchestrator/test_dependency_freshness.py` (new), `reconciliation_orchestrator/test_orchestrator.py`
- **Design ref:** I-4, I-5
- **AC:** (a) cleanup_stale_dependencies uses public API (query_dependencies + get_entity_by_uuid), returns unique blocker count, (b) __main__.py: init dependency_cleanup=None in results, Task 5 inside try block after Task 4, own try/except fail-open, (c) update module docstring, (d) update test_orchestrator.py for new key, (e) 1 test: stale edge cleaned, returns 1.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/reconciliation_orchestrator/ -v`
