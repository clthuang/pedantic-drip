# Plan: Entity Lineage Tracking

## Overview

This plan implements a unified entity registry database (SQLite) with MCP tools for entity identity, relationships, and lineage traversal. The implementation follows TDD order: database layer first, then MCP server and backfill scanner (parallelizable), then bootstrap/registration, then command integrations.

## Interface Legend

| ID | Name | Design Section |
|----|------|---------------|
| I1 | MCP Server Registration in plugin.json | Interfaces → I1 |
| I5 | `/show-lineage` Command Interface | Interfaces → I5 |
| I6 | Modified `create-feature.md` Entity Registration | Interfaces → I6 |
| I6b | Modified `create-project` Entity Registration | Interfaces → I6b |
| I2 | `register_entity` MCP Tool Interface | Interfaces → I2 |
| I3 | `get_lineage` MCP Tool Interface | Interfaces → I3 |
| I4 | `export_lineage_markdown` MCP Tool Interface | Interfaces → I4 |
| I7 | `depends_on_features` Handling | Interfaces → I7 |
| I8 | Phase Gate Tracking — gap-log.md | Interfaces → I8 |

## Dependency Graph

```
C1 (EntityDatabase)
  ├─ C2 (Entity MCP Server)   ─┐
  └─ C3 (Backfill Scanner)    ─┤  (Steps 2 & 3 are parallelizable)
                                └─ C8 (Bootstrap + Registration)
                                     ├─ C4 (/show-lineage command)
                                     ├─ C5 (create-feature modifications)
                                     ├─ C6 (create-project + decomposing modifications)
                                     └─ C7 (brainstorming skill modifications)

C9 (ID Canonicalization) — embedded in C1, not a separate step
C10 (Tree Rendering) — embedded in C2's get_lineage tool, not a separate step
```

## Phase Gate Note

The design merges spec Phase A (read-only lineage) and Phase B (write-path changes) because the DB-centric architecture provides both read and write tools from day one. The gap-log gate (I8) applies to **broader DB scope expansion** (replacing more .meta.json fields with DB ownership) — it does NOT gate entity registration in Steps 5-8. Entity registration is the core deliverable of this feature.

## Implementation Steps

### Step 1: EntityDatabase — Core Schema and CRUD

**Why this item:** Foundation for all other steps. EntityDatabase (C1) provides the SQLite schema, CRUD methods, recursive CTE queries, and immutable field enforcement that every subsequent component depends on. **C9 (ID Canonicalization) is implemented here** — type_id auto-generation as `{entity_type}:{entity_id}` with bare ID normalization to full `{id}-{slug}` form (see TDD sub-step 2).
**Why this order:** No dependencies — this is the leaf node. All other steps require EntityDatabase to exist.

**Component:** C1, C9
**Files:**
- `plugins/iflow/hooks/lib/entity_registry/__init__.py` (new, empty)
- `plugins/iflow/hooks/lib/entity_registry/database.py` (new)
- `plugins/iflow/hooks/lib/entity_registry/test_database.py` (new, tests first)

**TDD order:**
1. Write tests for `EntityDatabase.__init__` — schema creation, pragma verification (WAL, foreign_keys ON, busy_timeout), migration versioning → Implement schema creation + pragmas
2. Write tests for `register_entity` — happy path, idempotency (INSERT OR IGNORE), entity_type validation, type_id auto-generation (`{entity_type}:{entity_id}`), parent validation → Implement register_entity
3. Write tests for immutable field triggers — RAISE(ABORT) on type_id, entity_type, created_at mutation → Implement triggers
4. Write tests for `set_parent` — happy path, circular reference rejection (CTE walk-up), self-parent rejection, non-existent entity rejection → Implement set_parent
5. Write tests for `get_entity` — existing entity, non-existent returns None → Implement get_entity
6. Write tests for `get_lineage` — upward traversal (root first), downward traversal (BFS order), depth limit, single entity (no parent) → Implement get_lineage with recursive CTEs
7. Write tests for `update_entity` — name/status/metadata updates, shallow metadata merge, empty dict clears metadata → Implement update_entity
8. Write tests for `export_lineage_markdown` — single tree, all trees, correct markdown format → Implement export_lineage_markdown

**Note:** Implementation follows test order incrementally — each sub-step writes tests then implementation, not all tests then all implementation. After all 8 sub-steps are green, perform a refactor pass: extract shared helpers, remove duplication, verify naming consistency with design.

