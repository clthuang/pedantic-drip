"""MCP entity server for unified lineage tracking of iflow entities.

Runs as a subprocess via stdio transport.  Never print to stdout
(corrupts JSON-RPC protocol) -- all logging goes to stderr.
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager

# Make entity_registry and semantic_memory importable from hooks/lib/.
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

from entity_registry.backfill import run_backfill
from entity_registry.database import EntityDatabase
from entity_registry.server_helpers import (
    _process_export_entities,
    _process_export_lineage_markdown,
    _process_get_lineage,
    _process_register_entity,
    _process_set_parent,
    parse_metadata,
)
from semantic_memory.config import read_config

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Module-level globals (set during lifespan)
# ---------------------------------------------------------------------------

_db: EntityDatabase | None = None
_config: dict = {}
_project_root: str = ""
_artifacts_root: str = ""

# ---------------------------------------------------------------------------
# Lifespan handler
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server):
    """Manage DB connection and backfill lifecycle."""
    global _db, _config, _project_root, _artifacts_root

    # Determine DB path (env override for testing, else global store).
    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/iflow/entities/entities.db"),
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    _db = EntityDatabase(db_path)

    # Read config from the project root.
    project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
    _project_root = project_root
    config = read_config(project_root)
    _config = config
    _artifacts_root = os.path.join(project_root, str(config.get("artifacts_root", "docs")))

    # Backfill existing artifacts (idempotency guard inside run_backfill).
    try:
        run_backfill(_db, _artifacts_root)
    except Exception as exc:
        print(f"entity-server: backfill failed: {exc}", file=sys.stderr)

    # Always run workflow_phases backfill (has its own INSERT OR IGNORE idempotency).
    # Called OUTSIDE the backfill_complete guard so newly registered entities
    # get workflow_phases rows on every startup.
    try:
        from entity_registry.backfill import backfill_workflow_phases

        result = backfill_workflow_phases(_db, _artifacts_root)
        if result["created"] > 0:
            print(
                f"entity-server: workflow_phases backfill created {result['created']} rows",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"entity-server: workflow_phases backfill failed: {exc}", file=sys.stderr)

    print(
        f"entity-server: started (db={db_path}, artifacts={_artifacts_root})",
        file=sys.stderr,
    )

    try:
        yield {}
    finally:
        if _db is not None:
            _db.close()
            _db = None
        _config = {}


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("entity-registry", lifespan=lifespan)


@mcp.tool()
async def register_entity(
    entity_type: str,
    entity_id: str,
    name: str,
    artifact_path: str | None = None,
    status: str | None = None,
    parent_type_id: str | None = None,
    metadata: str | None = None,
) -> str:
    """Register a new entity in the lineage registry.

    Parameters
    ----------
    entity_type:
        One of: backlog, brainstorm, project, feature.
    entity_id:
        Unique identifier within the entity_type namespace
        (e.g. '029-entity-lineage-tracking').
    name:
        Human-readable name (e.g. 'Entity Lineage Tracking').
    artifact_path:
        Optional filesystem path to the entity's artifact.
    status:
        Optional status string.
    parent_type_id:
        Optional type_id of the parent entity (e.g. 'project:my-project').
    metadata:
        Optional JSON string of additional metadata.

    Returns confirmation message or error.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"

    return _process_register_entity(
        _db, entity_type, entity_id, name,
        artifact_path, status, parent_type_id,
        parse_metadata(metadata),
    )


@mcp.tool()
async def set_parent(type_id: str, parent_type_id: str) -> str:
    """Set or change the parent of an entity.

    Parameters
    ----------
    type_id:
        The entity to update (e.g. 'feature:029-entity-lineage-tracking').
    parent_type_id:
        The new parent entity (e.g. 'project:my-project').

    Returns confirmation message or error.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"

    return _process_set_parent(_db, type_id, parent_type_id)


@mcp.tool()
async def get_entity(type_id: str) -> str:
    """Retrieve a single entity by type_id.

    Parameters
    ----------
    type_id:
        Entity identifier (e.g. 'feature:029-entity-lineage-tracking').

    Returns JSON representation of the entity or not-found message.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"

    entity = _db.get_entity(type_id)
    if entity is None:
        return f"Entity not found: {type_id}"
    for key in ("uuid", "entity_id", "parent_uuid"):
        entity.pop(key, None)
    return json.dumps(entity, separators=(",", ":"))


