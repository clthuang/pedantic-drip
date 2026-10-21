# Design: Entity Lineage Tracking

## Prior Art Research

### Codebase Findings (18 items)

**Existing SQLite Infrastructure (critical for reuse):**
- `MemoryDatabase` class at `plugins/iflow/hooks/lib/semantic_memory/database.py` — full SQLite persistence with WAL mode, NORMAL synchronous, busy timeout, cache sizing
- Schema migration system via numbered `MIGRATIONS` dict + `_metadata` table version tracking
- Content-addressed IDs: `SHA-256(normalized_text)[:16]` — proven pattern for deterministic, collision-resistant IDs
- Upsert with `BEGIN IMMEDIATE` for TOCTOU safety under concurrent access
- FTS5 full-text search with auto-sync triggers (INSERT/DELETE/UPDATE)
- MCP server at `plugins/iflow/mcp/memory_server.py` — FastMCP (stdio transport), lifespan-managed DB connection, narrow purpose-built tools (`store_memory`, `search_memory`)
- Global store at `~/.claude/iflow/memory/` — cross-project, persists across sessions
- Python >=3.10 runtime via `plugins/iflow/.venv`, core deps: numpy, python-dotenv

**Entity Scanning Patterns:**
- `show-status` scans `{iflow_artifacts_root}/features/*/.meta.json` for active features, groups by `project_id` — Glob+Read scan pattern
- `decomposing` skill creates planned features with `project_id`, `module`, `depends_on_features` in `.meta.json`
- Entity resolution uses wildcard glob: `{iflow_artifacts_root}/features/{id}-*/`

**Lineage Field Population:**
- `create-feature` handles `brainstorm_source` (path) and `backlog_source` (5-digit ID) via regex `\*Source: Backlog #(\d{5})\*`
- `create-feature` currently deletes backlog row on promotion
- `decomposing` writes `project_id` and `depends_on_features` on planned features
- No `parent` field exists — all lineage is implicit

**`.meta.json` Schema:**
- Core fields: id, slug, mode, status, created, completed, branch
- Source tracking: brainstorm_source, backlog_source, project_id, depends_on_features
- 28 existing features, 0 projects

### External Findings (16 items)

**Tree Storage Patterns in SQLite:**
- **Adjacency List** — simplest: each row has `parent_id` column. Recursive CTEs (`WITH RECURSIVE`) handle ancestor/descendant queries. Best for small trees (<1000 nodes) with infrequent deep traversals. Our use case: <200 entities, max depth 4.
- **Closure Table** — nodes table + ancestor-descendant pairs with depth. O(1) ancestor/descendant lookups but O(n) writes on insert. Overkill for our scale.
- **Materialized Path** — path string column (e.g., `/backlog/brainstorm/feature`). Good read/write balance but string manipulation for queries. Fragile under reparenting.
- **Decision:** Adjacency list with recursive CTEs — simplest, sufficient at our scale, well-supported by SQLite.

**DB Design for LLM Agents:**
- YAML outperforms JSON for LLM comprehension (structure recognition, lower token count) — use YAML for DB content fields where applicable
- Narrow purpose-built write tools (not raw SQL) — LLMs make fewer errors with constrained interfaces like `register_entity(type, id, name)` than with `execute_sql(query)`
- Idempotent operation patterns — `register_entity` should be a safe no-op if entity already exists, not an error
- Immutable field enforcement via SQLite triggers or `BEFORE UPDATE` checks — prevents accidental overwrites of `entity_type`, `created_at`
- sqlite-utils library: auto-schema from dicts, upsert, content-addressable PKs — but we already have a proven pattern in `MemoryDatabase`
- Simon Willison's llm CLI pattern: SQLite source-of-truth, markdown export for visibility — exact match for user requirement

**Tree Rendering:**
- Unicode box-drawing: `├─` (branch), `└─` (last child), `│` (continuation)
- Recursive depth-first with `is_last` flag to choose `└─` vs `├─`

## Architecture Overview

Entity Lineage Tracking introduces a **unified entity registry database** (SQLite) as the single source of truth for entity identity, relationships, and core metadata. LLM agents interact with entities exclusively through narrow MCP tools. Human-readable markdown is generated from the DB on demand.

**Core architectural shift:** Instead of parsing `.meta.json` fields, scanning brainstorm files for regex markers, and editing markdown table rows — all operations that are fragile when performed by LLM text manipulation — the system uses a programmatic SQLite database with immutable field enforcement, referential integrity, and deterministic queries.

```
                    ┌──────────────────────────────────────┐
                    │  Entity Registry DB (SQLite)         │
                    │  ~/.claude/iflow/entities/entities.db │
                    │                                      │
                    │  ┌──────────┐  ┌──────────────────┐  │
                    │  │ entities │  │ _metadata        │  │
                    │  │ table    │  │ (schema version) │  │
                    │  └──────────┘  └──────────────────┘  │
                    └──────────┬───────────────────────────┘
                               │
              ┌────────────────┼────────────────────┐
              │                │                     │
    ┌─────────▼──────┐  ┌─────▼──────────┐  ┌──────▼───────────┐
    │  Entity MCP    │  │  /show-lineage  │  │  Existing cmds   │
    │  Server        │  │  command        │  │  (create-feature │
    │                │  │                 │  │   create-project │
    │  register_     │  │  Queries DB     │  │   decomposing)   │
    │  entity        │  │  via MCP tools  │  │                  │
    │  set_parent    │  │  Renders tree   │  │  Call MCP tools  │
    │  get_lineage   │  │  output         │  │  to register     │
    │  update_entity │  │                 │  │  entities + set   │
    │  export_md     │  │                 │  │  parent refs      │
    └────────────────┘  └────────────────┘  └──────────────────┘
```

