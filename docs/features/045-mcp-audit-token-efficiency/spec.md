# Specification: MCP Audit — Token Efficiency & Engineering Excellence

## Rationale (in lieu of PRD)
This feature originates from a direct audit of MCP tool usage in show-status, which revealed `export_entities` returning ~12.2k tokens for 63 entities when only 3 non-completed entities were needed. The audit expanded to all 3 MCP servers (25 tools total) and found systemic issues: verbose responses, UUID leakage in confirmations, and 8 tools with inline business logic violating the thin-wrapper principle. No PRD was created because this is an internal engineering audit with clear, enumerable scope.

## Problem Statement
iflow's 3 MCP servers (entity-registry, workflow-engine, memory) have 25 tools with two systemic issues:
1. **Token waste:** Several tools return verbose responses (UUIDs, full metadata, indent=2, in_sync reports) — measured at 1k-30k tokens per call when callers need <100 tokens
2. **Inline business logic:** 8 tools have logic directly in MCP handlers instead of library backends, making them untestable without MCP and violating the thin-wrapper principle

## Tool Inventory

### Entity Registry (8 tools)
| Tool | Phase 1 (tokens) | Phase 2 (extraction) | Current Issues |
|------|-----------------|---------------------|----------------|
| register_entity | UUID in response | Already in server_helpers | |
| set_parent | UUID in response | Extract to server_helpers | Inline logic |
| get_entity | Full dump, indent=2 | — | ~200 tokens vs ~50 needed |
| get_lineage | OK | — | |
| update_entity | UUID in response | — | |
| export_lineage_markdown | — | — | |
| export_entities | **15-30k tokens** | — | No field projection |
| search_entities | OK | — | Already concise |

### Workflow Engine (15 tools)
| Tool | Phase 1 (tokens) | Phase 2 (extraction) | Current Issues |
|------|-----------------|---------------------|----------------|
| get_phase | Drop `source` | — | |
| transition_phase | Drop `source` | — | |
| complete_phase | Drop `source` | — | |
| validate_prerequisites | — | — | |
| list_features_by_phase | Drop `completed_phases` | — | ~1.4k tokens |
| list_features_by_status | Drop `completed_phases` | — | ~1.4k tokens |
| reconcile_check | — | — | |
| reconcile_apply | — | Remove dead `direction` param | |
| reconcile_frontmatter | Filter in_sync | — | ~4k tokens |
| reconcile_status | Add summary_only | — | ~6k tokens |
| init_feature_state | — | Extract to library | Inline logic |
| init_project_state | — | Extract to library | Inline logic |
| activate_feature | — | Extract to library | Inline logic |
| init_entity_workflow | — | Extract to library | `db._conn` access |
| transition_entity_phase | — | Extract to library | `db._conn` access |

### Memory (2 tools)
| Tool | Phase 1 (tokens) | Phase 2 (extraction) | Current Issues |
|------|-----------------|---------------------|----------------|
| store_memory | OK | — | Already has CLI backend |
| search_memory | Add category filter, brief mode | — | ~800-1.2k tokens |

## Success Criteria
- [ ] All MCP tools delegate to library functions (zero inline business logic in MCP handlers)
- [ ] `export_entities` supports `fields` parameter for projection
- [ ] `get_entity` returns concise output (drop uuid, entity_id, parent_uuid, compact JSON)
- [ ] `reconcile_status` supports `summary_only` mode
- [ ] `reconcile_frontmatter` filters out `in_sync` reports by default
- [ ] `list_features_by_phase/status` drop `completed_phases` array from response
- [ ] `search_memory` supports optional `category` filter and `brief` mode
- [ ] UUID removed from confirmation messages
- [ ] All inline entity lifecycle logic moved to library
- [ ] Existing tests pass after refactoring

## Scope

### In Scope

**Phase 1 — Token efficiency (high impact, low risk):**
- Add `fields` projection to `export_entities` — new optional param, default=None preserves current full-dump behavior for backward compatibility
- Add `summary_only` param to `reconcile_status`
- Filter `in_sync` reports from `reconcile_frontmatter` default output
- Drop `completed_phases` from list_features_by_phase/status responses
- Compact `get_entity` output (drop uuid, entity_id, parent_uuid; use `separators=(',',':')`)
- Remove UUID from confirmation messages
- Remove `source` field from `_serialize_state()` (keep `degraded` only)
- Add `category` filter to `search_memory`
- Add `brief` mode to `search_memory` (name+confidence only)

**Phase 2 — Library extraction (medium risk):**
- Extract `set_parent` to a `_process_set_parent` function in `server_helpers` (consistency — all other entity tools use server_helpers)
- Extract `init_entity_workflow` + `transition_entity_phase` to `hooks/lib/entity_registry/entity_lifecycle.py`
- Extract `init_feature_state` / `init_project_state` / `activate_feature` to `hooks/lib/workflow_engine/feature_lifecycle.py`
- Replace `db._conn` private access with new `EntityDatabase` public methods
- Remove vestigial `direction` param from `reconcile_apply` MCP tool (only one value supported) MCP tool (library function keeps param, MCP hardcodes `"meta_json_to_db"`)

**Phase 1 and Phase 2 have no technical dependencies.** Recommended order: Phase 1 first (highest impact, lowest risk).

### Out of Scope
- Adding pagination to list tools (separate feature)
- Caching `db.get_all_entries()` in memory server
- Adding `score` transparency to `search_memory`
- Deduplicating validation logic between `store_memory` and `semantic_memory.writer`
- Adding new MCP tools

