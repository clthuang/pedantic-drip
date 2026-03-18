# Design: State Consistency Consolidation

## Prior Art Research

### Codebase Patterns
- `session-start.sh` Python subprocess pattern: uses `PLUGIN_ROOT/.venv/bin/python` with `PYTHONPATH=SCRIPT_DIR/lib`, timeout guard (5s), retry (3x), stderr suppressed (`2>/dev/null`). `build_memory_context()` (lines 358–413) is the canonical model for adding reconciliation — Location: plugins/iflow/hooks/session-start.sh
- `MarkdownImporter.import_all(project_root, global_store)` → dict `{imported, skipped}`. Uses `source_hash` content dedup via `_upsert_entry`. Called via `python -m semantic_memory.injector` CLI — Location: plugins/iflow/hooks/lib/semantic_memory/importer.py
- `EntityDatabase.update_entity(type_id, name=None, status=None, artifact_path=None, metadata=None)` — accepts type_id string, no status validation, raises ValueError if entity not found — Location: plugins/iflow/hooks/lib/entity_registry/database.py:845
- `reconcile_apply` only syncs workflow_phase/last_completed_phase/mode/kanban_column — entity `status` column is NOT in scope. Entity status sync needs a separate path — Location: plugins/iflow/hooks/lib/workflow_engine/reconciliation.py:569
- `complete_phase` sets entity status='completed' via `db.update_entity()` at workflow_state_server.py:802. This is the canonical in-server status mutation pattern.
- `cleanup-brainstorms.md` has NO entity registry update after file deletion — Location: plugins/iflow/commands/cleanup-brainstorms.md:73

### External Patterns
- Single Python subprocess from bash hook: established git hook pattern. One entrypoint handles all logic, returns exit code.
- SQLite UPSERT (`INSERT ... ON CONFLICT DO UPDATE`) for idempotent file-to-DB sync — Source: sqlite.org
- Jira/Linear: abandonment is a terminal state (soft delete), entity preserved for historical reporting — Source: Atlassian Community, Linear docs

## Architecture Overview

### Component Map

```
session-start.sh
  ├── build_memory_context()        [existing]
  ├── run_reconciliation()          [NEW — Phase 1]
  │     └── python -m reconciliation_orchestrator
  │           ├── entity_status_sync()   — reads .meta.json, updates entity DB
  │           ├── brainstorm_sync()      — registers unregistered brainstorm files
  │           └── kb_import()            — runs MarkdownImporter
  └── build_context()               [existing]

commands/
  ├── abandon-feature.md            [NEW — Phase 2]
  ├── cleanup-brainstorms.md        [MODIFIED — Phase 2]
  └── show-status.md                [MODIFIED — Phase 3]

hooks/lib/
  └── reconciliation_orchestrator/  [NEW — Phase 1]
      ├── __init__.py
      ├── __main__.py               — CLI entrypoint
      ├── entity_status.py          — .meta.json → entity DB sync
      ├── brainstorm_registry.py    — brainstorm file → entity DB registration
      └── kb_import.py              — MarkdownImporter wrapper
```

### Data Flow

```
.meta.json files ──→ entity_status_sync() ──→ entities.db (status column)
                         │
                         ├── reads .meta.json status field
                         ├── reads entity DB status via db.get_entity()
                         ├── compares: if different → db.update_entity()
                         └── if .meta.json missing → db.update_entity(status="archived")

brainstorms/*.prd.md ──→ brainstorm_sync() ──→ entities.db (new rows)
                         │
                         ├── lists files in brainstorms/
                         ├── for each: db.get_entity("brainstorm:{stem}")
                         ├── if not found → db.register_entity()
                         └── if found → skip (idempotent)

docs/knowledge-bank/ ──→ kb_import() ──→ memory.db (entries table)
                         │
                         ├── calls MarkdownImporter.import_all()
                         ├── source_hash dedup (entry-level)
                         └── returns {imported, skipped} counts
```

### Design Principles
1. **.meta.json is source of truth** for entity status — DB is a derived cache
2. **Unidirectional sync only** — .meta.json → DB, never DB → .meta.json
3. **Fail-open everywhere** — reconciliation errors are warnings, never block session start
4. **Single subprocess** — all reconciliation runs in one Python invocation to minimize overhead
5. **Idempotent operations** — safe to run multiple times with identical results

## Components

### C1: Reconciliation Orchestrator (`hooks/lib/reconciliation_orchestrator/`)

**Purpose:** Single Python module that runs all session-start reconciliation tasks in sequence.

**Location:** `plugins/iflow/hooks/lib/reconciliation_orchestrator/`

