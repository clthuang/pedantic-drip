# Plan: State Consistency Consolidation

## Implementation Order

### Stage 0: Diagnostics (Prerequisite)

0. **FR-0 Diagnostic Queries** — Quantify actual drift before implementation
   - **Why this item:** PRD requires diagnostic queries to validate assumptions and potentially reduce scope.
   - **Why this order:** Must run first to inform scope decisions.
   - **Deliverable:** Run `SELECT source, COUNT(*) FROM entries GROUP BY source` in memory.db; count entity registry rows where status differs from `.meta.json` status. Document results.
   - **Complexity:** Simple — two queries, document output
   - **Files:** Results documented in implementation log
   - **Verification:** Results documented. If drift is minimal (<20 entities), consider reducing to Phase 1 only.

### Stage 1: Foundation (No dependencies)

**TDD sub-order for each item:** (a) Define function signature and return type, (b) Write unit tests against that interface, (c) Implement to pass the tests.

**API verification notes:**
- `EntityDatabase(db_path: str)` — positional `db_path` argument
- `EntityDatabase.get_entity(type_id: str) → dict | None` — returns dict, not object; access fields via `entity["status"]`
- `EntityDatabase.update_entity(type_id, status=None, ...)` — raises ValueError if entity not found
- `EntityDatabase.register_entity(entity_type, entity_id, name, ..., status=None)` — status defaults to None; **must pass status="active" explicitly** for brainstorm registration
- `MemoryDatabase(db_path: str)` — positional `db_path` argument (no keyword `db_path=`)
- `MarkdownImporter(db: MemoryDatabase, artifacts_root: str)` — constructor
- `MarkdownImporter.import_all(project_root: str, global_store: str)` — `global_store` is a path string, NOT boolean

1. **Entity Status Sync module** — C2: Read .meta.json files, compare with entity DB, update drifted statuses
   - **Why this item:** Core reconciliation logic (FR-1). All other components depend on entity statuses being accurate.
   - **Why this order:** No dependencies — operates on existing EntityDatabase API and .meta.json files.
   - **Deliverable:** `plugins/iflow/hooks/lib/reconciliation_orchestrator/entity_status.py` with `sync_entity_statuses(db, full_artifacts_path)` function
   - **Complexity:** Medium — requires iterating directories, JSON parsing with error handling, status mapping validation
   - **Files:** `plugins/iflow/hooks/lib/reconciliation_orchestrator/__init__.py`, `entity_status.py`, `test_entity_status.py`
   - **Verification:** Unit tests pass: drifted status updated, no-drift skipped, missing .meta.json archived, malformed JSON warned, unknown status skipped, missing directory handled

2. **Brainstorm Registry Sync module** — C3: Register unregistered brainstorm files as entities
   - **Why this item:** Required for show-status to query brainstorms from entity registry (FR-8).
   - **Why this order:** No dependencies — operates on existing EntityDatabase.register_entity() API.
   - **Deliverable:** `plugins/iflow/hooks/lib/reconciliation_orchestrator/brainstorm_registry.py` with `sync_brainstorm_entities(db, full_artifacts_path)` function
   - **Complexity:** Simple — directory listing, entity existence check, register if missing
   - **Files:** `brainstorm_registry.py`, `test_brainstorm_registry.py`
   - **Implementation note:** Design C3 pseudocode has a variable name bug (`artifacts_root` vs `full_artifacts_path`). The function signature must accept BOTH `full_artifacts_path` (for directory scanning) AND `artifacts_root` (relative, for storing artifact_path). Updated signature: `sync_brainstorm_entities(db, full_artifacts_path, artifacts_root)`. Scan uses `os.path.join(full_artifacts_path, "brainstorms")`. Stored artifact_path uses `os.path.join(artifacts_root, "brainstorms", filename)` to match existing entity conventions.
   - **Verification:** Unit tests pass: unregistered file registered with correct entity_id/type/status="active", already-registered skipped, .gitkeep ignored, non-.prd.md files ignored

