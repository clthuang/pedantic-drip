# Specification: State Consistency Consolidation

## Problem Statement
The iflow plugin has dual write paths that cause silent divergence between its data stores: (1) knowledge bank markdown entries are not indexed in the semantic memory DB, causing search blind spots, and (2) entity registry status drifts from `.meta.json` because non-completion lifecycle transitions have no entity status update path.

## Success Criteria
- [ ] After session-start reconciliation, every markdown KB entry has a corresponding row in the semantic memory DB (verified by count comparison and spot-check queries for "markdown migration", "hook development bash stderr", "entity registry")
- [ ] Entity registry `status` field matches `.meta.json` `status` for all features and projects after reconciliation
- [ ] `show-status` queries entity registry + workflow engine MCP tools instead of scanning filesystem
- [ ] Promoted brainstorms excluded from "Open Brainstorms" display via entity status filter
- [ ] Brainstorm files in `{artifacts_root}/brainstorms/` are registered as entities at session-start
- [ ] Feature abandonment updates `.meta.json` and entity registry in sequence (fail-open: `.meta.json` persists if entity update fails; reconciliation resolves drift)
- [ ] `cleanup-brainstorms` marks deleted brainstorm entities as "archived"
- [ ] All reconciliation is idempotent and non-blocking (fail-open)

## Scope

### In Scope
- **Phase 1 — Session-start reconciliation:**
  - FR-0: Diagnostic queries to quantify actual drift before implementation
  - FR-1: New status reconciliation function that reads `.meta.json` status and calls `update_entity` for drifted entities. Status mapping: active→active, completed→completed, abandoned→abandoned, planned→planned, promoted→promoted
  - FR-2/FR-3: Wire status reconciliation + `MarkdownImporter` into session-start hook
  - FR-8: Brainstorm entity registration — scan `{artifacts_root}/brainstorms/` and register unregistered files

- **Phase 2 — Lifecycle gap closure:**
  - FR-4: `cleanup-brainstorms` calls `update_entity(status="archived")` for deleted brainstorms
  - FR-5: Feature abandonment flow — updates `.meta.json` status to "abandoned" and entity registry status to "abandoned"

- **Phase 3 — Consumer migration:**
  - FR-6: Refactor `show-status` to query entity registry + workflow engine MCP tools (with artifact-based fallback for MCP-unavailable)
  - FR-7: Filter promoted brainstorms by entity status != "promoted"
  - `list-features` migration deferred — `show-status` is the primary consumer and proves the pattern; `list-features` can follow in a subsequent feature

### Out of Scope
- Bidirectional knowledge bank sync (DB → markdown) — session captures are intentionally DB-only
- Full event sourcing for entity lifecycle — overkill for <100 entities
- Real-time hooks at every lifecycle transition — session-start reconciliation is sufficient
- Knowledge bank deduplication (fuzzy matching of semantically similar entries)
- Entity registry garbage collection — "archived" status preserves lineage
- Migrating `show-status` to a standalone Python CLI tool
- `list-features` migration to entity registry queries — deferred until `show-status` migration proves the pattern (note: PRD success criterion for list-features will be addressed in a follow-up feature)

## Acceptance Criteria

### AC-1: Session-start entity status reconciliation
- Given a feature with `.meta.json` status "completed" but entity registry status "active"
- When session-start reconciliation runs
- Then entity registry status is updated to "completed"

### AC-2: Session-start entity status reconciliation (no drift)
- Given all entity registry statuses already match `.meta.json` statuses
- When session-start reconciliation runs
- Then no entity updates are performed (idempotent)

### AC-3: Session-start KB import
- Given a markdown KB entry in `docs/knowledge-bank/patterns.md` with no corresponding semantic DB row
- When session-start reconciliation runs `MarkdownImporter`
- Then the entry is imported to semantic memory DB with correct content hash

### AC-4: Session-start KB import (already imported entries)
- Given markdown KB entries whose content has not changed since last import
- When session-start reconciliation runs `MarkdownImporter`
- Then import is skipped for entries with matching `source_hash` (content-level dedup)

### AC-5: Brainstorm entity registration
- Given a brainstorm file exists at `{artifacts_root}/brainstorms/20260318-example.prd.md` with no entity in registry
- When session-start reconciliation scans brainstorms directory
- Then a brainstorm entity is registered with `entity_type` = "brainstorm", `entity_id` = filename stem (e.g., "20260318-example"), `entity_type_id` = "brainstorm:20260318-example", `artifact_path` = file path, `status` = "active"

### AC-6: Brainstorm entity registration (already registered)
- Given a brainstorm file exists and its entity is already in the registry
- When session-start reconciliation scans brainstorms directory
- Then no duplicate entity is created (idempotent)

### AC-7: Cleanup-brainstorms entity update
- Given a brainstorm file is selected for deletion and has an entity in the registry
- When `/iflow:cleanup-brainstorms` deletes the file
- Then entity registry status is updated to "archived"

### AC-8: Cleanup-brainstorms entity update (no entity)
- Given a brainstorm file is selected for deletion but has no entity in the registry (old brainstorm)
- When `/iflow:cleanup-brainstorms` deletes the file
- Then deletion succeeds without entity update (no error)

