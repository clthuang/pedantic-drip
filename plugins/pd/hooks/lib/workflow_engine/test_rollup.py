"""Tests for the progress rollup engine (rollup.py).

Covers:
- PHASE_WEIGHTS_7 and PHASE_WEIGHTS_5D constants
- compute_progress() with various child states
- rollup_parent() ancestor chain traversal
- Edge cases: no children, all abandoned, no parent, max depth
"""
from __future__ import annotations

import json
import pytest

from entity_registry.database import EntityDatabase
from workflow_engine.rollup import (
    PHASE_WEIGHTS_5D,
    PHASE_WEIGHTS_7,
    _MAX_DEPTH,
    compute_progress,
    rollup_parent,
)


@pytest.fixture
def db():
    """In-memory EntityDatabase for testing."""
    d = EntityDatabase(":memory:")
    yield d
    d.close()


def _register(db, entity_type, entity_id, name, *, status=None,
              parent_type_id=None, metadata=None):
    """Register entity and return its uuid."""
    return db.register_entity(
        entity_type=entity_type,
        entity_id=entity_id,
        name=name,
        status=status,
        parent_type_id=parent_type_id,
        metadata=metadata,
    )


def _with_phase(db, type_id, phase, *, mode="standard"):
    """Create a workflow_phases row for an entity."""
    db.create_workflow_phase(
        type_id,
        workflow_phase=phase,
        mode=mode,
    )


# -----------------------------------------------------------------------
# PHASE_WEIGHTS constants
# -----------------------------------------------------------------------

class TestPhaseWeightsConstants:
    """Verify the weight constants are correct."""

    def test_phase_weights_7_keys(self):
        expected = {
            "brainstorm", "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        }
        assert set(PHASE_WEIGHTS_7.keys()) == expected

    def test_phase_weights_7_values(self):
        assert PHASE_WEIGHTS_7["brainstorm"] == 0.0
        assert PHASE_WEIGHTS_7["specify"] == 0.1
        assert PHASE_WEIGHTS_7["design"] == 0.3
        assert PHASE_WEIGHTS_7["implement"] == 0.7
        assert PHASE_WEIGHTS_7["finish"] == 0.9

    def test_phase_weights_7_monotonic(self):
        """Progress values should be non-decreasing through the lifecycle."""
        phases = ["brainstorm", "specify", "design", "create-plan",
                  "create-tasks", "implement", "finish"]
        values = [PHASE_WEIGHTS_7[p] for p in phases]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1], (
                f"{phases[i]} ({values[i]}) < {phases[i-1]} ({values[i-1]})"
            )

    def test_phase_weights_5d_keys(self):
        expected = {"discover", "define", "design", "deliver", "debrief"}
        assert set(PHASE_WEIGHTS_5D.keys()) == expected

    def test_phase_weights_5d_values(self):
        assert PHASE_WEIGHTS_5D["discover"] == 0.0
        assert PHASE_WEIGHTS_5D["define"] == 0.1
        assert PHASE_WEIGHTS_5D["design"] == 0.3
        assert PHASE_WEIGHTS_5D["deliver"] == 0.7
        assert PHASE_WEIGHTS_5D["debrief"] == 0.9

    def test_phase_weights_5d_monotonic(self):
        phases = ["discover", "define", "design", "deliver", "debrief"]
        values = [PHASE_WEIGHTS_5D[p] for p in phases]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_all_weights_between_0_and_1(self):
        for name, w in {**PHASE_WEIGHTS_7, **PHASE_WEIGHTS_5D}.items():
            assert 0.0 <= w <= 1.0, f"{name} weight {w} out of range"


# -----------------------------------------------------------------------
# get_children_by_uuid (Task 3.2b)
# -----------------------------------------------------------------------

class TestGetChildrenByUuid:
    """Tests for EntityDatabase.get_children_by_uuid()."""

    def test_parent_with_three_children(self, db):
        parent_uuid = _register(db, "project", "p1", "Project 1")
        c1 = _register(db, "feature", "f1", "F1",
                        parent_type_id="project:p1", status="active")
        c2 = _register(db, "feature", "f2", "F2",
                        parent_type_id="project:p1", status="active")
        c3 = _register(db, "feature", "f3", "F3",
                        parent_type_id="project:p1", status="active")

        children = db.get_children_by_uuid(parent_uuid)
        child_uuids = {c["uuid"] for c in children}
        assert child_uuids == {c1, c2, c3}

    def test_no_children(self, db):
        parent_uuid = _register(db, "project", "p1", "Project 1")
        children = db.get_children_by_uuid(parent_uuid)
        assert children == []

    def test_only_direct_children(self, db):
        """Grandchildren should not be returned."""
        gp_uuid = _register(db, "project", "p1", "Project 1")
        parent_uuid = _register(db, "feature", "f1", "F1",
                                 parent_type_id="project:p1")
        _register(db, "task", "t1", "T1",
                  parent_type_id="feature:f1")

        children = db.get_children_by_uuid(gp_uuid)
        assert len(children) == 1
        assert children[0]["uuid"] == parent_uuid

    def test_nonexistent_parent_uuid(self, db):
        """Querying a non-existent UUID returns empty list."""
        children = db.get_children_by_uuid("00000000-0000-4000-8000-000000000000")
        assert children == []


