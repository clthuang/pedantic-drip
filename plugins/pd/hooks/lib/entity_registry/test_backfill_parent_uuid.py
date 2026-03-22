"""Tests for backfill.py uuid-primary parent resolution (Task 1b.7a).

Verifies that parent linkage in backfill_workflow_phases prefers parent_uuid
and falls back to parent_type_id for legacy entities.
"""
from __future__ import annotations

import json
import os

import pytest

from entity_registry.backfill import backfill_workflow_phases
from entity_registry.database import EntityDatabase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_and_root(tmp_path):
    """DB with parent-child entities and a minimal artifact tree."""
    db = EntityDatabase(str(tmp_path / "test.db"))
    artifacts_root = str(tmp_path)

    # Create features dir
    feat_dir = tmp_path / "features"
    feat_dir.mkdir()

    yield db, artifacts_root
    db.close()


# ---------------------------------------------------------------------------
# Test: parent_uuid preferred for child lookup
# ---------------------------------------------------------------------------


class TestParentUuidPreference:
    def test_child_lookup_uses_parent_uuid(self, db_and_root):
        """When parent_uuid is set, child completion check uses it."""
        db, artifacts_root = db_and_root

        # Register brainstorm with a child feature
        bs_uuid = db.register_entity("brainstorm", "test-bs", "Test Brainstorm")
        feat_uuid = db.register_entity(
            "feature", "001-child", "Child Feature",
            parent_type_id="brainstorm:test-bs",
        )

        # Verify parent_uuid was set
        child = db.get_entity("feature:001-child")
        assert child["parent_uuid"] == bs_uuid

        # Mark child as completed
        db.update_entity("feature:001-child", status="completed")

        # Create feature dir with .meta.json for the child
        feat_child_dir = os.path.join(artifacts_root, "features", "001-child")
        os.makedirs(feat_child_dir, exist_ok=True)
        meta = {
            "id": "001",
            "slug": "child",
            "status": "completed",
            "lastCompletedPhase": "finish",
        }
        with open(os.path.join(feat_child_dir, ".meta.json"), "w") as f:
            json.dump(meta, f)

        # Run backfill_workflow_phases
        result = backfill_workflow_phases(db, artifacts_root)

        # Brainstorm should get a workflow_phases row
        # The child completion detection should have worked
        assert result["errors"] == []

    def test_legacy_parent_type_id_fallback(self, db_and_root):
        """When parent_uuid is NULL but parent_type_id is set, fallback works."""
        db, artifacts_root = db_and_root

        # Register brainstorm
        bs_uuid = db.register_entity("brainstorm", "legacy-bs", "Legacy BS")

        # Register child feature
        feat_uuid = db.register_entity(
            "feature", "002-legacy", "Legacy Child",
            parent_type_id="brainstorm:legacy-bs",
        )

        # Manually clear parent_uuid to simulate legacy data
        db._conn.execute(
            "UPDATE entities SET parent_uuid = NULL WHERE uuid = ?",
            (feat_uuid,),
        )
        db._conn.commit()

        # Verify parent_uuid is NULL but parent_type_id is set
        child = db.get_entity("feature:002-legacy")
        assert child["parent_uuid"] is None
        assert child["parent_type_id"] == "brainstorm:legacy-bs"

        # Mark child as completed
        db.update_entity("feature:002-legacy", status="completed")

        # Create .meta.json
        feat_dir = os.path.join(artifacts_root, "features", "002-legacy")
        os.makedirs(feat_dir, exist_ok=True)
        meta = {
            "id": "002",
            "slug": "legacy",
            "status": "completed",
            "lastCompletedPhase": "finish",
        }
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump(meta, f)

        result = backfill_workflow_phases(db, artifacts_root)
        assert result["errors"] == []

    def test_parent_uuid_resolves_children_correctly(self, db_and_root):
        """Parent with uuid-linked children: all completed -> kanban=completed."""
        db, artifacts_root = db_and_root

        # Register brainstorm parent
        bs_uuid = db.register_entity("brainstorm", "parent-bs", "Parent BS")

        # Register two child features with parent_uuid
        for i in range(1, 3):
            db.register_entity(
                "feature", f"00{i}-c", f"Child {i}",
                parent_type_id="brainstorm:parent-bs",
            )
            db.update_entity(f"feature:00{i}-c", status="completed")

            feat_dir = os.path.join(artifacts_root, "features", f"00{i}-c")
            os.makedirs(feat_dir, exist_ok=True)
            meta = {
                "id": f"00{i}",
                "slug": "c",
                "status": "completed",
                "lastCompletedPhase": "finish",
            }
            with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
                json.dump(meta, f)

        result = backfill_workflow_phases(db, artifacts_root)
        assert result["errors"] == []

        # Check brainstorm got completed kanban due to all children complete
        wp = db.get_workflow_phase("brainstorm:parent-bs")
        assert wp is not None
        assert wp["kanban_column"] == "completed"

    def test_mixed_parent_uuid_and_type_id_children(self, db_and_root):
        """Some children have parent_uuid, some only parent_type_id."""
        db, artifacts_root = db_and_root

        bs_uuid = db.register_entity("brainstorm", "mix-bs", "Mixed BS")

        # Child 1: has parent_uuid (normal)
        feat1_uuid = db.register_entity(
            "feature", "001-mix", "Mix Child 1",
            parent_type_id="brainstorm:mix-bs",
        )
        db.update_entity("feature:001-mix", status="completed")

        # Child 2: parent_uuid cleared (legacy)
        feat2_uuid = db.register_entity(
            "feature", "002-mix", "Mix Child 2",
            parent_type_id="brainstorm:mix-bs",
        )
        db._conn.execute(
            "UPDATE entities SET parent_uuid = NULL WHERE uuid = ?",
            (feat2_uuid,),
        )
        db._conn.commit()
        db.update_entity("feature:002-mix", status="completed")

        # Create .meta.json files
        for eid in ["001-mix", "002-mix"]:
            feat_dir = os.path.join(artifacts_root, "features", eid)
            os.makedirs(feat_dir, exist_ok=True)
            meta = {"id": eid[:3], "slug": eid[4:], "status": "completed", "lastCompletedPhase": "finish"}
            with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
                json.dump(meta, f)

        result = backfill_workflow_phases(db, artifacts_root)
        assert result["errors"] == []

        # Both children should be found (via uuid or type_id fallback)
        wp = db.get_workflow_phase("brainstorm:mix-bs")
        assert wp is not None
        assert wp["kanban_column"] == "completed"