### AC-9: Feature abandonment
- Given an active feature with `.meta.json` status "active" and entity registry status "active"
- When `/iflow:abandon-feature` is run for the feature
- Then `.meta.json` status is set to "abandoned", followed by entity registry status update to "abandoned". The abandonment command updates only `.meta.json` and entity registry status — it does not call `complete_phase` or modify the `workflow_phases` table. If entity registry update fails, `.meta.json` change persists and session-start reconciliation will resolve the drift on next session.

### AC-10: show-status via entity registry (MCP available)
- Given MCP servers are available and entity registry has current data
- When `/iflow:show-status` runs
- Then it uses MCP tool calls (`search_entities`, `get_phase`, `list_features_by_status`) to retrieve data. Output includes `Source: entity-registry` footer when MCP is available, vs `Source: filesystem` in fallback mode.

### AC-11: show-status fallback (MCP unavailable)
- Given MCP servers are unavailable
- When `/iflow:show-status` runs
- Then it falls back to artifact-based file scanning (current behavior)

### AC-12: Promoted brainstorm filtering
- Given a brainstorm entity with status "promoted" in entity registry
- When `/iflow:show-status` displays "Open Brainstorms"
- Then the promoted brainstorm is excluded from the list

### AC-13: Reconciliation performance
- Given a repo with <100 features and <200 KB entries
- When session-start reconciliation runs
- Then total wall-clock elapsed time is under 5 seconds (measured on development machine with warm filesystem cache). Diagnostic logging reports elapsed time per sub-operation.

### AC-14: Reconciliation fail-open
- Given the reconciliation orchestrator fails to start (missing venv, DB unavailable, Python import error, or subprocess timeout)
- When session-start triggers reconciliation
- Then the failure is caught, logged as a warning, and the session proceeds normally

### AC-15: Status mapping completeness
- Given the status reconciliation function
- When it encounters a `.meta.json` status value
- Then it maps using: active→active, completed→completed, abandoned→abandoned, planned→planned, promoted→promoted

### AC-15b: Unknown status value handling
- Given a `.meta.json` with an unrecognized status value (e.g., "draft")
- When status reconciliation runs
- Then the entity is skipped with a warning log (no update, no error)

### AC-16: Entity in registry but .meta.json deleted
- Given an entity with status "active" in registry but no corresponding `.meta.json` file on disk
- When session-start reconciliation runs
- Then entity status is updated to "archived"

## Feasibility Assessment

### Assessment Approach
1. **First Principles** — Session-start reconciliation is a well-understood pattern (Kubernetes-style desired vs actual state comparison)
2. **Codebase Evidence** — All required infrastructure exists:
   - `MarkdownImporter` at `plugins/iflow/hooks/lib/semantic_memory/importer.py` — already implements markdown → DB import
   - `db.update_entity()` at `plugins/iflow/hooks/lib/entity_registry/database.py` — already updates entity status
   - `reconcile_apply` MCP tool — already detects and fixes workflow phase drift
   - `session-start.sh` hook — already runs at session start, can be extended
   - `register_entity` MCP tool — already registers entities idempotently
3. **External Evidence** — SSOT with unidirectional sync is the dominant industry pattern — Source: Confluent, AWS Prescriptive Guidance

### Assessment
**Overall:** Confirmed
**Reasoning:** All building blocks exist. Phase 1 (reconciliation) requires wiring existing functions into session-start. Phase 2 (abandonment) requires a new command file (~50 lines) and one `update_entity` call in `cleanup-brainstorms`. Phase 3 (show-status migration) requires rewriting the command to use MCP queries instead of file scanning — the MCP tools already exist.
**Key Assumptions:**
- `MarkdownImporter.import_all()` can complete within ~3s for <200 entries — Status: Needs verification (run FR-0 diagnostic)
- `session-start.sh` hook can accommodate additional reconciliation calls without exceeding startup latency tolerance — Status: Needs verification
- `update_entity` MCP tool metadata parsing is reliable enough for status-only updates (no metadata param needed) — Status: Verified at engine.py:173 (db.update_entity only sets status, no metadata)
**Open Risks:** If `MarkdownImporter` is slow on first run (cold cache, all 169+ entries), session-start may exceed 5s budget. Mitigation: `MarkdownImporter` uses `source_hash` content-level dedup — after first import, subsequent runs only process new/changed entries. Fail-open pattern ensures session still starts even if budget is exceeded.

## Dependencies
- Entity registry MCP server must be running for reconciliation and entity updates
- Workflow engine MCP server must be running for `show-status` phase queries
- Memory MCP server must be running for `MarkdownImporter` DB access (or direct SQLite fallback)

## Resolved Questions
- **MarkdownImporter execution model:** Synchronous during session-start. Simpler, matches fail-open pattern — if it fails or exceeds budget, the session still starts with a warning log. Success criteria are verifiable immediately after session-start.
- **Abandonment flow surface:** New `/iflow:abandon-feature` command (separation of concerns — `finish-feature` has completion semantics, abandonment is a different intent).

## Implementation Constraints
- Session-start reconciliation MUST be implemented as a single Python subprocess call (orchestrator pattern) to avoid multiplying subprocess overhead. All reconciliation sub-operations (entity status, KB import, brainstorm registration) execute within one Python invocation. The orchestrator directly imports `entity_registry` and `semantic_memory` Python modules (no MCP round-trips during reconciliation — MCP tools are for agent use, the orchestrator uses the underlying libraries).
- `MarkdownImporter` uses `source_hash` (content hashing) for entry-level dedup, not file-level mtime. The existing dedup mechanism is sufficient for correctness; file-level mtime optimization is a future enhancement if performance requires it.
