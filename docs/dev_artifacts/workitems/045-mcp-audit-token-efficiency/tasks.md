# Tasks: MCP Audit — Token Efficiency & Engineering Excellence

## Stage 1: Token Efficiency — Entity Registry (Parallel Group A)

### Task 1.1: Add `fields` parameter to `export_entities`
- **Plan item:** 1 (P1-C1)
- **Files:** `plugins/iflow/hooks/lib/entity_registry/server_helpers.py`, `plugins/iflow/mcp/entity_server.py`, entity registry tests
- **Steps:**
  1. Add test: `export_entities(fields="type_id,name,status")` returns only 3 fields per entity
  2. Add test: `fields=None` returns all fields (backward compat)
  3. Add test: all-invalid fields returns error listing valid field names
  4. Add `fields` param to `_process_export_entities()` in `server_helpers.py` — filter after `db.export_entities_json()` returns
  5. Add `fields` param to `export_entities` MCP tool in `entity_server.py`, forward to `_process_export_entities`
  6. Run entity registry tests — all pass
- **Acceptance:** `export_entities(fields="type_id,name,status")` returns only those 3 fields; `fields=None` returns all; invalid fields produce error with valid field list
- **Depends on:** Nothing

### Task 1.2: Compact `get_entity` output
- **Plan item:** 2 (P1-C2)
- **Files:** `plugins/iflow/mcp/entity_server.py`, entity registry tests
- **Steps:**
  1. Update existing `get_entity` test assertions to expect compact JSON without `uuid`, `entity_id`, `parent_uuid`
  2. In `entity_server.py` `get_entity` handler: pop `uuid`, `entity_id`, `parent_uuid` from entity dict; use `json.dumps(entity, separators=(',',':'))` instead of `indent=2`
  3. Run entity registry tests — all pass
- **Acceptance:** `get_entity` response excludes `uuid`, `entity_id`, `parent_uuid`; uses compact JSON (no indent, minimal separators)
- **Depends on:** Nothing

### Task 1.3: Remove UUID from confirmation messages
- **Plan item:** 3 (P1-C3)
- **Files:** `plugins/iflow/mcp/entity_server.py`, `plugins/iflow/hooks/lib/entity_registry/server_helpers.py`, entity registry tests
- **Steps:**
  1. Update test assertions that check confirmation messages for `register_entity`, `update_entity`, `set_parent`
  2. In `server_helpers._process_register_entity`: change return to `f"Registered: {type_id}"`
  3. In `entity_server.py` `update_entity` handler: change return to `f"Updated: {type_id}"`
  4. In `entity_server.py` `set_parent` handler: replace the entire try-block body with `_db.set_parent(type_id, parent_type_id)` then `return f"Parent set: {type_id} → {parent_type_id}"` — remove the `db.get_entity()` UUID lookup calls (`child_uuid`, `child`, `parent` variables are no longer needed)
  5. Run entity registry tests — all pass
- **Acceptance:** No UUID appears in any confirmation message; only `type_id` used
- **Depends on:** Nothing

## Stage 2: Token Efficiency — Workflow Engine (Parallel Group B)

### Task 2.1: Clean up `_serialize_state` — drop `completed_phases` and `source`
- **Plan item:** 4 (P1-C4)
- **Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`
- **Steps:**
  1. Remove `test_completed_phases_tuple_to_list` test class from `test_workflow_state_server.py`
  2. Find all ~22 test assertions checking `completed_phases` or `source` in serialized state dicts — remove or replace with `degraded` check
  3. Modify `_serialize_state()`: remove `completed_phases` and `source` keys, add `"degraded": state.source == "meta_json_fallback"`
  4. Run workflow state server tests — all 276+ pass
  5. Verify: `grep -n 'completed_phases' test_workflow_state_server.py | grep -v 'completed_phases=('` returns zero hits
- **Acceptance:** `_serialize_state` output has `degraded: bool`, no `completed_phases`, no `source`; all tests pass
- **Depends on:** Nothing

### Task 2.2: Add `summary_only` mode to `reconcile_status`
- **Plan item:** 5 (P1-C5)
- **Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`
- **Steps:**
  1. Add test: `reconcile_status(summary_only=True)` returns `{"healthy": bool, "workflow_drift_count": int, "frontmatter_drift_count": int}`
  2. Add `summary_only` param to `reconcile_status` MCP tool and `_process_reconcile_status`
  3. Implement early return in `_process_reconcile_status` when `summary_only=True` — count entities with drift status != "in_sync"
  4. Run workflow state server tests — all pass
- **Acceptance:** `summary_only=True` returns exactly 3 fields; `summary_only=False` (default) returns full report unchanged
- **Depends on:** Nothing

