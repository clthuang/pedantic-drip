# Plan: MCP Audit — Token Efficiency & Engineering Excellence

## TDD Sub-Order (applies to all items)

Each item follows: (a) update/write tests for new behavior, (b) implement to make tests pass, (c) verify existing tests still pass.

## Implementation Order

### Stage 1: Token Efficiency — Entity Registry (No dependencies, parallel)

1. **export_entities field projection** — P1-C1
   - **Why this item:** Highest-impact token reduction (15-30k → <1k for typical calls)
   - **Why this order:** No dependencies.
   - **Deliverable:** Add `fields` param to `export_entities` MCP tool + `_process_export_entities` in server_helpers. When `fields=None`, full dump preserved. When `fields="type_id,name,status"`, only those fields returned. If all fields invalid, return error listing valid fields (discovered from first entity's keys; empty entity list returns normally).
   - **Complexity:** Simple
   - **Files:** `plugins/iflow/mcp/entity_server.py`, `plugins/iflow/hooks/lib/entity_registry/server_helpers.py`, entity registry tests
   - **TDD:** (a) Add test: `export_entities(fields="type_id,name,status")` returns only 3 fields. Add test: `fields=None` returns all fields. Add test: invalid fields produce error. (b) Implement. (c) Existing entity registry tests pass.
   - **Verification:** New tests pass. Existing tests pass.

2. **get_entity compact output** — P1-C2
   - **Why this item:** ~200 → ~50 tokens per call.
   - **Why this order:** No dependencies.
   - **Deliverable:** Drop `uuid`, `entity_id`, `parent_uuid`. Use `separators=(',',':')`.
   - **Complexity:** Simple
   - **Files:** `plugins/iflow/mcp/entity_server.py`, entity registry tests
   - **TDD:** (a) Update existing get_entity test assertions to expect compact format without uuid/entity_id/parent_uuid. (b) Implement. (c) All tests pass.
   - **Verification:** Updated tests pass.

3. **UUID removal from confirmations** — P1-C3
   - **Why this item:** 36 chars noise removed per message.
   - **Why this order:** No dependencies.
   - **Deliverable:** `register_entity` → `"Registered: {type_id}"`, `update_entity` → `"Updated: {type_id}"`, `set_parent` → `"Parent set: {type_id} → {parent_type_id}"`.
   - **Complexity:** Simple
   - **Files:** `plugins/iflow/mcp/entity_server.py`, `server_helpers.py`, entity registry tests
   - **TDD:** (a) Update test assertions that check confirmation messages. (b) Implement. (c) All tests pass.
   - **Verification:** Updated tests pass.

### Stage 2: Token Efficiency — Workflow Engine (No dependencies, parallel)

4. **_serialize_state cleanup** — P1-C4
   - **Why this item:** Removes ~40% tokens from all state-returning tools.
   - **Why this order:** No dependencies. Single function change.
   - **Deliverable:** `_serialize_state()` drops `completed_phases` and `source`, keeps `degraded` (computed as `state.source == "meta_json_fallback"`).
   - **Complexity:** Medium — 22 `completed_phases` references in test_workflow_state_server.py to update, including dedicated test class `test_completed_phases_tuple_to_list` (line 123) which must be removed.
   - **Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`
   - **Impact confirmation:** test_engine.py and transition_gate tests use `completed_phases` from the `FeatureWorkflowState` model object directly (not from `_serialize_state`), so they are NOT affected by this change. Only `test_workflow_state_server.py` assertions on serialized output need updating.
   - **TDD:** (a) Remove `test_completed_phases_tuple_to_list` test class. Update all assertions that check for `completed_phases` or `source` in serialized state dicts — replace with `degraded` check where applicable. (b) Implement `_serialize_state` change. (c) All 276+ workflow state server tests pass.
   - **Verification:** All tests pass. `grep completed_phases test_workflow_state_server.py` returns zero matches in assertion contexts.

5. **reconcile_status summary mode** — P1-C5
   - **Why this item:** 6k → 20 tokens for health checks.
   - **Why this order:** No dependencies.
   - **Deliverable:** `summary_only=True` returns `{"healthy": bool, "workflow_drift_count": int, "frontmatter_drift_count": int}`. Counts = number of entities with drift status != "in_sync".
   - **Complexity:** Simple
   - **Files:** `plugins/iflow/mcp/workflow_state_server.py`, tests
   - **TDD:** (a) Add test: `reconcile_status(summary_only=True)` returns 3-field JSON. (b) Implement. (c) Existing reconcile tests pass.
   - **Verification:** New + existing tests pass.

6. **reconcile_frontmatter filter in_sync** — P1-C6
   - **Why this item:** 4k → <200 tokens on healthy repos.
   - **Why this order:** No dependencies.
   - **Deliverable:** Default output: `{"total_scanned": N, "drifted_count": M, "reports": [...only drifted...]}`.
   - **Complexity:** Simple
   - **Files:** `plugins/iflow/mcp/workflow_state_server.py`, tests
   - **TDD:** (a) Update existing reconcile_frontmatter test assertions to expect filtered output format. (b) Implement. (c) All tests pass.
   - **Verification:** Updated tests pass.

### Stage 3: Token Efficiency — Memory Server (No dependencies, parallel)

7. **search_memory category filter + brief mode** — P1-C7
   - **Why this item:** `category` halves response; `brief` reduces per-entry from ~100 to ~15 tokens.
   - **Why this order:** No dependencies.
   - **Deliverable:** `category` filters candidates BEFORE ranking (after `db.get_all_entries()`, before `ranking_engine.rank()`). `brief=True` returns only name+confidence. Zero-match category returns empty results (not error).
   - **Complexity:** Medium — category filter integrates into retrieval pipeline between candidate retrieval and ranking.
   - **Files:** `plugins/iflow/mcp/memory_server.py`, memory server tests
   - **TDD:** (a) Add test: `search_memory(category="patterns")` returns only pattern entries. Add test: `brief=True` returns name+confidence only. Add test: non-matching category returns empty. (b) Implement. (c) Existing memory tests pass.
   - **Verification:** New + existing tests pass.

### Stage 4: Library Extraction — EntityDatabase Method (Foundation)

8. **EntityDatabase.upsert_workflow_phase()** — P2-C2
   - **Why this item:** Required by entity_lifecycle.py (item 9). Replaces `db._conn` SQL.
   - **Why this order:** Must precede item 9.
   - **Deliverable:** New public method: `upsert_workflow_phase(type_id, **kwargs)`. Uses `type_id` as PK (NOT entity_uuid — workflow_phases table PK is type_id). ALLOWED_COLUMNS validation. Atomic INSERT OR IGNORE with all fields + UPDATE.
   - **Complexity:** Medium
   - **Files:** `plugins/iflow/hooks/lib/entity_registry/database.py`, entity registry tests
   - **TDD:** (a) Write tests: insert new row, update existing row, reject invalid column name, idempotent re-insert. (b) Implement. (c) Existing 710+ entity registry tests pass.
   - **Verification:** New + existing tests pass.

### Stage 5: Library Extraction — Entity Lifecycle (Depends on Stage 4)

9. **entity_lifecycle.py** — P2-C1
   - **Why this item:** Moves 180 lines of inline `db._conn` logic to testable library.
   - **Why this order:** Depends on upsert_workflow_phase (item 8).
   - **Deliverable:** `entity_lifecycle.py` with full ENTITY_MACHINES (exact copy from workflow_state_server.py), `init_entity_workflow()`, `transition_entity_phase()`. MCP handlers become thin wrappers with `@_with_error_handling`/`@_catch_entity_value_error` decorators retained. Library functions return `dict`; MCP handlers call `json.dumps()`.
   - **Pre-implementation check:** `grep ENTITY_MACHINES workflow_state_server.py` to confirm all references are within the two extracted functions. If other references exist, import ENTITY_MACHINES from entity_lifecycle.py.
   - **Complexity:** Complex — must preserve exact transition graph, forward/backward semantics, entities.status updates.
   - **Files:** `plugins/iflow/hooks/lib/entity_registry/entity_lifecycle.py` (new), `plugins/iflow/mcp/workflow_state_server.py` (thin wrapper), new tests, existing tests
   - **TDD:** (a) Write tests for entity_lifecycle functions: valid transition, invalid transition rejected, forward updates last_completed_phase, backward preserves it, entities.status updated, init idempotent. (b) Implement. (c) All existing 276+ workflow state server tests pass.
   - **Verification:** New + existing tests pass. Zero `db._conn` in the extracted handlers.

### Stage 6: Library Extraction — Remaining (Independent, parallel)

10. **feature_lifecycle.py** — P2-C3
    - **Why this item:** Moves ~230 lines of inline logic to testable library.
    - **Why this order:** Independent — can run parallel with items 9, 11, 12.
    - **Deliverable:** `feature_lifecycle.py` with `init_feature_state`, `init_project_state` (including `features`, `milestones` params), `activate_feature`. Library functions return result dicts including `feature_type_id` and `feature_dir`. MCP handler calls `_project_meta_json(db, engine, result["feature_type_id"])` as post-step using returned values.
    - **Complexity:** Complex — mechanical extraction of large functions. Preserve idempotent retry, kanban fixup, entity registration, all error paths.
    - **Files:** `plugins/iflow/hooks/lib/workflow_engine/feature_lifecycle.py` (new), `plugins/iflow/mcp/workflow_state_server.py` (thin wrapper)
    - **TDD:** (a) Write tests for each function covering happy path and error cases. (b) Extract. (c) All existing tests pass.
    - **Verification:** Existing tests pass. init_feature_state creates entity + .meta.json correctly.

11. **set_parent extraction** — P2-C4
    - **Why this item:** Consistency — all other entity tools use server_helpers.
    - **Why this order:** Independent.
    - **Deliverable:** `server_helpers._process_set_parent(db, type_id, parent_type_id)` + thin MCP wrapper.
    - **Complexity:** Simple — 6 lines.
    - **Files:** `server_helpers.py`, `entity_server.py`
    - **TDD:** (a) Update test assertions if needed. (b) Extract. (c) Tests pass.
    - **Verification:** set_parent works identically.

12. **reconcile_apply direction removal** — P2-C5
    - **Why this item:** Dead surface area.
    - **Why this order:** Independent.
    - **Deliverable:** Remove `direction` from MCP tool signature. Handler hardcodes `"meta_json_to_db"`. Library unchanged.
    - **Complexity:** Simple
    - **Files:** `plugins/iflow/mcp/workflow_state_server.py`
    - **TDD:** (a) Update tests that pass direction param. (b) Remove param. (c) Tests pass.
    - **Verification:** `reconcile_apply()` works without direction.

## Dependency Graph

```
Stages 1-3 (all parallel — 7 items, no inter-dependencies):
  [1: export fields]  [2: get_entity]  [3: UUID]    [7: search_memory]
  [4: serialize_state]  [5: reconcile_status]  [6: reconcile_frontmatter]

Stage 4 → Stage 5 (sequential):
  [8: upsert_workflow_phase] ──→ [9: entity_lifecycle.py]

Stage 6 (parallel, independent of Stages 4-5):
  [10: feature_lifecycle.py]  [11: set_parent]  [12: direction removal]
```

## Risk Areas

- **Item 4:** 22+ test assertion updates in test_workflow_state_server.py. Risk of missing one. Mitigated by running full suite after each change.
- **Item 9:** Most complex extraction — 180 lines of state machine logic. Risk of missing edge case. Mitigated by writing comprehensive tests first (TDD).
- **Item 10:** Largest extraction. `_project_meta_json` coupling — MCP handler calls it post-return using values from library function's result dict.

## Testing Strategy

- **TDD for all items:** Tests written/updated before implementation
- **Existing suites:** entity_registry (710+), workflow_engine (309+), workflow_state_server (276+), memory_server
- **Test assertion updates required:** Items 2, 3, 4, 6 modify existing output formats
- **New tests required:** Items 1, 5, 7, 8, 9, 10

## Definition of Done

- [ ] All 12 items implemented with TDD ordering
- [ ] Entity registry tests passing (710+)
- [ ] Workflow engine tests passing (309+)
- [ ] Workflow state server tests passing (276+)
- [ ] Memory server tests passing
- [ ] Zero `db._conn` access in workflow_state_server.py for entity lifecycle tools
- [ ] ENTITY_MACHINES relocated from workflow_state_server.py to entity_lifecycle.py
