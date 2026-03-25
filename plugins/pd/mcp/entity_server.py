"""MCP entity server for unified lineage tracking of pd entities.

Runs as a subprocess via stdio transport.  Never print to stdout
(corrupts JSON-RPC protocol) -- all logging goes to stderr.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import threading
import time
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
from sqlite_retry import with_retry

from mcp.server.fastmcp import FastMCP
from server_lifecycle import write_pid, remove_pid, start_parent_watchdog

# ---------------------------------------------------------------------------
# Module-level globals (set during lifespan)
# ---------------------------------------------------------------------------

_db: EntityDatabase | None = None
_db_unavailable: bool = False
_recovery_thread: threading.Thread | None = None
_config: dict = {}
_project_root: str = ""
_artifacts_root: str = ""

_logger = logging.getLogger("entity_server")


# ---------------------------------------------------------------------------
# Degraded mode helpers
# ---------------------------------------------------------------------------


def _init_db_with_retry(
    db_path: str,
    max_retries: int = 3,
    backoff_seconds: float = 2.0,
) -> EntityDatabase | None:
    """Attempt DB initialization with retries.

    Returns EntityDatabase instance, or None if all retries failed.
    """
    for attempt in range(max_retries):
        try:
            return EntityDatabase(db_path)
        except sqlite3.OperationalError:
            if attempt < max_retries - 1:
                time.sleep(backoff_seconds)
    return None


def _start_recovery_thread(
    db_path: str,
    poll_interval: float = 30.0,
) -> threading.Thread:
    """Start daemon thread that retries DB initialization.

    On success: sets global _db, clears _db_unavailable.
    Thread exits after successful recovery.
    """
    global _db, _db_unavailable

    def _recover():
        global _db, _db_unavailable
        while True:
            time.sleep(poll_interval)
            try:
                new_db = EntityDatabase(db_path)
                _db = new_db
                _db_unavailable = False
                _logger.info(
                    "DB recovered — backfill skipped, will run on next restart"
                )
                return
            except sqlite3.OperationalError:
                continue

    thread = threading.Thread(target=_recover, name="db-recovery", daemon=True)
    thread.start()
    return thread


def _check_db_available():
    """Return error dict if DB is unavailable, else None."""
    if _db_unavailable:
        return {"error": "database temporarily unavailable"}
    return None


# ---------------------------------------------------------------------------
# Lifespan handler
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server):
    """Manage DB connection and backfill lifecycle."""
    global _db, _db_unavailable, _recovery_thread, _config, _project_root, _artifacts_root

    # Determine DB path (env override for testing, else global store).
    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/pd/entities/entities.db"),
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    write_pid("entity_server")
    start_parent_watchdog()

    _db = _init_db_with_retry(db_path)
    if _db is None:
        _db_unavailable = True
        _recovery_thread = _start_recovery_thread(db_path)
        print(
            "entity-server: started in DEGRADED mode (DB locked)",
            file=sys.stderr,
        )
    else:
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
        remove_pid("entity_server")
        if _db is not None:
            _db.close()
            _db = None
        _config = {}


# ---------------------------------------------------------------------------
# Ref resolution helper (Task 1b.5)
# ---------------------------------------------------------------------------


def _resolve_ref_param(
    db: EntityDatabase,
    type_id: str | None,
    ref: str | None,
    *,
    is_mutation: bool = False,
) -> str:
    """Resolve a type_id or ref parameter to a concrete type_id.

    Parameters
    ----------
    db:
        Open EntityDatabase.
    type_id:
        Explicit type_id (takes precedence if provided).
    ref:
        Flexible reference: UUID, full type_id, or type_id prefix.
    is_mutation:
        If True, ambiguous prefix matches always error (never guess).

    Returns
    -------
    str
        The resolved type_id.

    Raises
    ------
    ValueError
        If neither param provided, ref not found, or ambiguous.
    """
    if type_id is not None:
        return type_id
    if ref is None:
        raise ValueError("Either type_id or ref must be provided")

    # resolve_ref returns a UUID — look up the entity to get type_id
    entity_uuid = db.resolve_ref(ref)
    entity = db.get_entity_by_uuid(entity_uuid)
    if entity is None:
        raise ValueError(f"No entity found matching ref: {ref!r}")
    return entity["type_id"]


# ---------------------------------------------------------------------------
# Sync DB-logic helpers (Type B handlers — extracted for @with_retry)
# ---------------------------------------------------------------------------


@with_retry("entity")
def _process_update_entity(
    db: EntityDatabase,
    resolved_type_id: str,
    name: str | None,
    description: str | None,
    status: str | None,
    metadata: dict | None,
) -> str:
    """Update mutable fields of an existing entity (retryable)."""
    db.update_entity(
        resolved_type_id, name=name, status=status,
        artifact_path=description, metadata=metadata,
    )
    return f"Updated: {resolved_type_id}"


@with_retry("entity")
def _process_delete_entity(db: EntityDatabase, resolved_type_id: str) -> str:
    """Delete an entity and all associated data (retryable)."""
    db.delete_entity(resolved_type_id)
    return json.dumps({"result": f"Deleted: {resolved_type_id}"})


@with_retry("entity")
def _process_add_entity_tag(db: EntityDatabase, resolved_type_id: str, tag: str) -> str:
    """Add a tag to an entity (retryable)."""
    entity = db.get_entity(resolved_type_id)
    if entity is None:
        return f"Error: entity not found: {resolved_type_id}"
    db.add_tag(entity["uuid"], tag)
    return json.dumps({"result": f"Tagged {resolved_type_id} with '{tag}'"})


@with_retry("entity")
def _process_add_dependency(
    db: EntityDatabase,
    dep_mgr,
    blocker_uuid: str,
    blocked_uuid: str,
    entity_ref: str,
    blocked_by_ref: str,
) -> str:
    """Add a dependency between two entities (retryable)."""
    dep_mgr.add_dependency(db, blocker_uuid, blocked_uuid)
    return json.dumps({
        "result": f"Dependency added: {entity_ref} blocked by {blocked_by_ref}"
    })


@with_retry("entity")
def _process_remove_dependency(
    db: EntityDatabase,
    dep_mgr,
    entity_uuid: str,
    blocked_by_uuid: str,
    entity_ref: str,
    blocked_by_ref: str,
) -> str:
    """Remove a dependency between two entities (retryable)."""
    dep_mgr.remove_dependency(db, entity_uuid, blocked_by_uuid)
    return json.dumps({
        "result": f"Dependency removed: {entity_ref} no longer blocked by {blocked_by_ref}"
    })


@with_retry("entity")
def _process_add_okr_alignment(
    db: EntityDatabase, entity_uuid: str, kr_uuid: str,
    entity_ref: str, kr_ref: str,
) -> str:
    """Link an entity to a key result (retryable)."""
    db.add_okr_alignment(entity_uuid, kr_uuid)
    return json.dumps({"result": f"Aligned {entity_ref} to {kr_ref}"})


@with_retry("entity")
def _process_create_key_result(
    db: EntityDatabase,
    parent_type_id: str,
    eid: str,
    name: str,
    status: str | None,
    metadata_json: str,
    weight: float,
) -> str:
    """Register a key_result entity with parent linkage (retryable)."""
    uuid = db.register_entity(
        entity_type="key_result",
        entity_id=eid,
        name=name,
        status=status,
        parent_type_id=parent_type_id,
        metadata=metadata_json,
    )
    return json.dumps({"uuid": uuid, "type_id": f"key_result:{eid}", "weight": weight})


@with_retry("entity")
def _process_update_kr_score(
    db: EntityDatabase, resolved_type_id: str, score: float,
) -> str:
    """Update score for a key_result entity (retryable)."""
    db.update_entity(resolved_type_id, metadata={"score": float(score)})
    return json.dumps({"result": f"Score updated to {score}", "type_id": resolved_type_id})


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
    metadata: str | dict | None = None,
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
        Optional metadata — pass a dict (preferred) or a JSON string;
        dicts are auto-coerced to JSON.

    Returns confirmation message or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    if isinstance(metadata, dict):
        metadata = json.dumps(metadata)

    return _process_register_entity(
        _db, entity_type, entity_id, name,
        artifact_path, status, parent_type_id,
        parse_metadata(metadata),
    )


@mcp.tool()
async def set_parent(
    type_id: str | None = None,
    parent_type_id: str | None = None,
    ref: str | None = None,
    parent_ref: str | None = None,
) -> str:
    """Set or change the parent of an entity.

    Parameters
    ----------
    type_id:
        The entity to update (e.g. 'feature:029-entity-lineage-tracking').
    parent_type_id:
        The new parent entity (e.g. 'project:my-project').
    ref:
        Alternative flexible reference for the child entity.
    parent_ref:
        Alternative flexible reference for the parent entity.

    Returns confirmation message or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref, is_mutation=True)
        resolved_parent = _resolve_ref_param(
            _db, parent_type_id, parent_ref, is_mutation=True
        )
    except ValueError as exc:
        return f"Error: {exc}"

    return _process_set_parent(_db, resolved_type_id, resolved_parent)