**Depends on:** Nothing
**Blocks:** Steps 2, 3

**Acceptance criteria coverage:** AC-1 (traversal), AC-2 (root node), AC-3 (orphaned), AC-4 (descendants), AC-14 (depth guard)

### Step 2: Entity MCP Server

**Why this item:** Exposes EntityDatabase to LLM agents via MCP tools (C2). **C10 (Tree Rendering) is implemented here** as the `render_tree` helper function (see TDD sub-step 1) — it formats `get_lineage` results into Unicode box-drawing trees for display. This is the interface that all commands and skills will use.
**Why this order:** Depends on Step 1 (wraps EntityDatabase). Can be implemented in parallel with Step 3 since they share only the Step 1 dependency.

**Component:** C2, C10
**Implements interfaces:** I2 (register_entity tool), I3 (get_lineage tool), I4 (export_lineage_markdown tool)
**Files:**
- `plugins/iflow/mcp/entity_server.py` (new)
- `plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py` (new, tests for extracted logic)

**TDD order:**
1. Write tests for tree rendering — single node, linear chain (3 deep), branching tree (2 children), `is_last` flag logic for `├─` vs `└─`, depth indentation → Implement `render_tree(entities: list[dict], root_type_id: str) -> str`
2. Write tests for metadata JSON string parsing — valid JSON, invalid JSON returns error, None passthrough → Implement `parse_metadata(metadata_str: str | None) -> dict | None`
3. Write tests for output_path resolution — relative resolved against artifacts_root, absolute used as-is, None returns text → Implement `resolve_output_path(output_path: str | None, artifacts_root: str) -> str | None`
4. Write tests for `_process_register_entity` — type_id construction, delegation to DB, error message formatting → Implement extracted function
5. Write tests for `_process_get_lineage` — delegates to DB, passes result to render_tree, formats depth-limit message → Implement extracted function
6. Create FastMCP server following `memory_server.py` pattern:
   - Lifespan: read project root, read artifacts_root from config (via `from semantic_memory.config import read_config` — safe, no numpy transitive dependency: `semantic_memory/__init__.py` only imports `hashlib`, `config.py` only uses `os` and `re`), open EntityDatabase, run backfill if needed
   - 6 MCP tools wrapping the extracted helper functions
   - Backfill trigger: check `_metadata` table for `backfill_complete` key (see Step 3)
7. Refactor pass: review helper function interfaces, remove duplication between process helpers, verify error message consistency.

**Parallelism note:** Sub-steps 1-5 are parallel with all of Step 3. Sub-step 6 (server lifespan + backfill import) must be sequenced after Step 3 is fully complete — it imports `run_backfill` from `backfill.py` which does not exist until Step 3 finishes.
**Task creation guidance:** When breaking Step 2 into tasks, sub-steps 1-5 should form a task group parallel with Step 3's tasks. Sub-step 6 must be a separate task explicitly blocked on Step 3's final task (not just any sub-step of Step 3).

**Depends on:** Step 1
**Blocks:** Step 4

**Acceptance criteria coverage:** AC-1 through AC-5 (all lineage display formats), AC-14 (depth limit message)

### Step 3: Backfill Scanner

**Why this item:** One-time migration from existing flat files (27 features, brainstorms, backlog.md) to the entity registry DB (C3). Without backfill, existing entities are invisible to lineage queries.
**Why this order:** Depends on Step 1 (uses EntityDatabase API). Can be implemented in parallel with Step 2. Must complete before Step 4 because the MCP server lifespan imports `run_backfill` from this module.

**Component:** C3
**Files:**
- `plugins/iflow/hooks/lib/entity_registry/backfill.py` (new)
- `plugins/iflow/hooks/lib/entity_registry/test_backfill.py` (new, separate from database tests)

