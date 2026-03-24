# Plan: SQLite Concurrency Defense

## Implementation Order

### Stage 1: Foundation
Items with no dependencies.

1. **Shared retry module (TDD)** — Write tests then implement `with_retry` and `is_transient`
   - **Why this item:** Design C1 — prerequisite for all server retry integrations (C2, C3, C4)
   - **Why this order:** No dependencies; all other retry work depends on this module existing
   - **Deliverable:** `plugins/pd/hooks/lib/test_sqlite_retry.py` (tests first, based on design interfaces I1/I2) then `plugins/pd/hooks/lib/sqlite_retry.py` implementing `with_retry(server_name, max_attempts, backoff)` decorator factory and `is_transient(exc)` predicate
   - **Complexity:** Simple — extracting proven code from `workflow_state_server.py:424-463`, parameterizing server name prefix
   - **Files:** `plugins/pd/hooks/lib/test_sqlite_retry.py` (new, written first), `plugins/pd/hooks/lib/sqlite_retry.py` (new, implements to pass tests)
   - **Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/test_sqlite_retry.py -v` passes; tests cover transient classification, retry count, backoff sequence, jitter, and exhausted-retry propagation

2. **Timeout standardization** — Change `MemoryDatabase` busy_timeout from 5000 to 15000ms
   - **Why this item:** Design C7, Spec FR-5 — inconsistent timeouts across DB modules
   - **Why this order:** No dependencies; independent change
   - **Deliverable:** `PRAGMA busy_timeout = 15000` in `semantic_memory/database.py`; stale comment fixed in `workflow_engine/engine.py:287`. Also grep for `sqlite3.connect(timeout=...)` parameters across all DB modules and document whether Python-level timeouts need alignment (Python `timeout` governs initial connection lock wait; PRAGMA `busy_timeout` governs SQL statement-level waits — intentional difference should be documented).
   - **Complexity:** Simple — two-line change plus documentation
   - **Files:** `plugins/pd/hooks/lib/semantic_memory/database.py`, `plugins/pd/hooks/lib/workflow_engine/engine.py`
   - **Verification:** Grep across production DB modules (excluding test files and doctor/) confirms no PRAGMA busy_timeout value other than 15000

### Stage 2: Import Pattern Validation
Depends on item 1 (shared module).

3. **Workflow state server refactor** — Replace local `_with_retry`/`_is_transient` with imports from shared module
   - **Why this item:** Design C4 — eliminate code duplication, single source of truth for retry logic
   - **Why this order:** Depends on item 1 (shared module). Must be done before entity/memory server integration to validate the import pattern works. Items 4 and 5 from Stage 1 are independent and can run in parallel with this.
   - **Deliverable:** `workflow_state_server.py` imports from `sqlite_retry.py`, local `_with_retry`/`_is_transient` definitions replaced with wrapper/alias
   - **Complexity:** Simple — import + alias, no behavioral change. Verify 9 `@_with_retry()` call sites unchanged.
   - **Files:** `plugins/pd/mcp/workflow_state_server.py`
   - **Verification:** All existing workflow state server tests pass; `grep -c '@_with_retry' workflow_state_server.py` returns 9

4. **Cascade atomicity fix** — Wrap `_run_cascade()` Phase B in `transaction()`
   - **Why this item:** Design C5, Spec FR-3 — eliminate split-commit in cascade operations
   - **Why this order:** Independent of retry module (uses existing `transaction()` infrastructure); can run in parallel with Stage 1
   - **Deliverable:** Restructure `_run_cascade()` method body per design I3: `with self._db.transaction():` block wraps only `cascade_unblock` (line 586) + `rollup_parent` (line 591). Move `compute_progress` (line 598) and notification push (lines 601-602) AFTER the `with` block exits. Wrap post-transaction `compute_progress` + notifications in separate try/except that logs but does not propagate — prevents a `compute_progress` failure after successful DB commit from masking the commit as `cascade_error`. Sub-deliverable: verify (read-only) that `_recover_pending_cascades()` in `reconciliation.py` handles complete Phase B failure. If detection absent, add to `docs/backlog.md`.
   - **Complexity:** Medium — changes commit semantics and requires method body restructuring (not just wrapping)
   - **Files:** `plugins/pd/hooks/lib/workflow_engine/entity_engine.py`
   - **Verification:** All 309 workflow engine tests pass; manual verification that `_run_cascade` uses `transaction()` context manager; reconciliation verification documented

5. **Multi-statement write audit and wrapping** — Wrap methods with 2+ write SQL statements before `_commit()` in `transaction()`
   - **Why this item:** Design C6, Spec FR-4 — protect multi-statement writes from partial visibility under contention
   - **Why this order:** Independent of retry module; can run in parallel with Stage 1
   - **Deliverable:** Audit result documented. Methods executing 2+ write SQL statements (INSERT, UPDATE, DELETE) before calling `_commit()` and not already inside `BEGIN IMMEDIATE` are wrapped in `transaction()`. Note: `delete_entity()` already uses `BEGIN IMMEDIATE` (line 1716) — no changes needed. `set_parent()` executes one UPDATE + one `_commit()` — single-statement write, skip per spec constraint. Focus on `register_entity()` (INSERT entity + INSERT FTS before one `_commit()`) and `update_entity()` (UPDATE + FTS delete/insert before one `_commit()`). Note: Python sqlite3 default isolation wraps these in implicit deferred transactions already — the purpose of wrapping in `transaction()` is to upgrade to `BEGIN IMMEDIATE` for contention-safe eager lock acquisition, preventing `SQLITE_BUSY` on write-upgrade.
   - **Complexity:** Medium — requires grep audit; circuit breaker at 8 sequences
   - **Files:** `plugins/pd/hooks/lib/entity_registry/database.py`
   - **Verification:** All 940+ entity registry tests pass; audit criteria: methods with 2+ write SQL statements before `_commit()` outside `BEGIN IMMEDIATE` are wrapped

### Stage 3: Server Integration
Items depending on Stages 1-2.

6. **Entity server retry integration** — Add `@with_retry("entity")` to all 10 write handlers
   - **Why this item:** Design C2, Spec FR-1 — entity server has zero retry coverage
   - **Why this order:** Depends on item 1 (shared module) and item 3 (validated import pattern)
   - **Deliverable:** Type A handlers (2 in `server_helpers.py`) decorated directly; Type B handlers (8 inline) extracted to sync `_process_*` functions then decorated. Exception handling broadened for `add_okr_alignment`, `create_key_result`, `update_kr_score` to catch `Exception`.
   - **Complexity:** Medium — 10 handlers, 8 need extraction to sync helpers, 3 need broader exception handling
   - **Files:** `plugins/pd/hooks/lib/entity_registry/server_helpers.py`, `plugins/pd/mcp/entity_server.py`
   - **Verification:** Run entity registry tests after each handler extraction to catch regressions early. All 940+ entity registry tests pass at completion. Manual verification each write handler has `@with_retry("entity")`.

7. **Memory server retry integration** — Add `@with_retry("memory")` to 3 write handlers
   - **Why this item:** Design C3, Spec FR-2 — memory server has zero retry coverage
   - **Why this order:** Depends on item 1 (shared module) and item 3 (validated import pattern)
   - **Deliverable:** `_process_store_memory` and `_process_record_influence` decorated; `delete_memory` inline logic extracted to `_process_delete_memory` then decorated. `store_memory` and `record_influence` async handlers get try/except Exception wrappers. Misleading comment at line 128 corrected.
   - **Complexity:** Simple — 3 handlers, 2 already sync helpers, 1 needs extraction
   - **Files:** `plugins/pd/mcp/memory_server.py`
   - **Verification:** All memory server tests pass; misleading comment updated

### Stage 4: Validation
Items depending on all previous stages.

8. **Concurrent-write integration tests** — Validate retry under multi-process contention
   - **Why this item:** Design C8, Spec NFR-1 — verify correctness under real concurrent access
   - **Why this order:** Depends on all previous items — tests the complete integrated behavior
   - **Deliverable:** `plugins/pd/hooks/lib/test_sqlite_retry_integration.py` with multiprocessing tests: N>=3 processes, 10+ writes each, barrier synchronization, row-count verification, exhausted-retry error verification
   - **Complexity:** Complex — multiprocessing coordination, real file-backed SQLite, timing-sensitive
   - **Files:** `plugins/pd/hooks/lib/test_sqlite_retry_integration.py` (new)
   - **Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/test_sqlite_retry_integration.py -v --timeout=60` passes; total completion under 30 seconds