@mcp.tool()
async def get_entity(type_id: str | None = None, ref: str | None = None) -> str:
    """Retrieve a single entity by type_id or ref.

    Parameters
    ----------
    type_id:
        Entity identifier (e.g. 'feature:029-entity-lineage-tracking').
    ref:
        Alternative flexible reference: UUID, full type_id, or type_id prefix.
        Resolved via db.resolve_ref(). Provide type_id OR ref (not both required).

    Returns JSON representation of the entity or not-found message.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    entity = _db.get_entity(resolved_type_id)
    if entity is None:
        return f"Entity not found: {resolved_type_id}"
    for key in ("uuid", "entity_id", "parent_uuid"):
        entity.pop(key, None)
    return json.dumps(entity, separators=(",", ":"))


@mcp.tool()
async def get_lineage(
    type_id: str | None = None,
    direction: str = "up",
    max_depth: int = 10,
    ref: str | None = None,
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
    ref:
        Alternative flexible reference for the starting entity.

    Returns formatted tree string or error message.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref)
    except ValueError as exc:
        return f"Error: {exc}"

    return _process_get_lineage(_db, resolved_type_id, direction, max_depth)


@mcp.tool()
async def update_entity(
    type_id: str | None = None,
    name: str | None = None,
    status: str | None = None,
    artifact_path: str | None = None,
    metadata: str | dict | None = None,
    ref: str | None = None,
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
        Metadata to shallow-merge — pass a dict (preferred) or a JSON
        string; dicts are auto-coerced. Empty dict '{}' clears.
    ref:
        Alternative flexible reference. Mutations require exact or unique match.

    Returns confirmation message or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref, is_mutation=True)
    except ValueError as exc:
        return f"Error: {exc}"

    if isinstance(metadata, dict):
        metadata = json.dumps(metadata)

    try:
        return _process_update_entity(
            _db, resolved_type_id, name=name, description=artifact_path,
            status=status, metadata=parse_metadata(metadata),
        )
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
    err = _check_db_available()
    if err:
        return json.dumps(err)
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
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    return _process_export_entities(
        _db, entity_type, status, output_path, include_lineage, _artifacts_root,
        fields=fields,
    )


@mcp.tool()
async def delete_entity(type_id: str | None = None, ref: str | None = None) -> str:
    """Delete an entity and all associated data (FTS, workflow_phases).

    Parameters
    ----------
    type_id:
        Entity to delete (e.g. 'feature:001-test').
    ref:
        Alternative flexible reference. Mutations require exact or unique match.

    Returns confirmation JSON or error JSON.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref, is_mutation=True)
        return _process_delete_entity(_db, resolved_type_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def add_entity_tag(
    type_id: str | None = None, tag: str = "", ref: str | None = None
) -> str:
    """Add a tag to an entity.

    Parameters
    ----------
    type_id:
        Entity identifier (type_id).
    tag:
        Tag string (lowercase, hyphens, max 50 chars).
    ref:
        Alternative flexible reference for the entity.

    Returns confirmation or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref, is_mutation=True)
        return _process_add_entity_tag(_db, resolved_type_id, tag)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": f"Unexpected error: {exc}"})


@mcp.tool()
async def get_entity_tags(type_id: str | None = None, ref: str | None = None) -> str:
    """Get all tags for an entity.

    Parameters
    ----------
    type_id:
        Entity identifier (type_id).
    ref:
        Alternative flexible reference for the entity.

    Returns JSON list of tags or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref)
        entity = _db.get_entity(resolved_type_id)
        if entity is None:
            return f"Error: entity not found: {resolved_type_id}"
        tags = _db.get_tags(entity["uuid"])
        return json.dumps({"type_id": resolved_type_id, "tags": tags})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": f"Unexpected error: {exc}"})