**Invocation:** Called from `session-start.sh` via `run_reconciliation()` (see I5 for full bash integration).

**CLI arguments:**
| Arg | Type | Required | Description |
|-----|------|----------|-------------|
| `--project-root` | str | yes | Absolute repo root (e.g., `/Users/terry/projects/my-ai-setup`) |
| `--artifacts-root` | str | yes | Relative sub-path for artifacts (e.g., `docs`) |
| `--entity-db` | str | yes | Path to entity registry DB file |
| `--memory-db` | str | yes | Path to semantic memory DB file |

**Internal structure:**
- `__main__.py` — CLI entrypoint. Parses args, opens DB connections (`EntityDatabase(args.entity_db)`, `MemoryDatabase(args.memory_db)`), constructs full artifacts path (`os.path.join(args.project_root, args.artifacts_root)`), runs tasks sequentially, closes connections, outputs JSON summary.
- `entity_status.py` — `sync_entity_statuses(db: EntityDatabase, full_artifacts_path: str) → dict`
- `brainstorm_registry.py` — `sync_brainstorm_entities(db: EntityDatabase, full_artifacts_path: str) → dict`
- `kb_import.py` — `sync_knowledge_bank(memory_db: MemoryDatabase, project_root: str, artifacts_root: str) → dict`

**Error isolation:** Each task is wrapped in try/except. If one fails, the others still run. The orchestrator returns per-task status in its JSON output.

**Performance budget:** Total ≤5s. Each task has individual timing. If total exceeds 5s, a warning is logged but execution is not interrupted.

### C2: Entity Status Sync (`entity_status.py`)

**Purpose:** Read all `.meta.json` files for features and projects, compare status with entity registry, update where drifted.

**Algorithm:**
```python
def sync_entity_statuses(db, full_artifacts_path):
    STATUS_MAP = {"active", "completed", "abandoned", "planned", "promoted"}
    results = {"updated": 0, "skipped": 0, "archived": 0, "warnings": []}

    for entity_type, subdir in [("feature", "features"), ("project", "projects")]:
        scan_dir = os.path.join(full_artifacts_path, subdir)
        if not os.path.isdir(scan_dir):
            continue

        for folder in os.listdir(scan_dir):
            meta_path = os.path.join(scan_dir, folder, ".meta.json")
            type_id = f"{entity_type}:{folder}"

            if not os.path.isfile(meta_path):
                # .meta.json deleted — archive entity if it exists
                try:
                    db.update_entity(type_id, status="archived")
                    results["archived"] += 1
                except ValueError:
                    pass  # entity not in registry, skip
                continue

            try:
                with open(meta_path) as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                results["warnings"].append(f"Failed to read {meta_path}: {e}")
                continue
            meta_status = meta.get("status")

            if meta_status not in STATUS_MAP:
                results["warnings"].append(f"Unknown status '{meta_status}' for {type_id}")
                continue

            entity = db.get_entity(type_id)  # returns None if not found
            if entity is None:
                results["skipped"] += 1  # entity not in registry
                continue

            if entity["status"] != meta_status:
                db.update_entity(type_id, status=meta_status)
                results["updated"] += 1
            else:
                results["skipped"] += 1

    return results
```

### C3: Brainstorm Registry Sync (`brainstorm_registry.py`)

**Purpose:** Scan brainstorms directory and register any unregistered brainstorm files as entities.

**Algorithm:**
```python
def sync_brainstorm_entities(db, full_artifacts_path):
    results = {"registered": 0, "skipped": 0}
    brainstorms_dir = os.path.join(full_artifacts_path, "brainstorms")

    if not os.path.isdir(brainstorms_dir):
        return results

    for filename in os.listdir(brainstorms_dir):
        if filename == ".gitkeep" or not filename.endswith(".prd.md"):
            continue

        stem = filename.replace(".prd.md", "")
        type_id = f"brainstorm:{stem}"
        artifact_path = os.path.join(artifacts_root, "brainstorms", filename)

        existing = db.get_entity(type_id)  # returns None if not found
        if existing:
            results["skipped"] += 1
            continue

        # Register new brainstorm entity
        db.register_entity(
            entity_type="brainstorm",
            entity_id=stem,
            name=stem,  # filename stem as name
            artifact_path=artifact_path,
            status="active"
        )
        results["registered"] += 1

    return results
```

### C4: KB Import Wrapper (`kb_import.py`)

**Purpose:** Run `MarkdownImporter.import_all()` to sync markdown KB entries to semantic memory DB.