# -----------------------------------------------------------------------
# compute_progress()
# -----------------------------------------------------------------------

class TestComputeProgress:
    """Tests for compute_progress()."""

    def test_no_children(self, db):
        parent_uuid = _register(db, "project", "p1", "Project 1")
        assert compute_progress(db, parent_uuid) == 0.0

    def test_all_children_completed(self, db):
        parent_uuid = _register(db, "project", "p1", "Project 1")
        _register(db, "feature", "f1", "F1",
                  parent_type_id="project:p1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="project:p1", status="completed")
        _register(db, "feature", "f3", "F3",
                  parent_type_id="project:p1", status="completed")

        assert compute_progress(db, parent_uuid) == 1.0

    def test_feature_child_in_implement_phase(self, db):
        parent_uuid = _register(db, "project", "p1", "Project 1")
        _register(db, "feature", "f1", "F1",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "feature:f1", "implement")

        progress = compute_progress(db, parent_uuid)
        assert progress == pytest.approx(0.7)

    def test_feature_child_in_brainstorm_phase(self, db):
        parent_uuid = _register(db, "project", "p1", "Project 1")
        _register(db, "feature", "f1", "F1",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "feature:f1", "brainstorm")

        assert compute_progress(db, parent_uuid) == pytest.approx(0.0)

    def test_task_child_in_deliver_phase(self, db):
        """Tasks use 5D weights."""
        parent_uuid = _register(db, "feature", "f1", "Feature 1",
                                 status="active")
        _register(db, "task", "t1", "T1",
                  parent_type_id="feature:f1", status="active")
        _with_phase(db, "task:t1", "deliver")

        assert compute_progress(db, parent_uuid) == pytest.approx(0.7)

    def test_abandoned_children_excluded(self, db):
        """Abandoned children are excluded from both numerator and denominator."""
        parent_uuid = _register(db, "project", "p1", "Project 1")
        _register(db, "feature", "f1", "F1",
                  parent_type_id="project:p1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="project:p1", status="abandoned")

        # Only f1 counts: 1.0 / 1 active child = 1.0
        assert compute_progress(db, parent_uuid) == 1.0

    def test_all_children_abandoned(self, db):
        parent_uuid = _register(db, "project", "p1", "Project 1")
        _register(db, "feature", "f1", "F1",
                  parent_type_id="project:p1", status="abandoned")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="project:p1", status="abandoned")

        assert compute_progress(db, parent_uuid) == 0.0

    def test_mixed_children_progress(self, db):
        """One completed, one in implement, one abandoned."""
        parent_uuid = _register(db, "project", "p1", "Project 1")
        _register(db, "feature", "f1", "F1",
                  parent_type_id="project:p1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "feature:f2", "implement")
        _register(db, "feature", "f3", "F3",
                  parent_type_id="project:p1", status="abandoned")

        # f1=1.0, f2=0.7, f3=excluded => (1.0+0.7)/2 = 0.85
        assert compute_progress(db, parent_uuid) == pytest.approx(0.85)

    def test_child_without_workflow_phase_row(self, db):
        """Child with no workflow_phases row contributes 0.0."""
        parent_uuid = _register(db, "project", "p1", "Project 1")
        _register(db, "feature", "f1", "F1",
                  parent_type_id="project:p1", status="active")
        # No _with_phase call — no workflow_phases row

        assert compute_progress(db, parent_uuid) == pytest.approx(0.0)

    def test_child_with_unknown_phase(self, db):
        """Child with a phase not in the weight table contributes 0.0."""
        parent_uuid = _register(db, "project", "p1", "Project 1")
        _register(db, "feature", "f1", "F1",
                  parent_type_id="project:p1", status="active")
        # Use a valid CHECK phase that isn't in PHASE_WEIGHTS_7
        _with_phase(db, "feature:f1", "draft")

        assert compute_progress(db, parent_uuid) == pytest.approx(0.0)

    def test_five_d_child_phases(self, db):
        """5D entity types use PHASE_WEIGHTS_5D."""
        parent_uuid = _register(db, "initiative", "i1", "Init 1")
        _register(db, "project", "pr1", "Proj 1",
                  parent_type_id="initiative:i1", status="active")
        _with_phase(db, "project:pr1", "deliver")

        assert compute_progress(db, parent_uuid) == pytest.approx(0.7)


# -----------------------------------------------------------------------
# rollup_parent()
# -----------------------------------------------------------------------

class TestRollupParent:
    """Tests for rollup_parent()."""

    def test_no_parent_is_noop(self, db):
        """Child with no parent_uuid — rollup does nothing."""
        child_uuid = _register(db, "feature", "f1", "F1", status="completed")
        rollup_parent(db, child_uuid)
        # No exception, nothing to verify on parent

    def test_child_completion_updates_parent_progress(self, db):
        parent_uuid = _register(db, "project", "p1", "Project 1")
        child_uuid = _register(db, "feature", "f1", "F1",
                                parent_type_id="project:p1",
                                status="completed")

        rollup_parent(db, child_uuid)

        parent = db.get_entity_by_uuid(parent_uuid)
        meta = json.loads(parent["metadata"])
        assert meta["progress"] == pytest.approx(1.0)

    def test_partial_progress_rollup(self, db):
        parent_uuid = _register(db, "project", "p1", "Project 1")
        child1_uuid = _register(db, "feature", "f1", "F1",
                                 parent_type_id="project:p1",
                                 status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "feature:f2", "design")

        rollup_parent(db, child1_uuid)

        parent = db.get_entity_by_uuid(parent_uuid)
        meta = json.loads(parent["metadata"])
        # (1.0 + 0.3) / 2 = 0.65
        assert meta["progress"] == pytest.approx(0.65)

    def test_ancestor_chain_rollup(self, db):
        """Rollup propagates up: grandparent <- parent <- child."""
        gp_uuid = _register(db, "initiative", "i1", "Init 1")
        parent_uuid = _register(db, "project", "p1", "Project 1",
                                 parent_type_id="initiative:i1",
                                 status="active")
        _with_phase(db, "project:p1", "deliver")
        child_uuid = _register(db, "feature", "f1", "F1",
                                parent_type_id="project:p1",
                                status="completed")

        rollup_parent(db, child_uuid)

        # Parent progress: f1 completed = 1.0
        parent = db.get_entity_by_uuid(parent_uuid)
        parent_meta = json.loads(parent["metadata"])
        assert parent_meta["progress"] == pytest.approx(1.0)

        # Grandparent progress: p1 is active with deliver phase = 0.7
        gp = db.get_entity_by_uuid(gp_uuid)
        gp_meta = json.loads(gp["metadata"])
        assert gp_meta["progress"] == pytest.approx(0.7)

    def test_nonexistent_child_uuid_is_noop(self, db):
        """Passing a non-existent UUID does nothing."""
        rollup_parent(db, "00000000-0000-4000-8000-000000000000")
        # No exception

    def test_abandoned_children_excluded_from_rollup(self, db):
        parent_uuid = _register(db, "project", "p1", "Project 1")
        child1_uuid = _register(db, "feature", "f1", "F1",
                                 parent_type_id="project:p1",
                                 status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="project:p1", status="abandoned")

        rollup_parent(db, child1_uuid)

        parent = db.get_entity_by_uuid(parent_uuid)
        meta = json.loads(parent["metadata"])
        # Only f1 counts: 1.0/1 = 1.0
        assert meta["progress"] == pytest.approx(1.0)

    def test_max_depth_respected(self, db):
        """Chain deeper than _MAX_DEPTH stops at _MAX_DEPTH."""
        # Create a chain of _MAX_DEPTH + 2 entities
        type_ids = []
        uuids = []
        for i in range(_MAX_DEPTH + 2):
            etype = "project" if i % 2 == 0 else "feature"
            eid = f"e{i}"
            parent = type_ids[-1] if type_ids else None
            uuid = _register(db, etype, eid, f"Entity {i}",
                             parent_type_id=parent, status="active")
            type_ids.append(f"{etype}:{eid}")
            uuids.append(uuid)

        # Complete the last entity
        db.update_entity(type_ids[-1], status="completed")

        rollup_parent(db, uuids[-1])

        # Check that entities up to _MAX_DEPTH ancestors got progress,
        # but the root (which is _MAX_DEPTH + 1 levels up) did NOT
        root = db.get_entity_by_uuid(uuids[0])
        root_meta = json.loads(root["metadata"]) if root["metadata"] else {}
        # With _MAX_DEPTH=5 and chain depth=7, root shouldn't be reached
        assert "progress" not in root_meta

    def test_preserves_existing_metadata(self, db):
        """rollup_parent should merge progress into existing metadata."""
        parent_uuid = _register(db, "project", "p1", "Project 1",
                                 metadata={"team": "alpha", "priority": 1})
        child_uuid = _register(db, "feature", "f1", "F1",
                                parent_type_id="project:p1",
                                status="completed")

        rollup_parent(db, child_uuid)

        parent = db.get_entity_by_uuid(parent_uuid)
        meta = json.loads(parent["metadata"])
        assert meta["progress"] == pytest.approx(1.0)
        assert meta["team"] == "alpha"
        assert meta["priority"] == 1

    def test_all_children_complete_means_full_progress(self, db):
        """AC-25: all children complete => parent progress = 100%."""
        parent_uuid = _register(db, "project", "p1", "Project 1")
        c1 = _register(db, "feature", "f1", "F1",
                        parent_type_id="project:p1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="project:p1", status="completed")
        _register(db, "feature", "f3", "F3",
                  parent_type_id="project:p1", status="completed")

        rollup_parent(db, c1)

        parent = db.get_entity_by_uuid(parent_uuid)
        meta = json.loads(parent["metadata"])
        assert meta["progress"] == pytest.approx(1.0)
