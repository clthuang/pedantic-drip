"""Tests for reconciliation_orchestrator.dependency_freshness module."""
from __future__ import annotations

import pytest

from entity_registry.database import EntityDatabase
from reconciliation_orchestrator.dependency_freshness import cleanup_stale_dependencies


class TestCleanupStaleDependencies:
    """cleanup_stale_dependencies removes stale edges and returns count."""

    def test_stale_edge_cleaned(self, tmp_path):
        """Create stale edge, run cleanup, assert returns 1 and edge removed."""
        db_path = str(tmp_path / "entities.db")
        db = EntityDatabase(db_path)

        uuid_blocked = db.register_entity(
            "feature", "fresh-blocked", "Blocked Entity",
            status="blocked", project_id="__unknown__",
        )
        uuid_blocker = db.register_entity(
            "feature", "fresh-blocker", "Completed Blocker",
            status="active", project_id="__unknown__",
        )
        db.add_dependency(uuid_blocked, uuid_blocker)

        # Complete blocker directly (bypass update_entity cascade to simulate
        # a pre-existing stale edge that wasn't cleaned by Layer 1)
        db._conn.execute(
            "UPDATE entities SET status = 'completed' WHERE uuid = ?",
            (uuid_blocker,),
        )
        db._conn.commit()

        # Run cleanup
        count = cleanup_stale_dependencies(db)

        assert count == 1

        # Edge should be removed
        deps = db.query_dependencies(entity_uuid=uuid_blocked)
        assert len(deps) == 0

        # Blocked entity should be promoted to planned
        entity = db.get_entity_by_uuid(uuid_blocked)
        assert entity["status"] == "planned"

        db.close()