**Data flow — entity creation:**
1. `create-feature` (or other command) creates the feature directory + `.meta.json` (workflow state)
2. Command calls `register_entity` MCP tool with entity type, ID, name, artifact path
3. Command calls `set_parent` MCP tool to establish the parent relationship
4. DB enforces: immutable fields (triggers), single parent (column constraint), parent existence (validation)

**Data flow — lineage query:**
1. `/show-lineage --feature=029` calls `get_lineage` MCP tool
2. MCP tool runs recursive CTE query against DB → returns ancestor chain as structured data
3. Command renders the tree output with Unicode box-drawing

**Data flow — markdown export:**
1. User or automation calls `export_lineage_markdown` MCP tool
2. Tool queries the full entity tree from DB
3. Generates human-readable markdown file at `{iflow_artifacts_root}/entity-registry.md`

### Key Architectural Decisions

1. **Separate DB from memory.db** — Entity registry is a distinct domain from semantic memory. Separate `~/.claude/iflow/entities/entities.db` avoids coupling entity lifecycle to memory system upgrades. Same global location pattern (`~/.claude/iflow/`) for cross-project persistence.

2. **MCP tools as the exclusive write interface** — LLM agents never write SQL directly. Narrow tools (`register_entity`, `set_parent`) constrain operations to valid state transitions. This eliminates the fragility of text-based entity management.

3. **Adjacency list with recursive CTEs** — Simplest tree storage pattern. At <200 entities, recursive CTE traversal is negligible cost. Avoids complexity of closure tables or materialized paths.

4. **`.meta.json` continues for workflow state** — The DB owns entity identity and relationships. `.meta.json` continues to own workflow-specific state (phases, mode, branch). This avoids a disruptive migration of the entire workflow system within this feature's scope.

5. **Backfill on first use** — When the MCP server starts and the DB is empty, it scans existing `features/`, `projects/`, `brainstorms/`, and `backlog.md` to populate the registry. This is a one-time operation, idempotent on subsequent starts.

6. **Phase A/B merge** — The spec defines Phase A (read-only lineage derivation) and Phase B (write-path changes to `create-feature`/`create-project`). The DB-centric architecture delivers both phases simultaneously: the MCP server provides both read (query lineage) and write (register entity) tools from day one. The `gap-log.md` gate (I8) still applies — broader DB scope expansion (replacing more `.meta.json` fields) requires 5+ lineage invocations across 2+ entity types first.

## Components

### C1: Entity Registry Database (`plugins/iflow/hooks/lib/entity_registry/database.py`)

**New file.** Python module following the `MemoryDatabase` pattern.

**Schema:**

```sql
CREATE TABLE entities (
    type_id       TEXT PRIMARY KEY,   -- "feature:029-entity-lineage-tracking"
    entity_type   TEXT NOT NULL       -- "backlog", "brainstorm", "project", "feature"
                  CHECK(entity_type IN ('backlog', 'brainstorm', 'project', 'feature')),
    entity_id     TEXT NOT NULL,      -- "029-entity-lineage-tracking"
    name          TEXT NOT NULL,      -- human-readable display name
    status        TEXT,               -- "active", "completed", "promoted", "planned", "abandoned"
    parent_type_id TEXT REFERENCES entities(type_id),  -- FK, NULL for roots
    artifact_path TEXT,               -- relative path to doc: "docs/features/029-entity-lineage-tracking/"
    created_at    TEXT NOT NULL,      -- ISO-8601, immutable after creation
    updated_at    TEXT NOT NULL,      -- ISO-8601, updated on any mutation
    metadata      TEXT                -- JSON blob for type-specific extras
);

CREATE TABLE _metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Immutable field enforcement
CREATE TRIGGER enforce_immutable_type_id
    BEFORE UPDATE OF type_id ON entities
    BEGIN SELECT RAISE(ABORT, 'type_id is immutable'); END;

CREATE TRIGGER enforce_immutable_entity_type
    BEFORE UPDATE OF entity_type ON entities
    BEGIN SELECT RAISE(ABORT, 'entity_type is immutable'); END;

CREATE TRIGGER enforce_immutable_created_at
    BEFORE UPDATE OF created_at ON entities
    BEGIN SELECT RAISE(ABORT, 'created_at is immutable'); END;

-- Tree constraint: prevent self-referencing parent
CREATE TRIGGER enforce_no_self_parent
    BEFORE INSERT ON entities
    WHEN NEW.parent_type_id = NEW.type_id
    BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END;

CREATE TRIGGER enforce_no_self_parent_update
    BEFORE UPDATE OF parent_type_id ON entities
    WHEN NEW.parent_type_id = NEW.type_id
    BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END;

-- Performance indexes
CREATE INDEX idx_parent ON entities(parent_type_id);
CREATE INDEX idx_entity_type ON entities(entity_type);
CREATE INDEX idx_status ON entities(status);
```

**Class: `EntityDatabase`**

```python
class EntityDatabase:
    def __init__(self, db_path: str) -> None:
        # Pragmas: WAL, NORMAL sync, busy_timeout=5000, cache_size=-8000
        # CRITICAL: PRAGMA foreign_keys = ON (required for parent_type_id FK enforcement)
        # Auto-migrate on init

    def register_entity(self, type_id: str, entity_type: str, entity_id: str,
                        name: str, artifact_path: str | None = None,
                        status: str | None = None, parent_type_id: str | None = None,
                        metadata: dict | None = None) -> str:
        # Idempotent: if type_id exists, return "already registered" without modifying fields
        # (INSERT OR IGNORE semantics — callers use update_entity for field changes)
        # Validates parent_type_id exists if provided
        # Validates no circular reference (max 10 hops check)
        # Returns "registered" or "already registered"

    def set_parent(self, type_id: str, parent_type_id: str) -> str:
        # Validates both entities exist
        # Validates no circular reference
        # Updates parent_type_id
        # Returns confirmation

    def get_entity(self, type_id: str) -> dict | None:
        # Simple SELECT by primary key

    def get_lineage(self, type_id: str, direction: str = "up",
                    max_depth: int = 10) -> list[dict]:
        # direction="up": Recursive CTE upward traversal → [root, ..., target]
        # direction="down": Recursive CTE downward traversal → [target, child1, child2, ...]

    def update_entity(self, type_id: str, name: str | None = None,
                      status: str | None = None, metadata: dict | None = None) -> str:
        # Updates mutable fields only (name, status, metadata)
        # Immutable fields enforced by triggers
        # Metadata merge: shallow dict merge — keys in incoming dict overwrite matching keys
        # in stored metadata; omitted keys are preserved; pass empty dict {} to clear all metadata

    def export_lineage_markdown(self, type_id: str | None = None) -> str:
        # Generate full tree as human-readable markdown
        # If type_id is None, export all trees (all roots and their descendants)
```