**Algorithm:**
```python
def sync_knowledge_bank(memory_db, project_root, artifacts_root, global_store_path):
    """
    Args:
        memory_db: MemoryDatabase instance (connected to memory.db)
        project_root: absolute repo root (e.g., /Users/terry/projects/my-ai-setup)
        artifacts_root: relative sub-path (e.g., "docs")
        global_store_path: directory containing memory.db (e.g., ~/.claude/iflow/memory)
                          Derived by orchestrator __main__.py from os.path.dirname(args.memory_db)
    """
    from semantic_memory.importer import MarkdownImporter

    importer = MarkdownImporter(db=memory_db, artifacts_root=artifacts_root)
    result = importer.import_all(
        project_root=project_root,       # absolute repo root
        global_store=global_store_path    # string path, NOT boolean
    )
    return {"imported": result.get("imported", 0), "skipped": result.get("skipped", 0)}
```

### C5: Abandon Feature Command (`commands/abandon-feature.md`)

**Purpose:** New command to transition a feature to abandoned status.

**Flow:**
1. Resolve target feature (from arg or active feature)
2. Read `.meta.json`, verify status is "active" or "planned" (valid starting states for abandonment)
   - If status is "completed": error "Feature already completed. Cannot abandon."
   - If status is "abandoned": error "Feature already abandoned."
3. Confirm with user (unless YOLO mode)
4. Update `.meta.json` status to "abandoned"
5. Call `update_entity` MCP tool: `update_entity(type_id="feature:{id}-{slug}", status="abandoned")`
6. If MCP call fails: warn, `.meta.json` change persists, session-start reconciliation will resolve drift
7. Output confirmation

**Does NOT call `complete_phase`** — abandonment is a status-only change, not a workflow phase completion. The `workflow_phases` table retains the last known phase for historical reference.

### C6: Cleanup-Brainstorms Modification

**Change:** After each brainstorm file is deleted, add:
```
Call update_entity MCP tool:
  update_entity(type_id="brainstorm:{stem}", status="archived")
If MCP call fails or entity not in registry: warn and continue (do not block deletion)
```

### C7: Show-Status Migration

**Change:** Replace filesystem scanning with entity registry MCP queries.

**New flow (MCP available):**
```
1. Current Context: git branch (unchanged)
2. Project Features: search_entities(entity_type="feature") + filter by project_id
   - For active features: get_phase() for current phase
3. Open Features: search_entities(entity_type="feature", status NOT IN ("completed"))
   - Exclude project-linked features
   - For active features: get_phase() for current phase
4. Open Brainstorms: search_entities(entity_type="brainstorm")
   - Filter: status != "promoted" AND status != "archived"
   - Display file age from artifact_path mtime
5. Footer: Source: entity-registry
```

**Fallback (MCP unavailable):**
Current filesystem scanning behavior preserved exactly. Footer shows `Source: filesystem`.

**MCP availability detection:** Same tri-state pattern (`mcp_available`: null → true/false on first call). First MCP call determines path for entire invocation.

## Technical Decisions

### TD-1: Direct Python imports, not MCP round-trips for orchestrator
**Decision:** The reconciliation orchestrator directly imports `entity_registry.database.EntityDatabase` and `semantic_memory` modules.
**Rationale:** MCP tools are for agent use (over stdio). The orchestrator runs as a subprocess from bash hook — no MCP server is available in that context. Direct imports are faster and simpler.
**Trade-off:** The orchestrator must be kept in sync with the library API. This is acceptable since both live in the same plugin.

### TD-2: Entity status sync scans .meta.json files, not DB
**Decision:** The reconciler iterates over filesystem directories and reads `.meta.json` files, comparing against DB.
**Rationale:** `.meta.json` is the source of truth (per CLAUDE.md and PRD constraint). Scanning files catches all state including manual edits. The alternative — querying DB and checking files — would miss entities not yet in the DB.
**Trade-off:** Filesystem scan is O(n) in feature count. For <100 features, this is negligible (<100ms).

### TD-3: Abandon-feature as a separate command, not finish-feature option
**Decision:** New `/iflow:abandon-feature` command rather than adding "Abandon" to `finish-feature`.
**Rationale:** `finish-feature` has completion semantics (retro, merge, cleanup). Abandonment is a different intent — no retro, no merge, no cleanup. Mixing them would complicate the command logic and confuse the workflow state.
**Trade-off:** One more command to maintain. Acceptable for semantic clarity.