**TDD order (incremental — each sub-step writes tests then implementation):**
1. Set up fixture directories: mock features/, projects/, brainstorms/, backlog.md → Implement fixture helpers
2. Write tests for topological ordering: backlog → brainstorm → project → feature → Implement scan ordering logic
3. Write tests for parent derivation: feature→brainstorm, feature→project, brainstorm→backlog (both `*Source: Backlog #ID*` and `**Backlog Item:** ID` marker formats) → Implement parent derivation
4. Write tests for orphaned backlog handling: synthetic entity with status="orphaned" → Implement orphaned backlog registration
5. Write tests for external brainstorm_source: synthetic entity with status="external" → Implement external path handling
6. Write tests for idempotency: running backfill twice produces same result → Verify via INSERT OR IGNORE semantics (intentional choice for backfill: silently skip duplicates, unlike the upsert pattern in memory_server which overwrites on conflict)
7. Write tests for .prd.md / .md priority: .prd.md files scanned first, .md only for unregistered stems → Implement glob ordering
8. Write tests for partial backfill recovery: `backfill_complete` marker not set → re-runs; marker set → skips → Implement `backfill_complete` marker in `_metadata` table (not entity count) to detect and recover from partial backfill. **Partial re-run safety:** When backfill re-runs after a partial failure, previously registered entities are silently skipped via INSERT OR IGNORE semantics — no duplicate errors, no data corruption, no need to delete partial state before retrying.
9. Refactor pass: review scan functions, consolidate regex patterns, verify topological ordering correctness.

**Depends on:** Step 1
**Blocks:** Step 4

**Acceptance criteria coverage:** AC-3 (orphaned parent), AC-7 (path normalization), AC-12 (orphaned backlog root)

### Step 4: Bootstrap Wrapper and MCP Registration

**Why this item:** Makes the entity MCP server discoverable by Claude Code (C8, I1). The bootstrap wrapper resolves the Python environment; plugin.json registration tells Claude Code to start the server.
**Why this order:** Depends on Steps 2 and 3 (entity_server.py imports from both). Blocks Steps 5-8 because commands/skills need the MCP server registered before they can call its tools.

**Component:** C8, I1
**Files:**
- `plugins/iflow/mcp/run-entity-server.sh` (new)
- `plugins/iflow/.claude-plugin/plugin.json` (modified — add `entity-registry` to `mcpServers` object)
- `plugins/iflow/mcp/test_entity_server.sh` (new, integration tests)

**Implementation:**
1. Create `run-entity-server.sh` following `run-memory-server.sh` pattern:
   - Resolution order: existing venv → system python3 → auto-bootstrap with `uv`
   - Set PYTHONPATH to include `hooks/lib`
   - Deps: `mcp>=1.0,<2` only (existing venv already has this). Version constraint intentionally synchronized with `run-memory-server.sh`.
   - Bootstrap uses `uv` for venv creation and dependency installation:
     ```bash
     # Bootstrap: create venv and install core deps (one-time)
     uv venv "$VENV_DIR"
     uv pip install --python "$VENV_DIR/bin/python" "mcp>=1.0,<2"
     ```
   - If `uv` is not available, fall back to `python3 -m venv` + `pip install`
   - **uv venv compatibility:** `uv venv` creates standard Python virtualenvs (PEP 405 compliant). The resulting venv is fully compatible with `pip`, `python -m pip`, and all standard tooling. Memory server's pip-based bootstrap works without modification in a uv-created venv.
   - **Shared venv note:** Both entity server and memory server share `$PLUGIN_DIR/.venv`. If entity server bootstraps first, the venv will only have `mcp` (missing numpy/dotenv for memory server). This is acceptable: memory server's own bootstrap handles missing deps. Add a header comment noting the shared venv.
2. Add `entity-registry` entry to `plugin.json` mcpServers
3. Write integration test script following `test_run_memory_server.sh` pattern:
   - Server startup, register_entity round-trip, get_lineage output verification, backfill_complete marker check

**Depends on:** Steps 2, 3
**Blocks:** Steps 5, 6, 7, 8

**Acceptance criteria coverage:** AC-11 (no breaking changes — plugin.json addition is backward compatible)

### Step 5: `/show-lineage` Command

**Why this item:** The primary user-facing command (C4, I5). Thin wrapper around `get_lineage` MCP tool — all complexity lives in the DB layer.
**Why this order:** Depends on Step 4 (MCP server must be registered for tool calls to work).

**Component:** C4, I5
**Files:**
- `plugins/iflow/commands/show-lineage.md` (new)

**Implementation:**
1. Create command markdown with frontmatter (description, argument-hint)
2. Argument parsing: `--feature`, `--project`, `--backlog`, `--brainstorm`, `--descendants`
3. Auto-detect feature from git branch: regex `^feature/(.+)$`
4. Construct type_id from arguments
5. Call `get_lineage` MCP tool with appropriate direction
6. Display formatted tree output
7. Error handling: entity not found, no argument and not on feature branch, depth limit