**Recursive CTE for ancestor chain:**

```sql
WITH RECURSIVE ancestors(type_id, entity_type, entity_id, name, status,
                         parent_type_id, artifact_path, created_at,
                         updated_at, metadata, depth) AS (
    -- Base case: the target entity
    SELECT *, 0 AS depth FROM entities WHERE type_id = ?
    UNION ALL
    -- Recursive step: follow parent_type_id upward
    SELECT e.*, a.depth + 1
    FROM entities e
    JOIN ancestors a ON e.type_id = a.parent_type_id
    WHERE a.depth < ?  -- max_depth parameter
)
SELECT * FROM ancestors ORDER BY depth DESC;  -- root first
```

**Recursive CTE for descendants:**

```sql
WITH RECURSIVE descendants(type_id, entity_type, entity_id, name, status,
                           parent_type_id, artifact_path, created_at,
                           updated_at, metadata, depth) AS (
    SELECT *, 0 AS depth FROM entities WHERE type_id = ?
    UNION ALL
    SELECT e.*, d.depth + 1
    FROM entities e
    JOIN descendants d ON e.parent_type_id = d.type_id
    WHERE d.depth < ?
)
SELECT * FROM descendants ORDER BY depth, entity_id;
```

**Circular reference detection for `set_parent`:**

```sql
-- Before setting child.parent_type_id = proposed_parent,
-- walk UP from proposed_parent. If we reach child, it's circular.
-- ? = proposed_parent, ?? = child (entity being reparented)
WITH RECURSIVE ancestors(type_id, parent_type_id, depth) AS (
    SELECT type_id, parent_type_id, 0 FROM entities WHERE type_id = ?  -- proposed parent
    UNION ALL
    SELECT e.type_id, e.parent_type_id, a.depth + 1
    FROM entities e
    JOIN ancestors a ON e.type_id = a.parent_type_id  -- follow parent_type_id upward
    WHERE a.depth < 10
)
SELECT 1 FROM ancestors WHERE type_id = ?;  -- bind: child_type_id (the entity being reparented)
```

This uses the same upward-traversal pattern as `get_lineage` — no self-referencing subquery.

**Multi-project isolation:** Entity `type_id` values are inherently project-scoped because:
- Feature IDs include the slug (globally unique across projects)
- Brainstorm IDs include timestamps (globally unique)
- Backlog IDs are project-local but collisions are benign — `backlog:00001` in two projects will have different names/artifact_paths
- The DB is global (`~/.claude/iflow/entities/`) by design (same pattern as memory.db), enabling cross-project lineage queries (e.g., "show all features I've built")

**Known limitation:** Backlog ID collisions across projects result in first-writer-wins semantics. The entity's name and artifact_path will reflect whichever project first registered the ID. Acceptable at current scale (single active project) but would need a `project_root` qualifier if multi-project concurrent use becomes common. A `project_root` column can be added additively without schema-breaking changes.

**Migration system:** Same pattern as `MemoryDatabase` — numbered `MIGRATIONS` dict, `_metadata` table for version tracking.

### C2: Entity MCP Server (`plugins/iflow/mcp/entity_server.py`)

**New file.** FastMCP server following `memory_server.py` pattern.

**Transport:** stdio (same as memory server)

**Lifespan:**
- Reads project root from `os.getcwd()` at server start
- Reads `artifacts_root` from `.claude/iflow.local.md` via `read_config()` (reuse existing `semantic_memory.config` module, default: `docs`)
- Opens `EntityDatabase` at `~/.claude/iflow/entities/entities.db`
- On first start (empty DB): runs backfill scan (see C3) with `project_root` and `artifacts_root`
- Closes DB on shutdown

**MCP Tools (6 tools):**

| Tool | Purpose | Mutates DB |
|------|---------|------------|
| `register_entity` | Create new entity in registry | Yes |
| `set_parent` | Set/change parent relationship | Yes |
| `get_entity` | Retrieve single entity details | No |
| `get_lineage` | Get ancestor chain (up) or descendant tree (down) | No |
| `update_entity` | Update mutable fields (name, status, metadata) | Yes |
| `export_lineage_markdown` | Generate human-readable lineage view | No |

**Tool signatures:**

