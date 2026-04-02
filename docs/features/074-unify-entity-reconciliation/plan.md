# Plan: Unify Entity Reconciliation

## Implementation Order

### Stage 1: Tests First, Then Implementation (TDD)

1. **Write unit tests for _sync_backlog_entities()** — Test-first
   - **Why this item:** TDD: define expected behavior before implementation
   - **Why this order:** Must precede item 2 (implementation)
   - **Deliverable:** Test cases in test_entity_status.py: parse row with (closed:)→dropped, (promoted→)→promoted, (fixed:)→dropped, (already implemented)→dropped, no marker→open, junk ID deletion (including delete_entity ValueError when entity has children), same-project dedup, missing backlog.md returns empty
   - **Complexity:** Simple (test fixtures with mock DB)
   - **Files:** `reconciliation_orchestrator/test_entity_status.py`
   - **Verification:** Tests exist and fail (RED phase)

2. **Implement _sync_backlog_entities() helper** — Make tests pass
   - **Why this item:** Design C2/I2 — the core missing functionality
   - **Why this order:** After item 1 (TDD GREEN phase)
   - **Deliverable:** New private function in entity_status.py that reads backlog.md, parses rows with BACKLOG_ROW_RE, detects status markers (including `(already implemented` — align with `doctor/checks.py` regex patterns), registers/updates entities following `backfill.py:_scan_backlog()` canonical two-step pattern (register_entity + update_entity). Includes junk cleanup (I3, catch ValueError from delete_entity for entities with children) and dedup (I4). Uses `db.list_entities()` (not search_entities). Uses `project_root` for path resolution (not full_artifacts_path/..).
   - **Complexity:** Medium (regex parsing + DB operations + cleanup logic)
   - **Files:** `reconciliation_orchestrator/entity_status.py`
   - **Verification:** All item 1 tests pass (GREEN phase)

3. **Write tests + implement _sync_brainstorm_entities()** — Absorb brainstorm_registry + missing-file detection
   - **Why this item:** Design C1/I5 — merge existing code + add AC-9
   - **Why this order:** Independent of items 1-2, parallel
   - **Deliverable:** Tests for: register new brainstorm, skip existing, archive missing file. Implementation: copy brainstorm_registry.py logic + add missing-file detection using `os.path.join(project_root, artifact_path)` for path resolution (not full_artifacts_path/..)
   - **Complexity:** Simple
   - **Files:** `reconciliation_orchestrator/entity_status.py`, `reconciliation_orchestrator/test_entity_status.py`
   - **Verification:** Tests pass

### Stage 2: Integration (depends on Stage 1)

4. **Refactor sync_entity_statuses() to call all 4 helpers** — Unified entry point
   - **Why this item:** Design C1/I1 — single function handling all entity types
   - **Why this order:** After items 1-2 (helpers must exist)
   - **Deliverable:** Updated sync_entity_statuses with new `artifacts_root` parameter, calling _sync_meta_json_entities (features+projects), _sync_brainstorm_entities, _sync_backlog_entities. Aggregated return dict with registered/deleted counts.
   - **Complexity:** Simple (orchestration wrapper)
   - **Files:** `reconciliation_orchestrator/entity_status.py`
   - **Verification:** Integration test: full sync on test fixtures with all 4 entity types

5. **Update orchestrator __main__.py** — Remove Task 2, pass artifacts_root
   - **Why this item:** Design C3 — orchestrator calls unified function
   - **Why this order:** After item 3 (needs unified function)
   - **Deliverable:** Remove brainstorm_registry import and Task 2 call. Add artifacts_root parameter to Task 1 call. Remove brainstorm_sync key from results dict.
   - **Complexity:** Simple (4 lines changed)
   - **Files:** `reconciliation_orchestrator/__main__.py`
   - **Verification:** Run orchestrator CLI, verify single entity_sync output with registered/deleted counts

### Stage 3: Cleanup (depends on Stage 2) — atomic step

6. **Delete brainstorm_registry + update tests + regression** — Atomic cleanup
   - **Why this item:** Design C4 — module absorbed. Tests must be updated in the same step to avoid broken test window.
   - **Why this order:** After item 4 (no more imports). Done as one atomic commit.
   - **Deliverable:** (a) Update test_orchestrator.py: remove brainstorm_sync assertions, assert entity_sync includes registered/deleted counts. Also verify test_entity_status.py works with new `artifacts_root` parameter (default "docs" provides backward compat). (b) Delete brainstorm_registry.py and test_brainstorm_registry.py. (c) Run full regression.
   - **Complexity:** Simple (test updates + file deletion)
   - **Files:** `reconciliation_orchestrator/brainstorm_registry.py` (delete), `reconciliation_orchestrator/test_brainstorm_registry.py` (delete), `reconciliation_orchestrator/test_orchestrator.py` (update)
   - **Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/reconciliation_orchestrator/ plugins/pd/hooks/lib/entity_registry/ -v` — all pass

7. **Regression test run** — Full test suite
   - **Why this item:** Zero regression verification
   - **Why this order:** After all changes
   - **Deliverable:** Clean test run
   - **Complexity:** Simple
   - **Files:** None
   - **Verification:** All entity_registry + reconciliation_orchestrator tests pass

## Dependency Graph

```
Item 1 (tests) ──→ Item 2 (backlog impl) ──→ Item 4 (unified fn) ──→ Item 5 (orchestrator) ──→ Item 6 (atomic cleanup + regression) ──→ Item 7 (regression)
Item 3 (brainstorm tests+impl) ──→ Item 4
```

## Risk Areas

- **Item 1 (backlog parsing):** Regex must handle all backlog.md row variants including `(already implemented`. Mitigation: align with `doctor/checks.py` regex patterns (most comprehensive); test against actual backlog.md content.
- **Item 2 (junk cleanup):** `delete_entity` raises `ValueError` for entities with children. Mitigation: wrap in try/except, log warning, skip undeletable entities.
- **Item 6 (deletion):** Must verify no hidden imports before deleting. Mitigation: grep for brainstorm_registry across entire codebase.

## Prior Art

- `backfill.py:_scan_backlog()` — canonical backlog parser (line 364). Uses pipe-split, register+update two-step pattern. Reference implementation for _sync_backlog_entities().
- `doctor/checks.py:796` — most comprehensive status regex: `r'\((?:closed|fixed|already implemented)[:\s—]'`. Use as authoritative reference.

## Testing Strategy

- **Unit tests:** Items 1-2 — test each helper independently with fixture data
- **Integration tests:** Item 3 — test unified function with all 4 entity types
- **Regression tests:** Item 7 — full test suite

## Definition of Done

- [ ] Backlog items in backlog.md are synced to entity registry with correct statuses
- [ ] Junk backlog entities (non-5-digit IDs) deleted from DB
- [ ] Same-project duplicate backlogs deduplicated
- [ ] Brainstorm registration absorbed from brainstorm_registry.py
- [ ] Missing brainstorm .prd.md files detected → entity status set to "archived"
- [ ] brainstorm_registry.py and its tests deleted
- [ ] Orchestrator outputs single entity_sync key
- [ ] All tests pass (zero regression)
