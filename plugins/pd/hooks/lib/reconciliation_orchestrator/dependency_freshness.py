"""Stale dependency cleanup for reconciliation orchestrator.

Scans blocked-downstream entities directly (feature 124 SC5's efficient
shape) rather than re-scanning every historical completed-blocker edge on
each run, then flips any whose blockers all satisfy the per-kind
completion predicate (D4) via DependencyManager._evaluate_and_flip. Edges
in entity_relations(kind='blocks') SURVIVE (FR124-4c) -- this is a
missed-cascade safety net, not an edge-tombstone sweep.

Scoped to the session's workspace (design W1.8): a session start never flips
another workspace's blocked entities.
"""
from __future__ import annotations

from entity_registry.dependencies import DependencyManager


def cleanup_stale_dependencies(db, workspace_uuid: str | None) -> int:
    """Flip blocked entities whose blockers are all resolved but missed cascade.

    Only *workspace_uuid*'s blocked entities are candidates. With no
    workspace the cleanup is skipped (returns 0): unscoped, it would flip
    every workspace's entities.

    Returns count of entities flipped blocked -> ready.

    Uses public API only (no db._conn):
    1. list_entities(workspace_uuid=...) to find this workspace's
       blocked-downstream candidates
    2. _evaluate_and_flip() flips any candidate whose blockers are all
       resolved (D4) -- a no-op fetch-only pass for the rest
    """
    if not workspace_uuid:
        return 0
    workspace_entities = db.list_entities(workspace_uuid=workspace_uuid)
    blocked_uuids = [
        e["uuid"] for e in (workspace_entities or [])
        if e.get("status") == "blocked"
    ]
    dep_mgr = DependencyManager()
    flipped = dep_mgr._evaluate_and_flip(db, blocked_uuids)
    return len(flipped)