```python
@mcp.tool()
async def register_entity(
    entity_type: str,       # "backlog", "brainstorm", "project", "feature"
    entity_id: str,         # "029-entity-lineage-tracking"
    name: str,              # "Entity Lineage Tracking"
    artifact_path: str | None = None,  # "docs/features/029-entity-lineage-tracking/"
    status: str | None = None,
    parent_type_id: str | None = None,  # "brainstorm:20260227-054029-entity-lineage-tracking"
    metadata: str | None = None,  # JSON string
) -> str:
    """Register a new entity in the entity registry.
    Idempotent: returns success if entity already exists with same type_id.
    type_id is auto-generated as "{entity_type}:{entity_id}"."""

@mcp.tool()
async def set_parent(
    type_id: str,           # "feature:029-entity-lineage-tracking"
    parent_type_id: str,    # "brainstorm:20260227-054029-entity-lineage-tracking"
) -> str:
    """Set the parent of an entity. Validates parent exists and no circular reference."""

@mcp.tool()
async def get_entity(
    type_id: str,           # "feature:029-entity-lineage-tracking"
) -> str:
    """Get entity details. Returns YAML-formatted entity data."""

@mcp.tool()
async def get_lineage(
    type_id: str,           # "feature:029-entity-lineage-tracking"
    direction: str = "up",  # "up" for ancestors, "down" for descendants
    max_depth: int = 10,
) -> str:
    """Get lineage tree. Returns formatted tree with Unicode box-drawing."""

@mcp.tool()
async def update_entity(
    type_id: str,
    name: str | None = None,
    status: str | None = None,
    metadata: str | None = None,  # JSON string, merged with existing
) -> str:
    """Update mutable fields of an entity. Immutable fields (type, created_at) are protected."""

@mcp.tool()
async def export_lineage_markdown(
    type_id: str | None = None,  # None = export all trees
    output_path: str | None = None,  # None = return as text
) -> str:
    """Export lineage as human-readable markdown. Optionally write to file.
    output_path resolution: relative paths are resolved against artifacts_root (from iflow.local.md config);
    absolute paths are used as-is. Callers should use relative paths (e.g., 'entity-registry.md')."""
```

### C3: Backfill Scanner (`plugins/iflow/hooks/lib/entity_registry/backfill.py`)

**New file.** One-time migration from existing flat files to DB.

**Triggered:** On MCP server startup when DB has zero entities.

**Scan logic:**
1. **Features:** Glob `{artifacts_root}/features/*/.meta.json` → register each as `feature:{id}-{slug}`, extract `brainstorm_source`/`backlog_source`/`project_id` to set parent
2. **Projects:** Glob `{artifacts_root}/projects/*/.meta.json` → read `.meta.json`, derive entity_id from the `id` field (same core field used by features, e.g., `P001`), register each as `project:{id}`, extract `brainstorm_source` to set parent
3. **Brainstorms:** Glob `{artifacts_root}/brainstorms/*.prd.md` first, then `{artifacts_root}/brainstorms/*.md` for remaining unregistered files. Priority: `.prd.md` files scanned first; `.md` files only if their stem was not already registered (register_entity idempotency makes double-registration safe as a fallback). Stem extraction: strip directory prefix and file extension (`.prd.md` or `.md`). Register each as `brainstorm:{stem}`, parse `*Source: Backlog #ID*` marker to set parent
4. **Backlog:** Read `{artifacts_root}/backlog.md` → register each row as `backlog:{id}`