### TD-4: show-status uses MCP tools, not direct DB access
**Decision:** `show-status.md` queries entity registry via MCP tools (`search_entities`, `get_phase`).
**Rationale:** `show-status` is a command file executed by the LLM agent, which already has MCP tool access. Direct DB access would require a Python subprocess, adding complexity. MCP tools are the established query interface for agents.
**Trade-off:** Depends on MCP server availability. Mitigated by the filesystem fallback.

### TD-5: Brainstorm registration uses filename stem as entity_id
**Decision:** `entity_id` = filename without `.prd.md` extension (e.g., `20260318-041527-state-consistency-consolidation`).
**Rationale:** Consistent with existing brainstorm entity registration in the brainstorming skill (Stage 3). Filenames are immutable identifiers — brainstorm files are never renamed.
**Trade-off:** If a file is renamed, the old entity becomes stale. Acceptable — brainstorm files are not renamed in practice.

## Risks

### R-1: MarkdownImporter first-run performance
**Risk:** First import of 169+ KB entries may exceed the 3s sub-budget.
**Likelihood:** Medium
**Impact:** Low (fail-open — session still starts)
**Mitigation:** `source_hash` dedup means subsequent runs only process new/changed entries. First-run cost is amortized over all future sessions.

### R-2: Entity not in registry during status sync
**Risk:** `.meta.json` exists for a feature but the entity was never registered (old feature, pre-entity-registry).
**Likelihood:** Medium (many legacy features)
**Impact:** Low — sync skips unregistered entities; they'll be registered if/when interacted with.
**Mitigation:** The sync logs a count of "skipped" entities. No action needed.

### R-3: Race condition between session-start reconciliation and MCP server startup
**Risk:** Reconciliation orchestrator tries to access DB while MCP server is still initializing (DB lock).
**Likelihood:** Low (orchestrator uses direct Python imports, not MCP)
**Impact:** Low (SQLite WAL mode allows concurrent reads)
**Mitigation:** Orchestrator opens its own connection. SQLite handles concurrent access via WAL.

## Interfaces

### I1: Reconciliation Orchestrator CLI

**Entrypoint:** `python -m reconciliation_orchestrator`

**Arguments:**
| Arg | Type | Required | Description |
|-----|------|----------|-------------|
| `--project-root` | str | yes | Absolute repo root (e.g., `/Users/terry/projects/my-ai-setup`) |
| `--artifacts-root` | str | yes | Relative sub-path for artifacts (e.g., `docs`) |
| `--entity-db` | str | yes | Path to entity registry DB file |
| `--memory-db` | str | yes | Path to semantic memory DB file |
| `--verbose` | flag | no | Write debug logs to `~/.claude/iflow/reconciliation.log` |

**Output (stdout, JSON):**
```json
{
  "entity_sync": {"updated": 2, "skipped": 40, "archived": 1, "warnings": []},
  "brainstorm_sync": {"registered": 1, "skipped": 3},
  "kb_import": {"imported": 5, "skipped": 164},
  "elapsed_ms": 1200,
  "errors": []
}
```

**Exit code:** Always 0 (fail-open). Errors are reported in the `errors` array.

### I2: entity_status.sync_entity_statuses()

```python
def sync_entity_statuses(
    db: EntityDatabase,
    full_artifacts_path: str
) -> dict:
    """
    Scan .meta.json files for features and projects.
    Compare status with entity registry.
    Update entity DB where status has drifted.

    Returns:
        {"updated": int, "skipped": int, "archived": int, "warnings": list[str]}
    """
```

### I3: brainstorm_registry.sync_brainstorm_entities()

```python
def sync_brainstorm_entities(
    db: EntityDatabase,
    full_artifacts_path: str
) -> dict:
    """
    Scan brainstorms/ directory for .prd.md files.
    Register unregistered files as brainstorm entities.

    Returns:
        {"registered": int, "skipped": int}
    """
```

### I4: kb_import.sync_knowledge_bank()

```python
def sync_knowledge_bank(
    memory_db: MemoryDatabase,
    project_root: str,
    artifacts_root: str,
    global_store_path: str
) -> dict:
    """
    Run MarkdownImporter to sync markdown KB entries to semantic memory DB.

    Args:
        memory_db: MemoryDatabase instance
        project_root: absolute repo root
        artifacts_root: relative sub-path (e.g., "docs")
        global_store_path: directory containing memory.db (derived from args.memory_db)

    Returns:
        {"imported": int, "skipped": int}
    """
```

### I5: session-start.sh integration