3. **KB Import Wrapper module** — C4: MarkdownImporter wrapper for session-start
   - **Why this item:** Fills knowledge bank blind spots (FR-3). Independent of entity sync.
   - **Why this order:** No dependencies — wraps existing MarkdownImporter API.
   - **Deliverable:** `plugins/iflow/hooks/lib/reconciliation_orchestrator/kb_import.py` with `sync_knowledge_bank(memory_db, project_root, artifacts_root, global_store_path)` function
   - **Complexity:** Simple — wraps existing MarkdownImporter.import_all() with correct parameters
   - **Files:** `kb_import.py`, `test_kb_import.py`
   - **Implementation note:** `global_store_path` is derived by the orchestrator `__main__.py` as `os.path.dirname(args.memory_db)`, NOT from `memory_db.db_path` (which doesn't exist on MemoryDatabase).
   - **Verification:** Unit tests pass: new entries imported, unchanged entries skipped via source_hash dedup, correct project_root/artifacts_root/global_store_path plumbing verified

### Stage 2: Orchestration (Depends on Stage 1)

4. **Reconciliation Orchestrator CLI** — C1: Single Python entrypoint that runs all three sync tasks
   - **Why this item:** Aggregates Stage 1 modules into a single subprocess callable from bash (FR-2).
   - **Why this order:** Depends on all three Stage 1 modules being implemented and tested.
   - **Deliverable:** `plugins/iflow/hooks/lib/reconciliation_orchestrator/__main__.py` with CLI arg parsing, DB connection management (try/finally for cleanup), sequential task execution, JSON output, and error isolation
   - **Complexity:** Medium — CLI arg parsing, DB connection lifecycle, per-task error isolation, elapsed time measurement, JSON output formatting
   - **Files:** `__main__.py`, `test_orchestrator.py`
   - **Implementation note:** DB connections: `EntityDatabase(args.entity_db)`, `MemoryDatabase(args.memory_db)`. Derive `global_store_path = os.path.dirname(args.memory_db)` and `full_artifacts_path = os.path.join(args.project_root, args.artifacts_root)` in __main__.py. Use try/finally to ensure `db.close()`.
   - **Verification:** Integration test: runs all three tasks with test DB and test artifacts, outputs valid JSON with per-task results and elapsed_ms, handles individual task failures gracefully

5. **Session-start.sh integration** — I5: Wire orchestrator into session-start hook
   - **Why this item:** Enables automatic reconciliation on every session start (FR-2).
   - **Why this order:** Depends on orchestrator CLI (item 4) being complete and tested.
   - **Deliverable:** `run_reconciliation()` function in `plugins/iflow/hooks/session-start.sh` with platform-aware timeout (gtimeout/timeout), correct variable references ($PROJECT_ROOT, $artifacts_root via resolve_artifacts_root()), stderr suppression
   - **Complexity:** Simple — follows existing `build_memory_context()` pattern exactly
   - **Files:** `plugins/iflow/hooks/session-start.sh`
   - **Verification:** Run existing hook tests (`bash plugins/iflow/hooks/tests/test-hooks.sh`) to verify session-start.sh still produces valid JSON. Smoke test: invoke orchestrator CLI directly with test arguments to verify clean exit.

### Stage 3: Lifecycle Commands (Parallelizable with Stages 1-2 — independent markdown file edits)

6. **Abandon-feature command** — C5: New command to transition features to abandoned status
   - **Why this item:** Closes the lifecycle gap where no command transitions to "abandoned" (FR-5).
   - **Why this order:** No code dependency on Stage 1/2 — standalone command file. Can be implemented in parallel.
   - **Deliverable:** `plugins/iflow/commands/abandon-feature.md` command file with feature resolution, status validation (active/planned only), .meta.json update, entity registry update via MCP, fail-open error handling
   - **Complexity:** Simple — follows existing command patterns (finish-feature as template), ~50 lines
   - **Files:** `plugins/iflow/commands/abandon-feature.md`
   - **Documentation sync:** Update README.md, README_FOR_DEV.md, and plugins/iflow/README.md with new command entry
   - **Verification:** Manual: execute `/iflow:abandon-feature` against a test feature on a branch. Verify .meta.json and entity registry state. Test: attempt to abandon completed feature → error. Test: MCP unavailable → .meta.json updated, warning logged.

7. **Cleanup-brainstorms entity update** — C6: Add entity registry update after file deletion
   - **Why this item:** Prevents orphaned entity rows when brainstorm files are deleted (FR-4).
   - **Why this order:** No code dependency on Stage 1/2 — standalone command file edit. Can be implemented in parallel.
   - **Deliverable:** Modified `plugins/iflow/commands/cleanup-brainstorms.md` with `update_entity` MCP call after each deletion
   - **Complexity:** Simple — add ~5 lines per deletion point in existing command
   - **Files:** `plugins/iflow/commands/cleanup-brainstorms.md`
   - **Verification:** Manual: delete a brainstorm with entity in registry → entity status updated to "archived". Test: delete brainstorm without entity → deletion succeeds, warning logged.

### Stage 4: Consumer Migration (Depends on Stage 1 for entity data; soft dependency on Stage 3)

8. **Show-status migration to entity registry** — C7: Replace filesystem scanning with MCP queries
   - **Why this item:** Makes show-status faster, deterministic, and enables promoted brainstorm filtering (FR-6, FR-7).
   - **Why this order:** Depends on entities being registered (Stage 1) and statuses being accurate (Stage 2). Soft dependency on Stage 3 — functional after Stage 1, but abandoned features won't appear correctly without Stage 3.
   - **Deliverable:** Modified `plugins/iflow/commands/show-status.md` with MCP-based data retrieval, client-side status filtering, `Source: entity-registry` / `Source: filesystem` footer, preserved fallback for MCP unavailability
   - **Complexity:** Complex — significant rewrite of data retrieval logic, MCP tool call orchestration, client-side filtering, fallback path preservation
   - **Files:** `plugins/iflow/commands/show-status.md`
   - **Pre-implementation check:** Use `export_entities(entity_type="feature")` and `export_entities(entity_type="brainstorm")` to list all entities of a type (NOT `search_entities`, which requires a query string). Also evaluate `list_features_by_status` from workflow state server for phase-enriched feature data. Document tool selection decisions during implementation.
   - **Verification:** Test: MCP available → output shows features/brainstorms from entity registry with `Source: entity-registry` footer. Test: promoted brainstorm excluded from "Open Brainstorms". Test: MCP unavailable → falls back to filesystem scan with `Source: filesystem` footer. Test: output format matches current show-status output (no regressions).

## Dependency Graph

```
Stage 0:
  [0: diagnostics] ──→ Scope decision

Stage 1 (parallel, TDD order per item):
  [1: entity_status] ──┐
  [2: brainstorm_reg] ──┼──→ [4: orchestrator CLI] ──→ [5: session-start.sh]
  [3: kb_import]      ──┘

Stage 3 (parallel with Stages 1-2 — independent markdown edits):
  [6: abandon-feature + doc sync]  (standalone)
  [7: cleanup-brainstorms]          (standalone)

Stage 4:
  [5] + [6] + [7] ──→ [8: show-status migration]
```

## Risk Areas

- **MarkdownImporter first-run performance** (item 3/4): First import of all KB entries may be slow. Mitigated by source_hash dedup on subsequent runs and fail-open pattern.
- **Show-status rewrite scope** (item 8): Most complex item. The command file is prompt-based, so the "rewrite" is a markdown instruction change, not code. Risk is behavioral regressions in edge cases (project-linked features, MCP degradation). Mitigated by preserving exact fallback behavior.
- **search_entities filter limitations** (item 8): MCP tool doesn't support `NOT IN` filters — all filtering is client-side by the LLM. Risk of the LLM forgetting to filter. Mitigated by explicit instructions in the command file.
- **Session-start.sh modification risk** (item 5): If the `run_reconciliation()` function has a bug, it could break session startup for all projects. Mitigated by `|| true` error suppression and existing hook test suite.

## Testing Strategy

- **Unit tests for:** entity_status.py, brainstorm_registry.py, kb_import.py (Stage 1 modules — TDD: tests written first)
- **Integration tests for:** orchestrator __main__.py (runs all three modules against test DB/artifacts)
- **Hook tests for:** session-start.sh integration (`bash plugins/iflow/hooks/tests/test-hooks.sh`)
- **Manual verification for:** command files (abandon-feature, cleanup-brainstorms, show-status — tested via agent execution)

## Definition of Done

- [ ] FR-0 diagnostic queries run and results documented
- [ ] All 8 items implemented
- [ ] Unit tests passing for Stage 1 modules (TDD: tests first)
- [ ] Integration test passing for orchestrator
- [ ] Hook tests passing after session-start.sh modification
- [ ] Session-start hook runs reconciliation without errors
- [ ] Abandon-feature command works for active and planned features
- [ ] Documentation sync completed for new command
- [ ] Cleanup-brainstorms updates entity registry on deletion
- [ ] Show-status queries entity registry when MCP available
- [ ] Show-status falls back to filesystem when MCP unavailable
- [ ] Promoted brainstorms excluded from "Open Brainstorms" display