### Task 2.3: Filter `in_sync` reports from `reconcile_frontmatter`
- **Plan item:** 6 (P1-C6)
- **Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`
- **Steps:**
  1. Update existing `reconcile_frontmatter` test assertions to expect new output format: `{"total_scanned": N, "drifted_count": M, "reports": [...only drifted...]}`. Remove assertions that check for `summary` key — the new envelope replaces `summary` with `total_scanned` and `drifted_count` as top-level integers. Update `summary`-related test helpers if any.
  2. Modify `_process_reconcile_frontmatter`: filter out `in_sync` reports, drop old `summary` key, wrap in new envelope with `total_scanned`, `drifted_count`, `reports`
  3. Run workflow state server tests — all pass
- **Acceptance:** Default output only contains drifted reports; no `summary` key; `total_scanned` reflects all scanned; `drifted_count` matches filtered list length
- **Depends on:** Nothing

## Stage 3: Token Efficiency — Memory Server (Parallel Group C)

### Task 3.1: Add `category` filter and `brief` mode to `search_memory`
- **Plan item:** 7 (P1-C7)
- **Files:** `plugins/iflow/mcp/memory_server.py`, memory server tests
- **Steps:**
  1. Add test: `search_memory(query="...", category="patterns")` returns only pattern entries
  2. Add test: `search_memory(query="...", brief=True)` returns plain-text output with `- {name} ({confidence})` per line
  3. Add test: non-matching category returns empty results (not error)
  4. Update `_process_search_memory` signature to: `def _process_search_memory(db, provider, config, query, limit, category=None, brief=False)`. Update `search_memory` MCP tool to forward `category` and `brief` params.
  5. Implement: category filter applies to `all_entries` after `db.get_all_entries()` but before building `entries_by_id` / `ranking_engine.rank()`. Brief mode returns plain-text lines (`"\n".join(lines)`) not JSON, format: `"Found {n} entries:\n- {name} ({confidence})\n..."`.
  6. Run memory server tests — all pass
- **Acceptance:** Category filters candidates pre-ranking; brief returns plain-text (not JSON), one line per entry: `- {name} ({confidence})`; zero-match category returns empty (not error)
- **Depends on:** Nothing

## Stage 4: Library Extraction — EntityDatabase Method (Foundation)

### Task 4.1: Add `upsert_workflow_phase()` to `EntityDatabase`
- **Plan item:** 8 (P2-C2)
- **Files:** `plugins/iflow/hooks/lib/entity_registry/database.py`, entity registry tests
- **Steps:**
  1. Write tests: insert new row, update existing row, reject invalid column name, idempotent re-insert
  2. Implement `upsert_workflow_phase(type_id, **kwargs)` in `database.py`: ALLOWED_COLUMNS validation, INSERT OR IGNORE + UPDATE, atomic with commit
  3. Run entity registry tests — all 710+ pass
- **Acceptance:** New method inserts new rows, updates existing rows, rejects invalid column names; all existing tests pass
- **Depends on:** Nothing

## Stage 5: Library Extraction — Entity Lifecycle (Sequential)

### Task 5.1: Create `entity_lifecycle.py` with `init_entity_workflow` and `transition_entity_phase`
- **Plan item:** 9 (P2-C1)
- **Files:** `plugins/iflow/hooks/lib/entity_registry/entity_lifecycle.py` (new), `plugins/iflow/mcp/workflow_state_server.py`, new tests, existing tests
- **Steps:**
  1. Write unit tests in `test_entity_lifecycle.py`: valid transition, invalid transition rejected, forward updates `last_completed_phase`, backward preserves it, `entities.status` updated, init idempotent, feature/project types rejected
  2. Create `entity_lifecycle.py` with `ENTITY_MACHINES` (exact copy from workflow_state_server.py), `init_entity_workflow()`, `transition_entity_phase()`
  3. In `workflow_state_server.py`: replace `_process_init_entity_workflow` and `_process_transition_entity_phase` with thin wrappers. Wrapper pattern: `return json.dumps(entity_lifecycle.init_entity_workflow(_db, type_id, workflow_phase, kanban_column))`. Library returns dict, wrapper serializes to JSON string. Retain `@_with_error_handling`/`@_catch_entity_value_error` decorators — they catch `ValueError` from library and return structured error JSON.
  4. Add re-export: `from entity_registry.entity_lifecycle import ENTITY_MACHINES` in `workflow_state_server.py` (test import compat)
  5. Run all workflow state server tests (276+) — pass
  6. Run new entity lifecycle unit tests — pass
  7. Verify: `python -c 'from workflow_state_server import ENTITY_MACHINES'` succeeds
  8. Verify: zero `db._conn` in extracted handlers
- **Acceptance:** `ENTITY_MACHINES` lives in `entity_lifecycle.py`; MCP handlers are thin wrappers; no `db._conn` in MCP server for these tools; all tests pass
- **Depends on:** Task 4.1

## Stage 6: Library Extraction — Remaining (Parallel Group D)

### Task 6.1: Create `feature_lifecycle.py` with `init_feature_state`, `init_project_state`, `activate_feature`
- **Plan item:** 10 (P2-C3)
- **Files:** `plugins/iflow/hooks/lib/workflow_engine/feature_lifecycle.py` (new), `plugins/iflow/mcp/workflow_state_server.py`, new tests, existing tests
- **Steps:**
  1. Write unit tests in `test_feature_lifecycle.py` for each function: happy path and error cases
  2. Create `feature_lifecycle.py` — mechanical extraction of `_process_init_feature_state`, `_process_init_project_state`, `_process_activate_feature`; replace globals with params
  3. In `workflow_state_server.py`: replace `_process_*` functions with thin wrappers. Per-wrapper patterns: **init_feature_state:** `result = feature_lifecycle.init_feature_state(...); _project_meta_json(db, engine, result["feature_type_id"]); return json.dumps(result)`. **init_project_state:** `result = feature_lifecycle.init_project_state(...); _project_meta_json(db, engine, result["project_type_id"]); return json.dumps(result)`. **activate_feature:** `result = feature_lifecycle.activate_feature(...); _project_meta_json(db, engine, result["feature_type_id"]); return json.dumps(result)`. Verify each library function returns the expected key before wiring.
  4. Library signature: `features` and `milestones` are required `str` params in `init_project_state` (matching source, not optional)
  5. Run all workflow state server tests — pass
  6. Run new feature lifecycle unit tests — pass
- **Acceptance:** Business logic in library module; MCP handlers contain only null-check, forwarding, return formatting, `_project_meta_json` post-step; all tests pass
- **Depends on:** Nothing (independent of Stage 5)

### Task 6.2: Extract `set_parent` to `server_helpers`
- **Plan item:** 11 (P2-C4)
- **Files:** `plugins/iflow/hooks/lib/entity_registry/server_helpers.py`, `plugins/iflow/mcp/entity_server.py`
- **Steps:**
  1. **Pre-condition:** Verify Task 1.3 is complete — confirm `set_parent` handler no longer contains UUID lookup calls (`child_uuid`, `child`, `parent` variables). If still present, complete Task 1.3 first. Then add `_process_set_parent(db, type_id, parent_type_id)` to `server_helpers.py` — calls only `db.set_parent(type_id, parent_type_id)` and returns `f"Parent set: {type_id} → {parent_type_id}"`.
  2. Update `entity_server.py` `set_parent` handler to delegate to `server_helpers._process_set_parent`
  3. Run entity registry tests — all pass
- **Acceptance:** `set_parent` MCP handler delegates to `server_helpers._process_set_parent`; behavior identical
- **Depends on:** Task 1.3 (confirmation format change must be done first)

### Task 6.3: Remove `direction` param from `reconcile_apply` MCP tool
- **Plan item:** 12 (P2-C5)
- **Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`
- **Steps:**
  1. Remove `test_invalid_direction_returns_error` (line ~2357) and `test_error_invalid_direction` (line ~2744) from test file
  2. Remove explicit `direction=` kwargs from ~10 remaining test call-sites
  3. Remove `direction` param from `reconcile_apply` MCP tool signature; hardcode `"meta_json_to_db"` in handler
  4. Library function `apply_workflow_reconciliation` keeps its `direction` param unchanged
  5. Run workflow state server tests — all pass
  6. Verify: `grep -n 'direction' test_workflow_state_server.py | grep -v '_SUPPORTED\|import'` returns zero MCP-level direction assertions