9. **Documentation and CLAUDE.md update** — Add test commands and document changes
    - **Why this item:** CLAUDE.md documentation sync requirement
    - **Why this order:** Last — all code changes must be finalized first
    - **Deliverable:** CLAUDE.md updated with test commands for sqlite_retry unit and integration tests (after entity registry test command block). Reconciliation cascade recovery verification documented (from item 5). If reconciliation gap found, add to `docs/backlog.md`.
    - **Complexity:** Simple — documentation only
    - **Files:** `CLAUDE.md`
    - **Verification:** `./validate.sh` passes; test commands documented

## Dependency Graph

```
Stage 1 (all parallel, no inter-dependencies):
  [1: sqlite_retry.py + tests (TDD)]
  [2: timeout standardization]
  [4: cascade atomicity]
  [5: multi-statement write audit]

Stage 2 (depends on item 1):
  [1] ──→ [3: workflow refactor]

Stage 3 (depends on items 1, 3):
  [1,3] ──→ [6: entity server retry]
  [1,3] ──→ [7: memory server retry]

Stage 4 (depends on all above):
  [1-7] ──→ [8: integration tests]
  [8] ──→ [9: documentation]
```

## Risk Areas

- **Item 5 (cascade atomicity):** Changes commit semantics of `_run_cascade()`. If any downstream code depends on `cascade_unblock` being committed independently of `rollup_parent`, behavior changes. Mitigation: reconciliation already handles complete Phase B failure.
- **Item 6 (multi-step write audit):** May discover more methods than expected. Circuit breaker at 8 — stop and re-evaluate if exceeded.
- **Item 7 (entity server):** 8 handlers need extraction from async to sync helpers. Most complex integration point. Must preserve existing error handling semantics.
- **Item 9 (integration tests):** Multiprocessing tests can be flaky due to timing. Use barrier synchronization (`multiprocessing.Event`) and generous timeout.

## Testing Strategy

- **Unit tests for:** `sqlite_retry.py` — `is_transient` classification, `with_retry` decorator behavior (retry count, backoff sequence, jitter, exhausted propagation)
- **Integration tests for:** concurrent multi-process DB writes using real file-backed SQLite (entity DB and memory DB scenarios)
- **Regression tests:** All existing test suites (entity registry 940+, workflow engine 309, memory server, UI) must continue to pass after changes

## Definition of Done

- [ ] `sqlite_retry.py` shared module exists with unit tests passing
- [ ] `workflow_state_server.py` refactored to import from shared module
- [ ] Entity server: all 10 write handlers have retry coverage
- [ ] Memory server: all 3 write handlers have retry coverage
- [ ] `_run_cascade()` Phase B operations atomic in single transaction
- [ ] Multi-step `_commit()` methods wrapped in `transaction()`
- [ ] `MemoryDatabase` busy_timeout standardized to 15000ms
- [ ] Concurrent-write integration tests pass
- [ ] All existing test suites pass (zero regressions)
- [ ] CLAUDE.md updated with test commands