@mcp.tool()
async def get_lineage(
    type_id: str,
    direction: str = "up",
    max_depth: int = 10,
) -> str:
    """Traverse the entity hierarchy and display as a tree.

    Parameters
    ----------
    type_id:
        Starting entity (e.g. 'feature:029-entity-lineage-tracking').
    direction:
        'up' walks toward root (ancestry), 'down' walks toward leaves
        (descendants). Default: 'up'.
    max_depth:
        Maximum levels to traverse (default: 10, AC-14 depth guard).

    Returns formatted tree string or error message.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"

    return _process_get_lineage(_db, type_id, direction, max_depth)


@mcp.tool()
async def update_entity(
    type_id: str,
    name: str | None = None,
    status: str | None = None,
    artifact_path: str | None = None,
    metadata: str | None = None,
) -> str:
    """Update mutable fields of an existing entity.

    Parameters
    ----------
    type_id:
        Entity to update (e.g. 'feature:029-entity-lineage-tracking').
    name:
        New name (if provided).
    status:
        New status (if provided).
    artifact_path:
        New artifact_path (if provided).
    metadata:
        JSON string of metadata to shallow-merge. Empty object '{}' clears.

    Returns confirmation message or error.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        _db.update_entity(
            type_id, name=name, status=status,
            artifact_path=artifact_path, metadata=parse_metadata(metadata),
        )
        return f"Updated: {type_id}"
    except Exception as exc:
        return f"Error updating entity: {exc}"


@mcp.tool()
async def export_lineage_markdown(
    type_id: str | None = None,
    output_path: str | None = None,
) -> str:
    """Export entity lineage as a markdown tree.

    Parameters
    ----------
    type_id:
        If provided, export only the tree rooted at this entity.
        If omitted, export all trees.
    output_path:
        If provided, write markdown to this file path (relative paths
        resolved against artifacts_root). Returns confirmation.
        If omitted, returns the markdown string directly.

    Returns markdown string or file-write confirmation.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"

    return _process_export_lineage_markdown(_db, type_id, output_path, _artifacts_root)


@mcp.tool()
async def export_entities(
    entity_type: str | None = None,
    status: str | None = None,
    output_path: str | None = None,
    include_lineage: bool = True,
    fields: str | None = None,
) -> str:
    """Export all entities (or a filtered subset) as structured JSON.

    Parameters
    ----------
    entity_type:
        Filter by type (backlog, brainstorm, project, feature).
    status:
        Filter by status string.
    output_path:
        Write to file; if None, return as string.
    include_lineage:
        Include parent/child relationships (default True).
    fields:
        Comma-separated field names to include per entity (e.g.
        'type_id,name,status'). If omitted, all fields returned.

    Returns JSON string or file-write confirmation.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"
    return _process_export_entities(
        _db, entity_type, status, output_path, include_lineage, _artifacts_root,
        fields=fields,
    )


@mcp.tool()
async def search_entities(
    query: str,
    entity_type: str | None = None,
    limit: int = 20,
) -> str:
    """Full-text search across all entities.

    Parameters
    ----------
    query:
        Search string (prefix-matched, sanitized).
    entity_type:
        Optional filter by entity_type.
    limit:
        Max results (default 20, max 100).

    Returns formatted search results or error message.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        results = _db.search_entities(query, entity_type=entity_type, limit=limit)
    except ValueError as exc:
        return f"Search error: {exc}"

    if not results:
        return f'No entities found matching "{query}".'

    n = len(results)
    lines = [f'Found {n} entities matching "{query}":\n']
    for i, r in enumerate(results, 1):
        # Intentional UX deviation from spec: use "no status" fallback instead
        # of empty parens when status is None/empty. Spec shows bare "()" but
        # "no status" is clearer for human readers.
        status = r.get("status") or "no status"
        lines.append(f'{i}. {r["type_id"]} — "{r["name"]}" ({status})')
    lines.append(f"\n{n} results shown (limit: {limit}).")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