- **Acceptance:** No `direction` param in MCP tool; library function unchanged; all tests pass
- **Depends on:** Nothing

## Dependency Graph

```
Parallel Group A (Stage 1): [1.1] [1.2] [1.3]
Parallel Group B (Stage 2): [2.1] [2.2] [2.3]
Parallel Group C (Stage 3): [3.1]
Foundation (Stage 4):       [4.1]
Sequential (Stage 5):       [4.1] → [5.1]
Parallel Group D (Stage 6): [6.1] [6.3]  (parallel)
Sequential in Group D:      [1.3] → [6.2]
```

**Explicit dependencies:**
- Task 5.1 depends on Task 4.1 (needs `upsert_workflow_phase`)
- Task 6.2 depends on Task 1.3 (confirmation format change must precede extraction)

**File concurrency constraints:**
- `entity_server.py`: Tasks 1.1, 1.2, 1.3, 6.2 — serialize within file
- `workflow_state_server.py`: Tasks 2.1, 2.2, 2.3, 5.1, 6.1, 6.3 — serialize within file
- `server_helpers.py`: Tasks 1.1, 1.3, 6.2 — serialize within file

## Summary

- **Total tasks:** 12
- **Parallel groups:** 4 (A, B, C, D) + 1 sequential chain (4→5)
- **Estimated per-task size:** 5-15 min each
- **TDD ordering:** Tests written/updated before implementation in every task
