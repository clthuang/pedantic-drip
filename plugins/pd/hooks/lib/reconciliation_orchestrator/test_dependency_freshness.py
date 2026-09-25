"""Tests for reconciliation_orchestrator.dependency_freshness module."""
from __future__ import annotations

import pytest

from entity_registry.database import EntityDatabase, _UNKNOWN_WORKSPACE_UUID
from reconciliation_orchestrator.dependency_freshness import cleanup_stale_dependencies


class TestCleanupStaleDependencies:
    """cleanup_stale_dependencies removes stale edges and returns count."""

    def test_stale_edge_cleaned(self, tmp_path):
        """Create stale edge, run cleanup, assert returns 1 and edge removed."""
        db_path = str(tmp_path / "entities.db")
        db = EntityDatabase(db_path)

        uuid_blocked = db.register_entity(
            "feature", name="Blocked Entity", seq=1, slug="fresh-blocked",
            status="blocked", workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        uuid_blocker = db.register_entity(
            "feature", name="Completed Blocker", seq=1, slug="fresh-blocker",
            status="active", workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.add_dependency(uuid_blocked, uuid_blocker)

        # Complete blocker directly (bypass update_entity cascade to simulate
        # a pre-existing stale edge that wasn't cleaned by Layer 1)
        db._conn.execute(
            "UPDATE entities SET status = 'completed' WHERE uuid = ?",
            (uuid_blocker,),
        )
        db._conn.commit()

        # Run cleanup, scoped to the workspace holding both entities (W1.8)
        count = cleanup_stale_dependencies(db, _UNKNOWN_WORKSPACE_UUID)

        # 1 entity flipped (the reworked blocked-downstream scan still
        # returns a flip-count here — one blocked entity, one flip).
        assert count == 1

        # Feature 124 FR124-4c: edge SURVIVES (no longer removed)
        deps = db.query_dependencies(entity_uuid=uuid_blocked)
        assert len(deps) == 1

        # Feature 124 FR124-4a: blocked entity should be promoted to ready
        entity = db.get_entity_by_uuid(uuid_blocked)
        assert entity["status"] == "ready"

        db.close()