## Acceptance Criteria

### AC-1: export_entities field projection
- Given `export_entities(entity_type="feature", fields="type_id,name,status")`
- When called with 50 features
- Then response contains exactly the 3 requested fields per entity and no others
- When `fields` param is omitted (None), response contains all fields (current behavior preserved)

### AC-2: get_entity concise output
- Given `get_entity(type_id="feature:043-state-consistency-consolid")`
- When called
- Then response JSON excludes `uuid`, `entity_id`, `parent_uuid`; uses compact JSON (`separators=(',',':')`, no indent)

### AC-3: reconcile_status summary mode
- Given `reconcile_status(summary_only=true)`
- When called on a healthy repo
- Then response is `{"healthy": true, "workflow_drift_count": 0, "frontmatter_drift_count": 0}` where counts are integers representing number of entities with drift status != "in_sync"

### AC-4: reconcile_frontmatter filters in_sync
- Given `reconcile_frontmatter()` on a repo with 50 artifacts, 48 in_sync
- When called
- Then response contains only the 2 drifted reports (reports with status == "in_sync" are excluded)

### AC-5: list_features compact response
- Given `list_features_by_phase(phase="implement")`
- When called
- Then each feature in response has `feature_type_id`, `current_phase`, `last_completed_phase`, `mode`, `degraded` — no `completed_phases` array, no `source` field (reflects AC-9 changes)

### AC-6: UUID removed from confirmations
- Given `register_entity(...)` or `update_entity(...)` or `set_parent(...)`
- When called successfully
- Then response message contains type_id only, no UUID

### AC-7: search_memory category filter
- Given `search_memory(query="hook development", category="patterns")`
- When called
- Then results contain only entries with category "patterns"

### AC-8: search_memory brief mode
- Given `search_memory(query="hook development", brief=true)`
- When called
- Then each result contains only `name` and `confidence` fields — no description, reasoning, or references

### AC-9: serialize_state drops source field
- Given any workflow engine tool that returns state (get_phase, transition_phase, complete_phase, list_features_*)
- When called
- Then response contains `degraded: bool` but no `source` field

### AC-10: Entity lifecycle extracted to library
- Given `init_entity_workflow` and `transition_entity_phase` tools
- When their MCP handlers are examined
- Then they delegate to functions in `hooks/lib/entity_registry/entity_lifecycle.py`:
  - `init_entity_workflow(db: EntityDatabase, type_id: str, workflow_phase: str, kanban_column: str) -> dict`
  - `transition_entity_phase(db: EntityDatabase, type_id: str, target_phase: str) -> dict`
- And no `db._conn` private access exists in MCP server code for these tools

### AC-11: Feature lifecycle extracted to library
- Given `init_feature_state`, `init_project_state`, `activate_feature` tools
- When their MCP handlers are examined
- Then business logic is in functions in `hooks/lib/workflow_engine/feature_lifecycle.py`
- MCP handlers contain only: `_db`/`_engine` None check, argument forwarding, return formatting — no JSON parsing, no entity registration, no validation beyond what MCP provides

### AC-12: db._conn replacement
- Given the extracted entity_lifecycle.py functions
- When they interact with workflow_phases table
- Then they use new `EntityDatabase` public methods (not `db._conn`):
  - `db.get_workflow_phase(type_id) -> dict | None` (exists at database.py:1320)
  - `db.update_workflow_phase(type_id, **kwargs)` (exists at database.py:1330)
  - Note: `upsert_workflow_phase` does NOT exist — the inline code uses `INSERT OR IGNORE` + `UPDATE`. A new `db.upsert_workflow_phase(type_id, phase, column)` method must be added to `EntityDatabase` as part of this feature to replace the raw SQL.

### AC-13: Existing tests pass
- Given all refactoring is complete
- When existing test suites run:
  - Entity registry: 710+ tests
  - Workflow engine: 309+ tests
  - Workflow state server: 276+ tests
  - Memory server tests
- Then all tests pass

### AC-14: reconcile_apply direction param removed from MCP
- Given `reconcile_apply` MCP tool
- When called
- Then no `direction` parameter exists in the MCP tool signature
- The library function `apply_workflow_reconciliation` keeps its `direction` param; the MCP handler hardcodes `"meta_json_to_db"`

### AC-15: set_parent extraction
- Given `set_parent` MCP tool in entity_server.py
- When its handler is examined
- Then it delegates to `server_helpers._process_set_parent()` (consistency with all other entity tools)

## Feasibility Assessment

**Overall:** Confirmed
**Reasoning:** Phase 1 changes are additive (new optional params with backward-compatible defaults). Phase 2 is mechanical refactoring (move functions to library modules, update imports). All existing tests verify current behavior and will catch regressions.
**Breaking change note:** `get_entity` output format changes (AC-2), `reconcile_frontmatter` default output changes (AC-4), `_serialize_state` drops `source` (AC-9), list_features drops `completed_phases` (AC-5). Per CLAUDE.md: "No backward compatibility" — these are intentional improvements for private tooling.
**Key Risk:** Phase 2 `db._conn` replacement — verify the existing `EntityDatabase` public methods (`get_workflow_phase`, `upsert_workflow_phase`, `update_workflow_phase`) cover all use cases of the inline SQL.

## Dependencies
- Entity registry test suite (710+ tests)
- Workflow engine test suite (309+ tests)
- Workflow state server test suite (276+ tests)
- Memory server test suite