**Parent derivation during backfill (replaces C3 from old design):**
- Feature with `project_id` → parent is `project:{project_id}`
- Feature with `brainstorm_source` (no project_id) → parent is `brainstorm:{filename-stem}`
- Feature with `backlog_source` (no brainstorm, no project) → parent is `backlog:{id}`
- Brainstorm with `*Source: Backlog #ID*` marker → parent is `backlog:{id}`
- Brainstorm with `**Backlog Item:** ID` marker → parent is `backlog:{id}` (older format)
- Brainstorm without marker but linked from feature with `backlog_source` → parent set via feature's context (the feature already points to both brainstorm and backlog)
- Feature with `brainstorm_source` pointing outside `{artifacts_root}/brainstorms/` (external path) → create synthetic brainstorm entity with `artifact_path` set to the external path and `status="external"`. This preserves the lineage link even when the file is not in the standard location (aligns with spec AC-7's "(external reference)" handling)

**Orphaned backlog handling:** When a feature has `backlog_source` pointing to a backlog ID (e.g., `00019`) but that ID is not found in `backlog.md` (already deleted/promoted), backfill registers a synthetic backlog entity:
```python
register_entity(
    entity_type="backlog", entity_id="00019",
    name="(backlog item deleted)", status="orphaned",
    artifact_path=None
)
```
This preserves the lineage chain (feature → brainstorm → backlog) even when the original backlog row is gone. The `orphaned` status signals the entity was reconstructed from references.

**Feature metadata extraction:** During feature backfill, extract `depends_on_features` from `.meta.json` if present and store in entity `metadata` JSON field as `{"depends_on_features": [...]}`. This enables descendant tree display (AC-5) to show dependency annotations.

**Topological ordering:** Backfill registers entities in dependency order: backlog → brainstorm → project → feature. This ensures parent entities exist before children reference them (required by FK constraint with `PRAGMA foreign_keys = ON`).

**Scope limitation:** Backfill only scans the primary `{artifacts_root}` directory. The `backfill_scan_dirs` config field (used by knowledge bank for cross-project scans) is not supported for entity backfill — entities are project-scoped by artifacts_root.

**Idempotency:** `register_entity` is idempotent — running backfill multiple times is safe.

### C4: `/show-lineage` Command (`plugins/iflow/commands/show-lineage.md`)

**New file.** Command markdown that uses MCP tools instead of file scanning.

**Responsibilities:**
- Parse arguments (`--feature`, `--project`, `--backlog`, `--brainstorm`, `--descendants`)
- Detect current feature from git branch when no argument provided: extract feature ID from branch name using `feature/{id}-{slug}` pattern (regex: `^feature/(.+)$`); if branch does not match, output error message and exit
- Call `get_lineage` MCP tool with appropriate `type_id` and `direction`
- Display the formatted tree output returned by the MCP tool

**Internal logic sections:**
1. Argument Parsing — resolve entity `type_id` from arguments or branch
2. MCP Tool Call — `get_lineage(type_id, direction="up"|"down")`
3. Output Display — tree is pre-formatted by MCP tool, command displays it
4. Error Handling — entity not found, depth limit, etc.

**Key simplification vs old design:** The command is a thin wrapper around MCP tool calls. No file scanning, no regex parsing, no path normalization. All that complexity lives in the DB layer.

### C5: Modified `create-feature.md` — Entity Registration

**Existing file modified.** After creating the feature directory and `.meta.json`:

1. Call `register_entity` MCP tool:
   ```
   register_entity(
     entity_type="feature",
     entity_id="{id}-{slug}",
     name="{slug}",
     artifact_path="docs/features/{id}-{slug}/",
     status="active",
     parent_type_id="{derived from brainstorm_source or backlog_source}"
   )
   ```

2. If brainstorm source exists, also ensure brainstorm is registered:
   ```
   register_entity(
     entity_type="brainstorm",
     entity_id="{filename-stem}",
     name="{title from first heading}",
     artifact_path="docs/brainstorms/{filename}.prd.md"
   )
   ```

3. **Backlog mark-as-promoted:** Instead of deleting the backlog row, call:
   ```
   update_entity(type_id="backlog:{id}", status="promoted")
   ```
   The backlog.md row is also annotated with `(promoted → feature:{id}-{slug})` for human readability (the DB is the source of truth, the markdown annotation is for visibility only).

**MCP failure handling:** If any entity MCP tool call fails (server unavailable, timeout, tool error), warn the user but do NOT block feature creation. The feature directory and `.meta.json` are created first — DB registration is an enhancement. Output: `"Warning: Entity registry unavailable — entity not registered. Feature created successfully."`

### C6: Modified `create-project` and `decomposing` — Entity Registration

**Existing files modified.** Same pattern as C5:

**`create-project`:**
- Register project entity with `register_entity`
- Set parent to brainstorm (if PRD source provided)
- Parse brainstorm for backlog source, register/update backlog entity

**`decomposing`:**
- When creating planned features, call `register_entity` for each with `parent_type_id="project:{project_id}"`

**MCP failure handling (both):** Same as C5 — warn but do not block project/feature creation if entity MCP tools are unavailable.

### C7: `brainstorming` Skill — Entity Registration

**Existing file modified.** After creating brainstorm PRD file:
- Call `register_entity` to register the brainstorm
- If brainstorm originated from backlog (`*Source: Backlog #ID*`), set parent to `backlog:{id}`

**MCP failure handling:** Same as C5 — warn but do not block brainstorm creation if entity MCP tools are unavailable.

### C8: MCP Server Registration and Bootstrap

**Registration file:** `plugins/iflow/.claude-plugin/plugin.json` — add `entity-registry` key to existing `mcpServers` object:

```json
{
  "mcpServers": {
    "memory-server": {
      "command": "${CLAUDE_PLUGIN_ROOT}/mcp/run-memory-server.sh",
      "args": []
    },
    "entity-registry": {
      "command": "${CLAUDE_PLUGIN_ROOT}/mcp/run-entity-server.sh",
      "args": []
    }
  }
}
```

**Bootstrap wrapper:** `plugins/iflow/mcp/run-entity-server.sh` — new file following `run-memory-server.sh` pattern:

```bash
#!/bin/bash
# Bootstrap and run the MCP entity registry server.
# Resolution order: existing venv → system python3 → auto-bootstrap venv.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"
SERVER_SCRIPT="$SCRIPT_DIR/entity_server.py"

export PYTHONPATH="$PLUGIN_DIR/hooks/lib${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

# Fast path: existing venv
if [[ -x "$VENV_DIR/bin/python" ]]; then
    exec "$VENV_DIR/bin/python" "$SERVER_SCRIPT"
fi

# System python3 with required deps
if python3 -c "import mcp.server.fastmcp" 2>/dev/null; then
    exec python3 "$SERVER_SCRIPT"
fi

# Bootstrap: create venv and install core deps (one-time) using uv
echo "entity-server: bootstrapping venv at $VENV_DIR..." >&2
if command -v uv &>/dev/null; then
    uv venv "$VENV_DIR" >&2
    uv pip install --python "$VENV_DIR/bin/python" "mcp>=1.0,<2" >&2
else
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -q "mcp>=1.0,<2" >&2
fi
exec "$VENV_DIR/bin/python" "$SERVER_SCRIPT"
```

**Dependencies:** Entity server requires only `mcp>=1.0,<2` (FastMCP transport) + Python stdlib (`sqlite3`, `json`, `os`, `pathlib`). No numpy, dotenv, or other external packages. The existing venv already has `mcp` installed (shared with memory server), so no additional pip install is needed when venv exists.

### C9: Entity ID Canonicalization

**Embedded in EntityDatabase, not a separate component.**

| Entity Type | Canonical type_id Format | Example |
|-------------|--------------------------|---------|
| `feature` | `feature:{id}-{slug}` | `feature:029-entity-lineage-tracking` |
| `project` | `project:{P-id}` | `project:P001` |
| `backlog` | `backlog:{5-digit-id}` | `backlog:00019` |
| `brainstorm` | `brainstorm:{filename-stem}` | `brainstorm:20260227-054029-entity-lineage-tracking` |

**ID validation rules (in `register_entity`):**
- `entity_type` must be one of the 4 allowed values
- `entity_id` must be non-empty
- `type_id` is always auto-generated as `{entity_type}:{entity_id}`
- Bare feature IDs (e.g., `029`) are NOT accepted — caller must provide full `{id}-{slug}`

**Spec alignment note:** Spec line 41 uses `feature:028` (bare numeric) in an example, but the canonical format is always `feature:{id}-{slug}` (e.g., `feature:028-auto-review-loop`). The design normalizes bare IDs during backfill by reading the actual directory name. Commands always generate the full format. This aligns with AC examples throughout the spec which use the full `feature:029-entity-lineage-tracking` form.

### C10: Tree Rendering (inline in `get_lineage` MCP tool response)

**Output format for upward traversal (ancestor chain):**
```
backlog:00019 — "improve data entity lineage..." (promoted, 2026-02-27)
  └─ brainstorm:20260227-054029-entity-lineage-tracking — "Entity Lineage Tracking" (2026-02-27)
       └─ feature:029-entity-lineage-tracking — "entity-lineage-tracking" (active, 2026-02-27)
```

**Output format for downward traversal (descendant tree):**
```
project:P001 — "Project Name" (active, 2026-03-01)
  ├─ feature:030-auth-module — "auth-module" (active, 2026-03-02)
  ├─ feature:031-api-gateway — "api-gateway" (planned, 2026-03-02)
  └─ feature:032-dashboard — "dashboard" (planned, 2026-03-02)
```

**Metadata per entity type:**

| Type | Name Source | Status Values | Extra |
|------|------------|---------------|-------|
| `feature` | `name` from DB | active/completed/planned/abandoned | — |
| `project` | `name` from DB | active/completed | — |
| `backlog` | `name` from DB (description text, truncated 50 chars) | promoted/active | — |
| `brainstorm` | `name` from DB (title from first heading) | — | — |

**Orphaned entity display** (parent_type_id points to non-existent entity):
```
brainstorm:20260201-deleted — (orphaned: parent not found in registry)
  └─ feature:010-deleted-source — "deleted-source" (active)
```

## Technical Decisions

### TD-1: SQLite as Entity Registry (not extending memory.db)

**Choice:** New `~/.claude/iflow/entities/entities.db` database
**Alternatives Considered:** (a) Add entity tables to memory.db, (b) Use JSON file index, (c) Use .meta.json as-is
**Trade-offs:** Separate DB avoids coupling entity lifecycle to memory system. Memory.db has a different access pattern (embedding BLOBs, FTS5 keyword search). Entity registry is simple relational data with tree traversal. Sharing a DB would require coordinating migrations across two domains. JSON index trades DB complexity for index-staleness risk.
**Rejected:** (a) Rejected: avoids schema coupling and allows independent vacuuming/migration. (b) Rejected: index must be rebuilt when entities change, introducing staleness risk. (c) Rejected: user explicitly requested programmatic DB approach over text-based management.
**Rationale:** Same global location pattern (`~/.claude/iflow/`), same SQLite patterns (WAL, migrations, MCP), but independent lifecycle. Clean separation of concerns.
**Evidence:** MemoryDatabase is 600+ lines with domain-specific logic (embeddings, FTS5, keyword processing). Entity registry has none of these needs.

### TD-2: MCP Tools as Exclusive Write Interface

**Choice:** All entity mutations go through MCP tools (`register_entity`, `set_parent`, `update_entity`)
**Alternatives Considered:** (a) Direct DB access from Python modules, (b) CLI wrapper scripts, (c) Raw SQL in command markdown
**Trade-offs:** MCP tools are discoverable by LLM agents, have typed parameters, return structured responses, and enforce validation. Direct DB access would be more flexible but bypasses validation. Raw SQL in command markdown is the exact fragility the user identified.
**Rejected:** (a) Rejected: bypasses constraint enforcement and would require importing Python modules from command markdown. (b) Rejected: adds process overhead and complicates error handling. (c) Rejected: fragile LLM text manipulation — the core problem this feature solves.
**Rationale:** The user's core feedback: "LLM text based to manage the document creation is inherently unstable and fragile. You should look at using programmatic way." MCP tools are the programmatic interface that LLM agents already know how to use.
**Evidence:** `memory_server.py` proves this pattern works — `store_memory` and `search_memory` tools have been reliable across hundreds of sessions.

### TD-3: Adjacency List over Closure Table

**Choice:** Simple `parent_type_id` column with recursive CTEs for traversal
**Alternatives Considered:** (a) Closure Table (node pairs with depth), (b) Materialized Path, (c) Nested Sets
**Trade-offs:** Adjacency list is simplest to implement and understand. Closure table offers O(1) lookups but requires maintaining N*depth rows on insert. At <200 entities with max depth 4, recursive CTE cost is negligible.
**Rationale:** Simplest solution that works at our scale. If entity count grows beyond 1000, upgrade to closure table is additive (new table, no schema change to entities).
**Evidence:** Research confirms adjacency list + recursive CTEs is the standard recommendation for small tree datasets in SQLite.

### TD-4: Backfill on First Startup

**Choice:** Auto-scan existing files to populate empty DB on first MCP server start
**Alternatives Considered:** (a) Manual migration script, (b) Dual-read (check DB, fall back to files), (c) No backfill
**Trade-offs:** Auto-backfill means zero manual intervention. Dual-read adds complexity to every query. No backfill means 27 existing features are invisible until re-created.
**Rejected:** (a) Rejected: requires user to remember to run script; breaks the zero-touch experience. (b) Rejected: doubles code paths and creates two sources of truth for every read. (c) Rejected: 28 features and their lineage relationships are too valuable to discard.
**Rationale:** The 28 existing features and their lineage relationships are valuable. Auto-backfill preserves them. The scan is deterministic and idempotent — running multiple times produces the same result.
**Evidence:** Existing brainstorm→feature links via `brainstorm_source` are present on 20/28 (~71%) of features. This data would be lost without backfill.

### TD-5: `.meta.json` Coexistence During Transition

**Choice:** `.meta.json` continues to own workflow state (phases, mode, branch). Entity registry DB owns identity and relationships.
**Alternatives Considered:** (a) Full migration of .meta.json to DB, (b) DB-only approach (no .meta.json)
**Trade-offs:** Full migration touches every workflow command (specify, design, create-plan, etc.) — massive scope expansion. Coexistence keeps this feature focused on lineage while providing the DB infrastructure for future migration.
**Rejected:** (a) Rejected: touches 8+ workflow commands — massive scope expansion far beyond lineage tracking. (b) Rejected: eliminates human-readable workflow state; .meta.json files are useful for debugging and manual inspection.
**Rationale:** Scope discipline. Entity lineage is the feature; replacing the entire workflow state system is not. The DB infrastructure created here is reusable for future state migration.
**Evidence:** 8+ workflow commands read/write .meta.json. Migrating all of them is a separate multi-session effort.

### TD-6: Immutable Fields via SQLite Triggers

**Choice:** `BEFORE UPDATE` triggers that `RAISE(ABORT)` on attempts to modify `type_id`, `entity_type`, `created_at`
**Alternatives Considered:** (a) Application-level checks in Python, (b) Views with INSTEAD OF triggers, (c) Trust callers
**Trade-offs:** SQLite triggers are enforced regardless of how the DB is accessed — Python code, raw SQL, future tools. Application-level checks only protect the current code path.
**Rejected:** (a) Rejected: only protects the current code path; new tools or direct DB access bypass checks. (b) Rejected: INSTEAD OF triggers add complexity with no practical benefit over BEFORE UPDATE. (c) Rejected: LLM agents are unpredictable; trusting callers is the same fragility the user criticized.
**Rationale:** Defense in depth. LLM agents are unpredictable. Trusting application-level guards is the same fragility the user criticized in text-based approaches. DB-level enforcement is absolute.
**Evidence:** Research confirms triggers as the standard pattern for immutable field enforcement in SQLite.

## Risks

### R1: MCP Server Startup Latency (Backfill)

**Impact:** Medium — first invocation of entity tools is slow during backfill scan
**Likelihood:** Low — backfill only runs once on first startup (empty DB)
**Mitigation:** Backfill scans ~30 features + brainstorms = ~60 file reads. At ~1ms per read, this is <100ms total. Subsequent startups skip backfill (DB already populated).

### R2: Dual-Write Drift Between DB and .meta.json

**Impact:** Medium — entity registered in DB but .meta.json has stale/missing lineage fields
**Likelihood:** Medium — during transition period, both systems coexist
**Mitigation:** DB is the source of truth for lineage. `.meta.json` lineage fields (`brainstorm_source`, `backlog_source`) are read-only legacy — never queried for lineage after backfill. Workflow commands continue writing them for backward compatibility but don't read them for lineage purposes.

### R3: Backfill Accuracy for Pre-010 Brainstorms

**Impact:** Low — some brainstorms may not have their backlog parent set correctly
**Likelihood:** Medium — pre-010 brainstorms may lack `*Source: Backlog*` marker
**Mitigation:** Multi-pattern detection (2 regex patterns). Feature-context fallback: if a feature has `backlog_source` and `brainstorm_source`, the brainstorm's parent is set to the backlog even if the marker is missing. Known limitation documented.

### R4: MCP Server Availability

**Impact:** High — if entity MCP server is down, entity registration fails
**Likelihood:** Low — stdio servers are started by Claude Code automatically
**Mitigation:** Entity registration failure in commands should warn but not block feature creation. The feature directory and .meta.json are created first; DB registration is an enhancement, not a prerequisite.

### R5: Concurrent Access

**Impact:** Low — concurrent entity registration could conflict
**Likelihood:** Very low — single-user tool, sequential workflow
**Mitigation:** SQLite WAL mode supports concurrent reads. Writes use `BEGIN IMMEDIATE` (same pattern as MemoryDatabase). `busy_timeout = 5000ms` handles brief contention.

## Test Strategy

### Unit Tests: `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Framework:** pytest (already in project dev dependencies)
- **Scope:** All `EntityDatabase` methods — register_entity (including INSERT OR IGNORE idempotency), set_parent (including circular reference rejection), get_entity, get_lineage (both up and down), update_entity (including shallow metadata merge), export_lineage_markdown
- **Trigger enforcement:** Verify RAISE(ABORT) on type_id, entity_type, created_at mutation attempts
- **FK constraint:** Verify set_parent rejects non-existent parent_type_id
- **Backfill:** Test `backfill.py` scan logic with fixture directories containing mock .meta.json, brainstorm files, and backlog.md

### Integration Tests: `plugins/iflow/mcp/test_entity_server.sh`
- **Pattern:** Follow `test_run_memory_server.sh` — bash script that starts the server, sends test tool calls, verifies responses
- **Coverage:** Server startup, backfill on empty DB, register_entity round-trip, get_lineage output format, export_lineage_markdown content
- **Bootstrap:** Verify `run-entity-server.sh` starts without errors

## Interfaces

### I1: Entity MCP Server Registration

**File:** `plugins/iflow/.claude-plugin/plugin.json` (existing plugin manifest)

**Addition to `mcpServers` object:**
```json
"entity-registry": {
  "command": "${CLAUDE_PLUGIN_ROOT}/mcp/run-entity-server.sh",
  "args": []
}
```

**Bootstrap wrapper:** `plugins/iflow/mcp/run-entity-server.sh` — see C8 for full specification.

### I2: `register_entity` MCP Tool Interface

**Input:**
```yaml
entity_type: "feature"                           # required, one of: backlog, brainstorm, project, feature
entity_id: "029-entity-lineage-tracking"         # required, type-specific format
name: "Entity Lineage Tracking"                  # required, human-readable
artifact_path: "docs/features/029-entity-lineage-tracking/"  # optional, relative to project root
status: "active"                                 # optional
parent_type_id: "brainstorm:20260227-054029-entity-lineage-tracking"  # optional
metadata: '{"mode": "standard", "branch": "feature/029"}'   # optional, JSON string
```

**Output (success):** `"Registered: feature:029-entity-lineage-tracking"`
**Output (idempotent):** `"Already registered: feature:029-entity-lineage-tracking"`
**Output (error):** `"Error: invalid entity_type 'foo'. Must be one of: backlog, brainstorm, project, feature"`

### I3: `get_lineage` MCP Tool Interface

**Input:**
```yaml
type_id: "feature:029-entity-lineage-tracking"   # required
direction: "up"                                   # optional, "up" or "down", default "up"
max_depth: 10                                     # optional, default 10
```

**Output (upward):**
```
backlog:00019 — "improve data entity lineage..." (promoted, 2026-02-27)
  └─ brainstorm:20260227-054029-entity-lineage-tracking — "Entity Lineage Tracking" (2026-02-27)
       └─ feature:029-entity-lineage-tracking — "entity-lineage-tracking" (active, 2026-02-27)
```

**Output (entity not found):** `"Entity feature:999-nonexistent not found in registry"`
**Output (depth exceeded):** `"Traversal depth limit reached (>10 hops) — possible circular reference. Displaying chain up to limit."`

### I4: `export_lineage_markdown` MCP Tool Interface

**Input:**
```yaml
type_id: null                    # optional, null = export all trees
output_path: "docs/entity-registry.md"  # optional, null = return as text
```

**Output (markdown content):**
```markdown
# Entity Registry

Generated: 2026-02-27T07:30:00Z
Total entities: 34

## Lineage Trees

### backlog:00019
backlog:00019 — "improve data entity lineage..." (promoted, 2026-02-27)
  └─ brainstorm:20260227-054029-entity-lineage-tracking — "Entity Lineage Tracking" (2026-02-27)
       └─ feature:029-entity-lineage-tracking — "entity-lineage-tracking" (active, 2026-02-27)

### Root Entities (no parent)
- feature:001-initial-setup — "initial-setup" (completed, 2026-01-01)
- feature:005-some-feature — "some-feature" (completed, 2026-01-15)
...
```

### I5: `/show-lineage` Command Interface

**Arguments:**
```yaml
---
description: Show entity lineage — ancestry chain or descendant tree
argument-hint: [--feature=ID | --project=ID | --backlog=ID | --brainstorm=STEM] [--descendants]
---
```

**Argument parsing rules:**
- `--feature={id}-{slug}` or `--feature={id}` — resolve to `feature:{id}-{slug}` via DB lookup
- `--project={P-prefixed-id}` — resolve to `project:{id}`
- `--backlog={5-digit-id}` — resolve to `backlog:{id}`
- `--brainstorm={filename-stem}` — resolve to `brainstorm:{stem}`
- `--descendants` — call `get_lineage` with `direction="down"`
- No arguments — detect from current git branch (`feature/{id}-{slug}` pattern)

**Error output:**
- Entity not found: `"Entity {type:id} not found in registry"`
- No argument and not on feature branch: `"No entity specified. Use --feature, --project, --backlog, or --brainstorm, or run from a feature branch."`
- Depth limit: `"Traversal depth limit reached (>10 hops)..."`

### I6: Modified `create-feature.md` — Entity Registration Calls

**Current behavior (Handle Backlog Source, step 3):**
```
- Find row matching | {id} |
- Remove that row
- Write updated backlog
- Display: Linked from backlog item #{id} (removed from backlog)
```

**New behavior:**
```
- Call register_entity MCP tool for the backlog item (idempotent)
- Call update_entity MCP tool to set backlog status to "promoted"
- Find row matching | {id} | in backlog.md
- Append to Description column: (promoted → feature:{id}-{slug})
- Row remains in table (for human readability; DB is source of truth)
- Call register_entity MCP tool for the brainstorm (if applicable)
- Call register_entity MCP tool for the feature with parent_type_id set
- Display: Linked from backlog item #{id} (promoted)
```

### I6b: Modified `create-project` — Entity Registration Calls

**Current behavior (Handle PRD Source):**
```
- Copy PRD file to project folder
- Set brainstorm_source in .meta.json
```

**New behavior:**
```
- Copy PRD file to project folder
- Set brainstorm_source in .meta.json
- Call register_entity MCP tool for the brainstorm (idempotent)
- Parse brainstorm content for *Source: Backlog #ID* marker
- If backlog marker found:
  - Call register_entity MCP tool for the backlog item (idempotent)
  - Call update_entity MCP tool to set backlog status to "promoted"
  - Call set_parent on brainstorm with parent_type_id="backlog:{id}"
- Call register_entity MCP tool for the project with parent_type_id set to brainstorm
- MCP failure handling: warn but do NOT block project creation
```

**Note:** This is a new code path for `create-project` — the existing command does not currently parse brainstorm content for backlog markers. The pattern is ported from `create-feature`'s Handle Backlog Source logic.

### I7: `depends_on_features` Handling

**Not stored in entity registry.** `depends_on_features` represents sibling dependencies within a project, NOT parent-child relationships. It remains in `.meta.json` as workflow metadata.

**Display in lineage tree:** When showing descendants of a project, the `get_lineage` MCP tool reads `depends_on_features` from the entity's `metadata` JSON field (populated during backfill from .meta.json) and appends `[depends on: feature:030]` annotations to the tree output.

### I8: Phase Gate Tracking — `gap-log.md`

**File:** `docs/dev_artifacts/workitems/029-entity-lineage-tracking/gap-log.md` — created during implementation as an empty template with the header structure shown below.

**Retained from original design.** Tracks /show-lineage invocations to validate the DB approach before extending to broader entity management.

**Format:**
```markdown
# Entity Registry Gap Log

## Summary
| Metric | Value |
|--------|-------|
| Invocations | 0 |
| Entity types queried | (none) |
| Gaps observed | (none) |

## Invocation Log
| # | Date | Entity | Type | Query | Gap Found |
|---|------|--------|------|-------|-----------|
```

**Gate criteria:** Summary table shows >= 5 invocations across >= 2 entity types before expanding DB scope to replace more .meta.json fields.