**Depends on:** Step 4
**Blocks:** Nothing

**Acceptance criteria coverage:** AC-1 (upward traversal), AC-2 (root node), AC-3 (orphaned), AC-4 (descendants), AC-5 (project tree), AC-12 (orphaned backlog), AC-14 (depth guard)

### Step 6: Modified `create-feature.md` — Entity Registration + Backlog Promotion

**Why this item:** Integrates entity registration into the feature creation workflow (C5, I6). Changes backlog handling from delete-on-promote to mark-as-promoted.
**Why this order:** Depends on Step 4 (MCP server must be registered). Independent of Steps 5, 7, 8.

**Component:** C5, I6
**Files:**
- `plugins/iflow/commands/create-feature.md` (modified)

**Implementation:**
1. After feature directory + .meta.json creation, add MCP tool calls:
   - `register_entity` for backlog item (idempotent) if backlog_source exists
   - `update_entity` to set backlog status to "promoted"
   - `register_entity` for brainstorm (idempotent) if brainstorm_source exists
   - `register_entity` for the feature with parent_type_id set
2. Change backlog handling: instead of removing row from backlog.md, append `(promoted → feature:{id}-{slug})` to Description column. **Multi-promotion format:** If Description already contains a `(promoted → ...)` annotation, append the new entity reference comma-separated inside the existing parenthetical per AC-6, e.g., `(promoted → project:P001, feature:029-entity-lineage-tracking)`.
3. MCP failure handling: warn but do NOT block feature creation
4. **Write ordering:** DB registration/update first, then backlog.md annotation. If annotation fails, warn but do not rollback DB — the DB is source of truth, backlog.md is a visibility aid.

**AC-11 note:** The output change from "(removed from backlog)" to "(promoted)" is permitted by AC-11's explicit exception: "unchanged except for the explicitly described modifications in this spec (backlog promotion in create-feature.md)".

**Depends on:** Step 4
**Blocks:** Nothing

**Acceptance criteria coverage:** AC-6 (backlog mark-as-promoted), AC-8 (parent field via DB), AC-9 (parent validation), AC-11 (no breaking changes — explicit exception for backlog promotion)

### Step 7: Modified `create-project` + `decomposing` — Entity Registration

**Why this item:** Extends entity registration to the project workflow (C6, I6b). Ports the backlog-source parsing pattern from create-feature to create-project (new code path).
**Why this order:** Depends on Step 4 (MCP server must be registered). Independent of Steps 5, 6, 8.

**Component:** C6, I6b
**Implements interfaces:** I7 (depends_on_features handling — stored as metadata, not parent-child)
**Files:**
- `plugins/iflow/commands/create-project.md` (modified)
- `plugins/iflow/skills/decomposing/SKILL.md` (modified)

**Implementation:**
1. `create-project.md`:
   - After project directory + .meta.json creation, add MCP tool calls
   - Register brainstorm entity (idempotent)
   - Parse brainstorm content for `*Source: Backlog #ID*` marker (new code path ported from create-feature)
   - If found: register backlog entity, update status to "promoted", set_parent on brainstorm
   - Register project entity with parent_type_id set to brainstorm
   - MCP failure handling: warn but do NOT block
   - **Spec divergence note:** Spec line 56 defers create-project backlog handling to Phase B. Design I6b includes it in the merged-phase approach (see Phase Gate Note). This is an intentional design override of spec phasing.
2. `decomposing` SKILL.md:
   - When creating planned features, add `register_entity` call with `parent_type_id="project:{project_id}"`
   - **`depends_on` mapping (I7):** The decomposer's `depends_on` array represents sibling dependencies (build order), NOT parent-child lineage. These are stored in entity `metadata` JSON as `{"depends_on_features": [...]}` for display in descendant trees (AC-5 annotations) but do NOT generate `set_parent` calls. Each decomposed feature's parent is always the project.
   - MCP failure handling: warn but do NOT block

**Depends on:** Step 4
**Blocks:** Nothing

**Acceptance criteria coverage:** AC-10 (decomposed feature parent), AC-13 (create-project parent field), AC-11 (no breaking changes)

### Step 8: Modified `brainstorming` Skill — Entity Registration

**Why this item:** Registers brainstorm entities at creation time (C7), establishing the earliest point in the lineage chain where entities are tracked.
**Why this order:** Depends on Step 4 (MCP server must be registered). Independent of Steps 5, 6, 7.

