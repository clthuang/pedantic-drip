"""Stale dependency cleanup for reconciliation orchestrator.

Scans entity_dependencies for edges where the blocker is completed,
then runs cascade_unblock to remove stale edges and promote dependents.
"""
from __future__ import annotations

from entity_registry.dependencies import DependencyManager


def cleanup_stale_dependencies(db) -> int:
    """Remove stale blocked_by edges and promote unblocked dependents.

    Returns count of unique completed blocker UUIDs processed.

    Uses public API only (no db._conn):
    1. query_dependencies() to get all edges
    2. get_entity_by_uuid() to check each blocker's status
    3. cascade_unblock() for completed blockers
    """
    all_edges = db.query_dependencies()
    stale_blockers: set[str] = set()
    for edge in all_edges or []:
        blocker = db.get_entity_by_uuid(edge["blocked_by_uuid"])
        if blocker and blocker.get("status") == "completed":
            stale_blockers.add(edge["blocked_by_uuid"])
    dep_mgr = DependencyManager()
    for uuid in stale_blockers:
        dep_mgr.cascade_unblock(db, uuid)
    return len(stale_blockers)
