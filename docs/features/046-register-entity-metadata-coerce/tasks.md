# Tasks: register_entity metadata dict coercion

## Stage 1: Core Fix

### Task 1.1: Add dict coercion + tests + docstrings for register_entity and update_entity
- **Plan item:** 1 (C1)
- **Files:** `plugins/iflow/mcp/entity_server.py`, `plugins/iflow/hooks/lib/entity_registry/test_entity_server.py`
- **Steps:**
  1. Add 5 tests to `test_entity_server.py`: `test_register_entity_metadata_dict` (pass dict, verify JSON string in DB), `test_register_entity_metadata_string` (JSON string passthrough), `test_register_entity_metadata_none` (None passthrough), `test_update_entity_metadata_dict` (dict update stored as JSON), `test_register_entity_metadata_invalid_json_string` (graceful error via parse_metadata, annotate as `derived_from: server_helpers:parse_metadata`)
  2. In `entity_server.py` `register_entity`: change `metadata: str | None = None` to `metadata: str | dict | None = None`. Add `if isinstance(metadata, dict): metadata = json.dumps(metadata)` as a standalone statement before line 144 (the `_process_register_entity` call). Note: `parse_metadata(metadata)` is called inline as an argument at line 147 — the coercion must run before this entire call so parse_metadata receives a string.
  3. Same change for `update_entity` (line ~224): type annotation + coercion as standalone statement before the `_db.update_entity(...)` call where `parse_metadata(metadata)` is called inline at line 249.
  4. Update `register_entity` docstring (line ~137): `"Optional JSON string of additional metadata."` → `"Optional metadata — pass a dict (preferred) or a JSON string; dicts are auto-coerced to JSON."`
  5. Update `update_entity` docstring (line ~239): `"JSON string of metadata to shallow-merge."` → `"Metadata to shallow-merge — pass a dict (preferred) or a JSON string; dicts are auto-coerced. Empty dict '{}' clears."`
  6. Run entity registry tests — all 757+ pass
  7. Verify FastMCP schema: inspect generated schema for `metadata` param includes both `string` and `object` types. If not, fall back to `Any = None` with manual isinstance checks.
- **Acceptance:** Dict metadata accepted without Pydantic error; string/None paths unchanged; 5 new tests pass; all existing tests pass
- **Depends on:** Nothing

## Stage 2: Template + Doc Updates (parallel)

### Task 2.1: Update add-to-backlog.md template
- **Plan item:** 2 (C2)
- **Files:** `plugins/iflow/commands/add-to-backlog.md`
- **Steps:**
  1. Find the metadata kwarg in the register_entity call (line ~51)
  2. Replace `metadata='{"description": "{full-description}"}'` with `metadata={"description": "{full-description}"}`
  3. Visual inspection: no outer quotes around metadata value
- **Acceptance:** Template passes metadata as dict literal (no outer quotes)
- **Depends on:** Task 1.1

### Task 2.2: Update CLAUDE.md gotcha
- **Plan item:** 3 (C3)
- **Files:** `CLAUDE.md`
- **Steps:**
  1. Find the entity registry MCP metadata gotcha entry
  2. Replace with: `**Entity registry MCP metadata gotcha:** register_entity and update_entity accept metadata as either a dict or JSON string (dict preferred). Internally coerced to JSON string via json.dumps() before parse_metadata.`
- **Acceptance:** Gotcha mentions both tools, states dict is preferred, explains coercion
- **Depends on:** Task 1.1 (documents behavior that only exists after coercion is implemented)

## Dependency Graph

```
Stage 1: [1.1]
Stage 2: [2.1] [2.2]  (parallel, both after 1.1)
```

## Summary

- **Total tasks:** 3
- **Parallel groups:** 1 (Stage 2)
- **Per-task size:** 5-10 min each
- **TDD ordering:** Tests written before implementation in Task 1.1
