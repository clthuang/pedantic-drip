"""Helper functions for the MCP entity server layer.

These wrap EntityDatabase calls with formatting, error handling,
and output suitable for MCP tool responses.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict


def render_tree(
    entities: list[dict], root_type_id: str, max_depth: int = 50
) -> str:
    """Render a flat list of entity dicts as a Unicode box-drawing tree.

    Parameters
    ----------
    entities:
        Flat list of entity dicts. Each must have keys: uuid, type_id, name,
        entity_type, status, parent_uuid, created_at.
    root_type_id:
        The UUID of the root node for this tree. Parameter name retained
        for API compatibility per spec R33, despite now accepting UUID values.
    max_depth:
        Maximum tree depth to render (default 50).

    Returns
    -------
    str
        Formatted tree string with Unicode box-drawing characters.
        Empty string if entities is empty or root_type_id not found.
    """
    if not entities:
        return ""

    # Build lookup map keyed by UUID (first pass)
    by_id: dict[str, dict] = {}
    for entity in entities:
        uid = entity["uuid"]
        by_id[uid] = entity

    # Build children map from parent_uuid (second pass — all entities
    # already in by_id, so ordering within the flat list doesn't matter)
    children: dict[str, list[str]] = defaultdict(list)
    for entity in entities:
        uid = entity["uuid"]
        parent = entity.get("parent_uuid")
        if parent is not None and parent in by_id:
            children[parent].append(uid)

    if root_type_id not in by_id:
        return ""

    lines: list[str] = []
    _render_node(by_id, children, root_type_id, "", True, True, lines, 0, max_depth)
    return "\n".join(lines)


def _format_entity_label(entity: dict) -> str:
    """Format a single entity as: type_id -- "name" (status, date) [depends on: ...].

    When the entity's ``metadata`` JSON contains a non-empty
    ``depends_on_features`` list, a ``[depends on: feature:xxx, ...]``
    annotation is appended (AC-5 / design I7).
    """
    date_part = entity["created_at"][:10]
    status = entity.get("status")
    if status:
        paren = f"({status}, {date_part})"
    else:
        paren = f"({date_part})"

    label = f'{entity["type_id"]} \u2014 "{entity["name"]}" {paren}'

    # AC-5: append depends_on_features annotation when present
    metadata_str = entity.get("metadata")
    if metadata_str:
        try:
            meta = json.loads(metadata_str)
            deps = meta.get("depends_on_features")
            if isinstance(deps, list) and deps:
                dep_refs = ", ".join(f"feature:{d}" for d in deps)
                label += f" [depends on: {dep_refs}]"
        except (json.JSONDecodeError, ValueError, TypeError):
            pass  # malformed metadata -- skip annotation gracefully

    return label


def _render_node(
    by_id: dict[str, dict],
    children: dict[str, list[str]],
    node_id: str,
    prefix: str,
    is_last: bool,
    is_root: bool,
    lines: list[str],
    depth: int = 0,
    max_depth: int = 50,
) -> None:
    """Recursively render a node and its children.

    Parameters
    ----------
    depth:
        Current depth in the tree (0 for root).
    max_depth:
        Maximum depth to render. When exceeded, a truncation indicator
        is appended instead of recursing further.
    """
    entity = by_id[node_id]
    label = _format_entity_label(entity)

    if is_root:
        lines.append(label)
        child_prefix = "  "
    else:
        connector = "\u2514\u2500" if is_last else "\u251c\u2500"
        lines.append(f"{prefix}{connector} {label}")
        # For children of this node, continuation indent depends on
        # whether this node was last among its siblings.
        child_prefix = prefix + ("   " if is_last else "\u2502  ")

    kids = children.get(node_id, [])
    if kids and depth >= max_depth:
        lines.append(f"{child_prefix}\u2514\u2500 ... (depth limit reached)")
        return

    for i, kid_id in enumerate(kids):
        kid_is_last = (i == len(kids) - 1)
        _render_node(
            by_id, children, kid_id, child_prefix, kid_is_last, False, lines,
            depth + 1, max_depth,
        )


def parse_metadata(metadata_str: str | None) -> dict | None:
    """Parse a JSON metadata string into a dict.

    Parameters
    ----------
    metadata_str:
        JSON string to parse, or None.

    Returns
    -------
    dict | None
        Parsed dict on success, None if input is None,
        or ``{"error": "<message>"}`` if JSON is invalid.
    """
    if metadata_str is None:
        return None
    try:
        return json.loads(metadata_str)
    except (json.JSONDecodeError, ValueError) as exc:
        return {"error": f"Invalid JSON: {exc}"}


def resolve_output_path(
    output_path: str | None, artifacts_root: str
) -> str | None:
    """Resolve an output path against an artifacts root directory.

    Parameters
    ----------
    output_path:
        Path to resolve. Relative paths are joined with artifacts_root.
        If None, returns None.
    artifacts_root:
        Base directory for relative path resolution. The resolved path
        must remain within this directory (path containment check).

    Returns
    -------
    str | None
        Resolved absolute path, or None if output_path is None or if
        the resolved path escapes artifacts_root.
    """
    if output_path is None:
        return None
    if os.path.isabs(output_path):
        resolved = os.path.realpath(output_path)
    else:
        resolved = os.path.realpath(os.path.join(artifacts_root, output_path))
    # Path containment: ensure resolved path stays within artifacts_root
    real_root = os.path.realpath(artifacts_root)
    if not (resolved.startswith(real_root + os.sep) or resolved == real_root):
        return None
    return resolved


def _process_register_entity(
    db,
    entity_type: str,
    entity_id: str,
    name: str,
    artifact_path: str | None,
    status: str | None,
    parent_type_id: str | None,
    metadata: dict | None,
) -> str:
    """Register an entity via EntityDatabase with error handling.

    Parameters
    ----------
    db:
        An EntityDatabase instance.
    entity_type:
        One of: backlog, brainstorm, project, feature.
    entity_id:
        Unique identifier within the entity_type namespace.
    name:
        Human-readable name.
    artifact_path:
        Optional filesystem path to the entity's artifact.
    status:
        Optional status string.
    parent_type_id:
        Optional type_id of the parent entity.
    metadata:
        Optional dict stored as JSON.

    Returns
    -------
    str
        Success message containing the type_id, or error message.
        Never raises exceptions.
    """
    try:
        db.register_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            name=name,
            artifact_path=artifact_path,
            status=status,
            parent_type_id=parent_type_id,
            metadata=metadata,
        )
        type_id = f"{entity_type}:{entity_id}"
        return f"Registered: {type_id}"
    except Exception as exc:
        return f"Error registering entity: {exc}"


def _process_export_lineage_markdown(
    db,
    type_id: str | None,
    output_path: str | None,
    artifacts_root: str,
) -> str:
    """Export entity lineage as markdown, optionally writing to a file.

    Parameters
    ----------
    db:
        An EntityDatabase instance.
    type_id:
        If provided, export only the tree rooted at this entity.
        If None, export all trees.
    output_path:
        If provided, write markdown to this file path (relative paths
        resolved against artifacts_root). Returns confirmation.
        If None, returns the markdown string directly.
    artifacts_root:
        Base directory for relative path resolution.

    Returns
    -------
    str
        Markdown string or file-write confirmation.
        Never raises exceptions.
    """
    try:
        md = db.export_lineage_markdown(type_id)
        resolved = resolve_output_path(output_path, artifacts_root)
        if resolved is not None:
            parent_dir = os.path.dirname(resolved)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(resolved, "w") as f:
                f.write(md)
            return f"Exported lineage to {resolved}"
        if output_path is not None and resolved is None:
            return f"Error exporting lineage: path escapes artifacts root"
        return md
    except Exception as exc:
        return f"Error exporting lineage: {exc}"


def _process_export_entities(
    db,
    entity_type: str | None,
    status: str | None,
    output_path: str | None,
    include_lineage: bool,
    artifacts_root: str,
    fields: str | None = None,
) -> str:
    """Export entities as JSON, optionally writing to a file.

    Parameters
    ----------
    db : EntityDatabase
        Active database instance.
    entity_type : str or None
        Filter by entity type (backlog/brainstorm/project/feature).
    status : str or None
        Filter by status value.
    output_path : str or None
        File path to write JSON to. None returns JSON string directly.
    include_lineage : bool
        Include parent_type_id in entity dicts.
    artifacts_root : str
        Root directory for path containment check.
    fields : str or None
        Comma-separated field names to include per entity (projection).
        None returns all fields (backward compatible).

    Returns
    -------
    str
        JSON string, file-write confirmation, or error message.
        Never raises exceptions.
    """
    try:
        data = db.export_entities_json(entity_type, status, include_lineage)
    except ValueError as exc:
        return f"Error: {exc}"

    if fields is not None:
        field_set = {f.strip() for f in fields.split(",")}
        entities = data["entities"]
        # Validate: if entities exist and ALL requested fields are invalid, return error
        if entities:
            valid_fields = set(entities[0].keys())
            if not field_set & valid_fields:
                return f"Error: no valid fields in '{fields}'. Valid fields: {', '.join(sorted(valid_fields))}"
        data["entities"] = [
            {k: v for k, v in entity.items() if k in field_set}
            for entity in entities
        ]

    if output_path is not None:
        resolved = resolve_output_path(output_path, artifacts_root)
        if resolved is None:
            return "Error: output path escapes artifacts root"
        try:
            parent_dir = os.path.dirname(resolved)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(resolved, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return f"Exported {data['entity_count']} entities to {resolved}"
        except OSError as exc:
            return f"Error writing export: {exc}"

    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def _process_get_lineage(
    db,
    type_id: str,
    direction: str,
    max_depth: int,
) -> str:
    """Get entity lineage via EntityDatabase with tree rendering.

    Parameters
    ----------
    db:
        An EntityDatabase instance.
    type_id:
        Starting entity for lineage traversal.
    direction:
        ``"up"`` walks toward root, ``"down"`` walks toward leaves.
    max_depth:
        Maximum levels to traverse.

    Returns
    -------
    str
        Formatted tree string, or error/not-found message.
        Never raises exceptions.
    """
    try:
        entities = db.get_lineage(type_id, direction=direction, max_depth=max_depth)
        if not entities:
            return f"Entity not found: {type_id}"

        # Determine the root of the rendered tree.
        # For "up" direction, lineage is root-first, so root is first element.
        # For "down" direction, the starting entity is the root.
        root_type_id = entities[0]["uuid"]

        return render_tree(entities, root_type_id)
    except Exception as exc:
        return f"Error retrieving lineage: {exc}"


def _process_set_parent(db, type_id: str, parent_type_id: str) -> str:
    """Set or change the parent of an entity.

    Parameters
    ----------
    db:
        An EntityDatabase instance.
    type_id:
        The entity to update (e.g. ``'feature:029-entity-lineage-tracking'``).
    parent_type_id:
        The new parent entity (e.g. ``'project:my-project'``).

    Returns
    -------
    str
        Confirmation message, or error message.  Never raises exceptions.
    """
    try:
        db.set_parent(type_id, parent_type_id)
        return f"Parent set: {type_id} → {parent_type_id}"
    except Exception as exc:
        return f"Error setting parent: {exc}"
