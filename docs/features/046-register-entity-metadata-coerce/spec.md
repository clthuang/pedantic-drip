# Specification: register_entity metadata dict coercion

## Rationale
RCA report: `docs/rca/20260318-register-entity-metadata-dict.md`. The `register_entity` and `update_entity` MCP tools declare `metadata: str | None` which causes Pydantic validation errors when LLMs pass dicts (a frequent misfire). Three root causes: strict type annotation, ambiguous command template quoting, and incomplete CLAUDE.md documentation.

## Problem Statement
LLMs consistently pass `metadata` as a dict to `register_entity` and `update_entity`, causing Pydantic `ValidationError: Input should be a valid string`. The `add-to-backlog` command template's quoting pattern amplifies this by visually resembling Python dict syntax.

## Success Criteria
- [ ] `register_entity(metadata={"key": "value"})` succeeds (dict auto-coerced to JSON string)
- [ ] `register_entity(metadata='{"key": "value"}')` continues to work (string path unchanged)
- [ ] `register_entity(metadata=None)` continues to work (None path unchanged)
- [ ] `update_entity` has the same coercion behavior
- [ ] `add-to-backlog.md` template uses unambiguous metadata format
- [ ] CLAUDE.md gotcha updated to mention both tools
- [ ] Existing tests pass after changes

## Scope

### In Scope
1. Change `metadata: str | None = None` to `metadata: str | dict | None = None` in both `register_entity` and `update_entity` MCP tool signatures in `entity_server.py`
2. Add dict-to-JSON-string coercion before calling `_process_register_entity` / passing to `parse_metadata` — `if isinstance(metadata, dict): metadata = json.dumps(metadata)`
3. Update `add-to-backlog.md` template to pass metadata as a Python dict literal — e.g., `metadata={"description": "{full-description}"}` — removing the outer quotes entirely (dicts are now accepted, directly addressing RC-2)
4. Update CLAUDE.md gotcha to mention both `register_entity` and `update_entity`, noting that dicts are now accepted

### Out of Scope
- Changing `parse_metadata` in `server_helpers.py` — it is shared across tools and its string-only contract is intentional (graceful error handling path); coercion belongs at the MCP tool boundary only
- Changing the database layer `EntityDatabase.register_entity` signature
- Adding dict support to any other MCP tool parameters

## Acceptance Criteria

### AC-1: Dict metadata accepted by register_entity
- Given a call to `register_entity` with `metadata={"description": "test"}`
- When the tool executes
- Then it succeeds, entity is registered, metadata stored as JSON string in DB

### AC-2: Dict metadata accepted by update_entity
- Given a call to `update_entity` with `metadata={"key": "value"}`
- When the tool executes
- Then it succeeds, entity metadata updated, new metadata stored as JSON string in DB (verifiable via `get_entity`)

### AC-3: String metadata still works
- Given a call to `register_entity` with `metadata='{"description": "test"}'`
- When the tool executes
- Then behavior is identical to current (no regression)

### AC-4: None metadata still works
- Given a call to `register_entity` with `metadata=None`
- When the tool executes
- Then metadata is not set (no regression)

### AC-5: add-to-backlog template updated
- Given the `add-to-backlog.md` command file
- When inspected
- Then the `metadata` parameter is passed as a plain dict literal (no outer quotes), directly leveraging the new dict acceptance

### AC-6: CLAUDE.md gotcha updated
- Given the CLAUDE.md knowledge section
- When inspected
- Then the gotcha text accurately states that both tools accept dict or JSON string, and recommends dict format as the preferred call pattern

### AC-7: Invalid JSON string still handled gracefully
- Given a call to `register_entity` with `metadata="{bad json}"`
- When the tool executes
- Then it succeeds (no crash), entity is registered, metadata stored as `{"error": "..."}` dict (existing `parse_metadata` behavior unchanged)

## Feasibility Assessment
**Overall:** Confirmed via reproduction script (`agent_sandbox/20260318/rca-register-entity-metadata/reproduction/repro.py`) and schema verification experiment. Change is isolated to two call sites in `entity_server.py`; `parse_metadata` and database layers are untouched.

## Dependencies
- Entity registry test suite (757+ tests)