```bash
run_reconciliation() {
    local python_cmd="$PLUGIN_ROOT/.venv/bin/python"
    local result
    local entity_db="${ENTITY_DB_PATH:-$HOME/.claude/iflow/entities/entities.db}"
    local memory_db="${MEMORY_DB_PATH:-$HOME/.claude/iflow/memory/memory.db}"
    local artifacts_root
    artifacts_root=$(resolve_artifacts_root)

    # Platform-aware timeout (macOS: gtimeout from coreutils, Linux: timeout)
    local timeout_cmd=""
    if command -v gtimeout &>/dev/null; then
        timeout_cmd="gtimeout 5"
    elif command -v timeout &>/dev/null; then
        timeout_cmd="timeout 5"
    fi

    result=$(PYTHONPATH="$SCRIPT_DIR/lib" \
        $timeout_cmd "$python_cmd" -m reconciliation_orchestrator \
        --project-root "$PROJECT_ROOT" \
        --artifacts-root "$artifacts_root" \
        --entity-db "$entity_db" \
        --memory-db "$memory_db" \
        2>/dev/null) || true

    # Timing diagnostics are in the JSON output (elapsed_ms field).
    # stderr is suppressed to prevent JSON corruption.
    # For debugging, run the orchestrator manually with --verbose flag
    # which writes to a log file instead of stderr.
}
```

**Insertion point:** In `main()`, between `build_memory_context()` (line 451) and `build_context()` (line 454).

### I6: abandon-feature.md command interface

**Invocation:** `/iflow:abandon-feature [--feature={id}-{slug}]`

**Arguments:**
| Arg | Type | Required | Description |
|-----|------|----------|-------------|
| `--feature` | str | no | Feature to abandon. If omitted, uses active feature. |

**Flow:**
1. Resolve feature (arg or active)
2. Read `.meta.json`, verify status is "active" or "planned" (valid starting states for abandonment)
   - If status is "completed": error "Feature already completed. Cannot abandon."
   - If status is "abandoned": error "Feature already abandoned."
3. Confirm: "Abandon feature {id}-{slug}? This cannot be undone." (skip in YOLO mode)
4. Write `.meta.json` with `status: "abandoned"`
5. Call `update_entity(type_id="feature:{id}-{slug}", status="abandoned")` MCP tool
6. If MCP fails: warn, continue (session-start reconciliation resolves drift)
7. Output: `Feature {id}-{slug} abandoned.`

**Does NOT:**
- Call `complete_phase` or modify `workflow_phases`
- Run retro, merge, or cleanup
- Delete the feature branch or folder

**Output includes:** `Branch feature/{id}-{slug} left intact. Delete manually with 'git branch -D feature/{id}-{slug}' if no longer needed.`

### I7: cleanup-brainstorms.md modification

**After each file deletion, add:**
```
Call update_entity MCP tool:
  update_entity(type_id="brainstorm:{filename_stem}", status="archived")

If MCP call fails or entity not found:
  Warn "Entity update skipped for {filename_stem}" and continue
```

### I8: show-status.md migration

**Replace Section 1.5 (Project Features), Section 2 (Open Features), and Section 3 (Open Brainstorms) data sources:**

**Current:** Filesystem scan → read `.meta.json` per feature folder
**New (MCP available):**
```
1. Call search_entities(entity_type="feature") → all feature entities
2. For each entity:
   - status from entity["status"]
   - project_id from entity.metadata (if present)
   - For active features: call get_phase(feature_type_id=entity.type_id)
3. Call search_entities(entity_type="brainstorm") → all brainstorm entities
4. Filter: status != "promoted" AND status != "archived"
5. For each: get file age from artifact_path mtime (if file still exists)
```

**Note:** `search_entities` MCP tool supports `entity_type` filter and returns all matching entities. Status filtering (e.g., excluding "completed") must be done client-side by the LLM after receiving results. The tool does not support `NOT IN` or multi-value exclusion filters.

**Fallback (MCP unavailable):** Existing filesystem scanning preserved unchanged.

**Output change:** Add footer line:
- MCP path: `Source: entity-registry`
- Fallback path: `Source: filesystem`

## Dependency Graph

```
Phase 1 (no dependencies between tasks):
  C1 (orchestrator) ← C2 (entity_status) + C3 (brainstorm_registry) + C4 (kb_import)
  session-start.sh modification (I5) depends on C1

Phase 2 (depends on Phase 1 for entity consistency):
  C5 (abandon-feature) — standalone command, no code dependencies
  C6 (cleanup-brainstorms mod) — standalone command edit, no code dependencies

Phase 3 (depends on Phase 1 for entity data; soft dependency on Phase 2 for abandoned status accuracy):
  C7 (show-status migration) — functional after Phase 1; Phase 2 only needed for abandoned features to appear correctly
```