**Component:** C7
**Files:**
- `plugins/iflow/skills/brainstorming/SKILL.md` (modified)

**Implementation:**
1. After creating brainstorm PRD file (end of Stage 3):
   - Call `register_entity` to register the brainstorm entity
   - If brainstorm originated from backlog (`*Source: Backlog #ID*` in args), set parent to `backlog:{id}`
2. MCP failure handling: warn but do NOT block brainstorm creation

**Depends on:** Step 4
**Blocks:** Nothing

**Acceptance criteria coverage:** AC-11 (no breaking changes)

### Step 9: Gap Log Template

**Why this item:** Tracking artifact for the phase gate (I8). Required to validate the DB approach before expanding DB scope beyond lineage.
**Why this order:** No dependencies — can be created at any point. Listed late because it's a trivial file creation.

**Component:** I8
**Files:**
- `docs/dev_artifacts/workitems/029-entity-lineage-tracking/gap-log.md` (new)

**Implementation:**
1. Create gap-log.md with the template from design I8 section (Summary table + Invocation Log table)
2. Initial values: 0 invocations, no entity types, no gaps

**Done when:** `docs/dev_artifacts/workitems/029-entity-lineage-tracking/gap-log.md` exists with Summary table (invocation count, entity types queried, gaps observed) and Invocation Log table (date, entity, query type, result, gap noted). See design I8 for exact template.

**Depends on:** Nothing
**Blocks:** Nothing

**Acceptance criteria coverage:** Phase gate tracking (spec Resolved Questions)

### Step 10: Documentation Updates

**Why this item:** Keeps READMEs and component counts in sync with new command and MCP server.
**Why this order:** Must follow Steps 5-8 so all component names and counts are finalized.

**Files:**
- `README.md` (modified — add /show-lineage to command table, update component counts)
- `README_FOR_DEV.md` (modified — update component counts)
- `plugins/iflow/README.md` (modified — add show-lineage command, update MCP server listing)
- `plugins/iflow/skills/workflow-state/SKILL.md` (no modification needed — `parent` field is NOT added to .meta.json schema in this feature; the DB owns lineage)

**Depends on:** Steps 5-8
**Blocks:** Nothing

## Risk Mitigations

| Risk | Mitigation in Plan |
|------|-------------------|
| R1: Backfill latency | Step 3 — scan is ~60 file reads (<100ms). If >500ms, add progress indicator |
| R2: Dual-write drift | Steps 6-8 write DB first, then legacy fields. DB is source of truth |
| R3: Pre-010 brainstorm accuracy | Step 3 includes multi-pattern detection (2 regex formats) + feature-context fallback. Known limitation documented |
| R4: MCP server unavailable | Steps 5-8 all include warn-but-don't-block error handling |
| R5: Concurrent access | Step 1 includes WAL mode + BEGIN IMMEDIATE + busy_timeout=5000 |

## Sequencing Summary

```
                    ┌─→  Step 2 (MCP Server)       ─┐
Step 1 (Database) ──┤                                ├──→  Step 4 (Bootstrap) ──┬──→ Step 5
                    └─→  Step 3 (Backfill Scanner)  ─┘                          ├──→ Step 6
                                                                                ├──→ Step 7
                                                                                ├──→ Step 8
                                                            Step 9 (anytime) ───┘
                                                            Step 10 (after 5-8)
```

**Critical path:** Step 1 (Database) → Step 2 (MCP Server) + Step 3 (Backfill) → Step 4 (Bootstrap) → Steps 5-8 (integrations) → Step 10 (Docs).

Steps 2 (MCP Server) and 3 (Backfill Scanner) can be implemented in parallel after Step 1 (Database) completes.
Steps 5 (show-lineage), 6 (create-feature), 7 (create-project + decomposing), 8 (brainstorming), and 9 (gap-log) can be implemented in parallel after Step 4 (Bootstrap) completes.
Step 10 (Documentation) runs after all implementation steps are done.

**Rollback gates:**
- **Gate 1 (Step 1):** If EntityDatabase schema or core CRUD fails, nothing proceeds. Rollback: delete `entity_registry/` module, no other artifacts affected.
- **Gate 2 (Step 4):** If bootstrap or MCP registration fails, integration steps 5-8 are blocked. Rollback: revert plugin.json change, remove run-entity-server.sh. Steps 1-3 remain independently valid.