@mcp.tool()
async def add_dependency(
    entity_ref: str,
    blocked_by_ref: str,
) -> str:
    """Add a dependency: entity is blocked by another entity.

    Parameters
    ----------
    entity_ref:
        The entity that is blocked (type_id, UUID, or prefix).
    blocked_by_ref:
        The entity that blocks it (type_id, UUID, or prefix).

    Returns confirmation JSON or error JSON.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        from entity_registry.dependencies import CycleError, DependencyManager

        entity_uuid = _db.resolve_ref(entity_ref)
        blocked_by_uuid = _db.resolve_ref(blocked_by_ref)
        mgr = DependencyManager()
        return _process_add_dependency(
            _db, mgr, entity_uuid, blocked_by_uuid, entity_ref, blocked_by_ref,
        )
    except CycleError as exc:
        return json.dumps({"error": f"Cycle detected: {exc}"})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": f"Unexpected error: {exc}"})


@mcp.tool()
async def remove_dependency(
    entity_ref: str,
    blocked_by_ref: str,
) -> str:
    """Remove a dependency between two entities.

    Parameters
    ----------
    entity_ref:
        The entity that was blocked (type_id, UUID, or prefix).
    blocked_by_ref:
        The entity that was blocking it (type_id, UUID, or prefix).

    Returns confirmation JSON or error JSON.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        from entity_registry.dependencies import DependencyManager

        entity_uuid = _db.resolve_ref(entity_ref)
        blocked_by_uuid = _db.resolve_ref(blocked_by_ref)
        mgr = DependencyManager()
        return _process_remove_dependency(
            _db, mgr, entity_uuid, blocked_by_uuid, entity_ref, blocked_by_ref,
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": f"Unexpected error: {exc}"})


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
    err = _check_db_available()
    if err:
        return json.dumps(err)
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
# OKR alignment tools (Task 6.5, AC-37 — lateral cross-linkage)
# ---------------------------------------------------------------------------


@mcp.tool()
async def add_okr_alignment(entity_ref: str, kr_ref: str) -> str:
    """Link an entity to a key result for lateral OKR alignment.

    Parameters
    ----------
    entity_ref:
        The entity to align (type_id, UUID, or prefix).
    kr_ref:
        The key_result to align with (type_id, UUID, or prefix).
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        entity_uuid = _db.resolve_ref(entity_ref)
        kr_uuid = _db.resolve_ref(kr_ref)
        return _process_add_okr_alignment(_db, entity_uuid, kr_uuid, entity_ref, kr_ref)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def get_okr_alignments(entity_ref: str) -> str:
    """Get all key results aligned to an entity.

    Parameters
    ----------
    entity_ref:
        The entity to query (type_id, UUID, or prefix).
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        entity_uuid = _db.resolve_ref(entity_ref)
        alignments = _db.get_okr_alignments(entity_uuid)
        results = [{"type_id": a["type_id"], "name": a["name"], "status": a.get("status")} for a in alignments]
        return json.dumps({"entity_ref": entity_ref, "alignments": results, "count": len(results)})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# OKR helpers — thin wrappers over rollup.py (Step 5.2, AC-32)
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_key_result(
    parent_ref: str,
    name: str,
    metric_type: str,
    weight: float = 1.0,
    entity_id: str | None = None,
    status: str | None = None,
) -> str:
    """Register a key_result entity with parent linkage, metric_type, and weight.

    Parameters
    ----------
    parent_ref:
        Reference (type_id, UUID, or prefix) to the parent objective.
    name:
        Human-readable KR name.
    metric_type:
        One of: milestone, binary, baseline_target.
    weight:
        Relative weight for weighted scoring (default 1.0).
    entity_id:
        Optional explicit ID; auto-generated if omitted.
    status:
        Optional initial status.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    _VALID_METRIC_TYPES = ("milestone", "binary", "baseline_target", "target", "baseline")
    if metric_type not in _VALID_METRIC_TYPES:
        return json.dumps({"error": f"Invalid metric_type: {metric_type}. Must be one of: {', '.join(_VALID_METRIC_TYPES)}"})
    try:
        parent_type_id = _resolve_ref_param(_db, None, parent_ref, is_mutation=True)
        eid = entity_id or name.lower().replace(" ", "-")[:30]
        metadata_json = json.dumps({"metric_type": metric_type, "weight": weight})
        return _process_create_key_result(
            _db, parent_type_id, eid, name, status, metadata_json, weight,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def update_kr_score(
    kr_ref: str,
    score: float,
) -> str:
    """Manually update score for a baseline_target (or binary-no-children) KR.

    Parameters
    ----------
    kr_ref:
        Reference to the key_result entity.
    score:
        New score value (0.0-1.0).
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    if not (0.0 <= score <= 1.0):
        return json.dumps({"error": f"Score must be between 0.0 and 1.0, got {score}"})
    try:
        resolved = _resolve_ref_param(_db, None, kr_ref, is_mutation=True)
        return _process_update_kr_score(_db, resolved, score)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
