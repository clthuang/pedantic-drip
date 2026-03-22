"""Tests for the progress rollup engine (rollup.py).

Covers:
- PHASE_WEIGHTS_7 and PHASE_WEIGHTS_5D constants
- compute_progress() with various child states
- rollup_parent() ancestor chain traversal
- compute_okr_score() with milestone, binary, baseline_target, and default
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
    compute_okr_score,
    compute_progress,
    compute_traffic_light,
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

    def test_traffic_light_stored_in_metadata(self, db):
        """AC-27: rollup stores traffic_light alongside progress."""
        parent_uuid = _register(db, "project", "p1", "Project 1")
        child_uuid = _register(db, "feature", "f1", "F1",
                                parent_type_id="project:p1",
                                status="completed")

        rollup_parent(db, child_uuid)

        parent = db.get_entity_by_uuid(parent_uuid)
        meta = json.loads(parent["metadata"])
        assert meta["progress"] == pytest.approx(1.0)
        assert meta["traffic_light"] == "GREEN"

    def test_traffic_light_yellow_on_partial_progress(self, db):
        """AC-27: progress 0.65 → YELLOW traffic light."""
        parent_uuid = _register(db, "project", "p1", "Project 1")
        child_uuid = _register(db, "feature", "f1", "F1",
                                parent_type_id="project:p1",
                                status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "feature:f2", "design")

        rollup_parent(db, child_uuid)

        parent = db.get_entity_by_uuid(parent_uuid)
        meta = json.loads(parent["metadata"])
        # (1.0 + 0.3) / 2 = 0.65
        assert meta["progress"] == pytest.approx(0.65)
        assert meta["traffic_light"] == "YELLOW"

    def test_traffic_light_red_on_low_progress(self, db):
        """AC-27: low progress → RED traffic light."""
        parent_uuid = _register(db, "project", "p1", "Project 1")
        child_uuid = _register(db, "feature", "f1", "F1",
                                parent_type_id="project:p1", status="active")
        _with_phase(db, "feature:f1", "specify")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "feature:f2", "brainstorm")

        rollup_parent(db, child_uuid)

        parent = db.get_entity_by_uuid(parent_uuid)
        meta = json.loads(parent["metadata"])
        # (0.1 + 0.0) / 2 = 0.05
        assert meta["progress"] == pytest.approx(0.05)
        assert meta["traffic_light"] == "RED"

    def test_traffic_light_propagates_up_ancestor_chain(self, db):
        """Traffic light stored at every level of the ancestor chain."""
        gp_uuid = _register(db, "initiative", "i1", "Init 1")
        _register(db, "project", "p1", "Project 1",
                  parent_type_id="initiative:i1", status="active")
        _with_phase(db, "project:p1", "deliver")
        child_uuid = _register(db, "feature", "f1", "F1",
                                parent_type_id="project:p1",
                                status="completed")

        rollup_parent(db, child_uuid)

        gp = db.get_entity_by_uuid(gp_uuid)
        gp_meta = json.loads(gp["metadata"])
        assert "traffic_light" in gp_meta
        # p1 phase=deliver => 0.7 progress => GREEN
        assert gp_meta["traffic_light"] == "GREEN"

    def test_ac27_verification_scenario(self, db):
        """AC-27 verification: 3 features (completed, implement, design) → 0.67 → YELLOW."""
        parent_uuid = _register(db, "project", "p1", "Project 1")
        c1 = _register(db, "feature", "f1", "F1",
                        parent_type_id="project:p1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "feature:f2", "implement")
        _register(db, "feature", "f3", "F3",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "feature:f3", "design")

        rollup_parent(db, c1)

        parent = db.get_entity_by_uuid(parent_uuid)
        meta = json.loads(parent["metadata"])
        # (1.0 + 0.7 + 0.3) / 3 = 0.6667
        assert meta["progress"] == pytest.approx(2.0 / 3.0, abs=0.01)
        assert meta["traffic_light"] == "YELLOW"


# -----------------------------------------------------------------------
# compute_traffic_light()
# -----------------------------------------------------------------------

class TestComputeTrafficLight:
    """Tests for compute_traffic_light() — AC-27 thresholds."""

    def test_red_at_zero(self):
        assert compute_traffic_light(0.0) == "RED"

    def test_red_below_threshold(self):
        assert compute_traffic_light(0.39) == "RED"

    def test_yellow_at_boundary(self):
        """Exactly 0.4 → YELLOW."""
        assert compute_traffic_light(0.4) == "YELLOW"

    def test_yellow_mid_range(self):
        assert compute_traffic_light(0.5) == "YELLOW"

    def test_yellow_just_below_green(self):
        assert compute_traffic_light(0.69) == "YELLOW"

    def test_green_at_boundary(self):
        """Exactly 0.7 → GREEN."""
        assert compute_traffic_light(0.7) == "GREEN"

    def test_green_high(self):
        assert compute_traffic_light(0.85) == "GREEN"

    def test_green_at_one(self):
        assert compute_traffic_light(1.0) == "GREEN"

    def test_red_just_below_yellow(self):
        """0.399... → RED (boundary precision)."""
        assert compute_traffic_light(0.3999999) == "RED"

    def test_yellow_just_below_green_precise(self):
        """0.699... → YELLOW (boundary precision)."""
        assert compute_traffic_light(0.6999999) == "YELLOW"


class TestComputeProgressMixedChildren:
    """AC-27: project with mixed 7-phase and 5D children."""

    def test_mixed_feature_and_task_children(self, db):
        """Project with feature (7-phase) and task (5D) children."""
        parent_uuid = _register(db, "project", "p1", "Project 1")
        _register(db, "feature", "f1", "F1",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "feature:f1", "implement")  # 0.7
        _register(db, "task", "t1", "T1",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "task:t1", "define")  # 0.1

        progress = compute_progress(db, parent_uuid)
        # (0.7 + 0.1) / 2 = 0.4
        assert progress == pytest.approx(0.4)

    def test_mixed_children_with_completed(self, db):
        """Feature completed + task in deliver + feature in brainstorm."""
        parent_uuid = _register(db, "project", "p1", "Project 1")
        _register(db, "feature", "f1", "F1",
                  parent_type_id="project:p1", status="completed")  # 1.0
        _register(db, "task", "t1", "T1",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "task:t1", "deliver")  # 0.7
        _register(db, "feature", "f2", "F2",
                  parent_type_id="project:p1", status="active")
        _with_phase(db, "feature:f2", "brainstorm")  # 0.0

        progress = compute_progress(db, parent_uuid)
        # (1.0 + 0.7 + 0.0) / 3 ≈ 0.567
        assert progress == pytest.approx(1.7 / 3.0)


# -----------------------------------------------------------------------
# compute_okr_score() — AC-32
# -----------------------------------------------------------------------

class TestComputeOkrScore:
    """Tests for compute_okr_score() — KR scoring by metric_type."""

    # -- milestone metric_type --

    def test_milestone_two_of_three_complete(self, db):
        """AC-32 verification: milestone KR with 2/3 children complete → 0.67."""
        kr_uuid = _register(db, "key_result", "kr1", "KR milestone",
                            metadata={"metric_type": "milestone"})
        _register(db, "feature", "f1", "F1",
                  parent_type_id="key_result:kr1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="key_result:kr1", status="completed")
        _register(db, "feature", "f3", "F3",
                  parent_type_id="key_result:kr1", status="active")

        score = compute_okr_score(db, kr_uuid)
        assert score == pytest.approx(2.0 / 3.0, abs=0.01)

    def test_milestone_all_complete(self, db):
        """All children complete → 1.0."""
        kr_uuid = _register(db, "key_result", "kr1", "KR milestone",
                            metadata={"metric_type": "milestone"})
        _register(db, "feature", "f1", "F1",
                  parent_type_id="key_result:kr1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="key_result:kr1", status="completed")

        assert compute_okr_score(db, kr_uuid) == pytest.approx(1.0)

    def test_milestone_none_complete(self, db):
        """No children complete → 0.0."""
        kr_uuid = _register(db, "key_result", "kr1", "KR milestone",
                            metadata={"metric_type": "milestone"})
        _register(db, "feature", "f1", "F1",
                  parent_type_id="key_result:kr1", status="active")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="key_result:kr1", status="active")

        assert compute_okr_score(db, kr_uuid) == pytest.approx(0.0)

    def test_milestone_abandoned_children_excluded(self, db):
        """Abandoned children excluded from both numerator and denominator."""
        kr_uuid = _register(db, "key_result", "kr1", "KR milestone",
                            metadata={"metric_type": "milestone"})
        _register(db, "feature", "f1", "F1",
                  parent_type_id="key_result:kr1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="key_result:kr1", status="abandoned")

        # 1 completed / 1 active = 1.0
        assert compute_okr_score(db, kr_uuid) == pytest.approx(1.0)

    def test_milestone_no_children(self, db):
        """Milestone KR with no children → 0.0."""
        kr_uuid = _register(db, "key_result", "kr1", "KR milestone",
                            metadata={"metric_type": "milestone"})
        assert compute_okr_score(db, kr_uuid) == pytest.approx(0.0)

    # -- binary metric_type --

    def test_binary_all_complete(self, db):
        """Binary KR: all children complete → 1.0."""
        kr_uuid = _register(db, "key_result", "kr1", "KR binary",
                            metadata={"metric_type": "binary"})
        _register(db, "feature", "f1", "F1",
                  parent_type_id="key_result:kr1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="key_result:kr1", status="completed")

        assert compute_okr_score(db, kr_uuid) == pytest.approx(1.0)

    def test_binary_not_all_complete(self, db):
        """Binary KR: not all children complete → 0.0."""
        kr_uuid = _register(db, "key_result", "kr1", "KR binary",
                            metadata={"metric_type": "binary"})
        _register(db, "feature", "f1", "F1",
                  parent_type_id="key_result:kr1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="key_result:kr1", status="active")

        assert compute_okr_score(db, kr_uuid) == pytest.approx(0.0)

    def test_binary_no_children_manual(self, db):
        """AC-32: Binary KR without children → manual score from metadata."""
        kr_uuid = _register(db, "key_result", "kr1", "KR binary",
                            metadata={"metric_type": "binary", "score": 1.0})

        assert compute_okr_score(db, kr_uuid) == pytest.approx(1.0)

    def test_binary_no_children_no_score(self, db):
        """Binary KR without children and no score → 0.0."""
        kr_uuid = _register(db, "key_result", "kr1", "KR binary",
                            metadata={"metric_type": "binary"})

        assert compute_okr_score(db, kr_uuid) == pytest.approx(0.0)

    def test_binary_abandoned_excluded(self, db):
        """Binary KR: abandoned children excluded, remaining all complete → 1.0."""
        kr_uuid = _register(db, "key_result", "kr1", "KR binary",
                            metadata={"metric_type": "binary"})
        _register(db, "feature", "f1", "F1",
                  parent_type_id="key_result:kr1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="key_result:kr1", status="abandoned")

        assert compute_okr_score(db, kr_uuid) == pytest.approx(1.0)

    # -- baseline_target metric_type --

    def test_baseline_target_returns_stored_score(self, db):
        """Baseline/target KR → manual only, return stored score."""
        kr_uuid = _register(db, "key_result", "kr1", "KR target",
                            metadata={"metric_type": "baseline_target", "score": 0.75})

        assert compute_okr_score(db, kr_uuid) == pytest.approx(0.75)

    def test_baseline_target_no_score(self, db):
        """Baseline/target KR with no stored score → 0.0."""
        kr_uuid = _register(db, "key_result", "kr1", "KR target",
                            metadata={"metric_type": "baseline_target"})

        assert compute_okr_score(db, kr_uuid) == pytest.approx(0.0)

    # -- default / un-scored --

    def test_no_metric_type(self, db):
        """KR with no metric_type → 0.0 (un-scored default)."""
        kr_uuid = _register(db, "key_result", "kr1", "KR unscored",
                            metadata={})

        assert compute_okr_score(db, kr_uuid) == pytest.approx(0.0)

    def test_none_metadata(self, db):
        """KR with None metadata → 0.0."""
        kr_uuid = _register(db, "key_result", "kr1", "KR no meta")

        assert compute_okr_score(db, kr_uuid) == pytest.approx(0.0)

    def test_unknown_metric_type(self, db):
        """KR with unrecognized metric_type → 0.0."""
        kr_uuid = _register(db, "key_result", "kr1", "KR unknown",
                            metadata={"metric_type": "velocity"})

        assert compute_okr_score(db, kr_uuid) == pytest.approx(0.0)

    def test_nonexistent_uuid(self, db):
        """Non-existent KR uuid → 0.0."""
        assert compute_okr_score(db, "00000000-0000-4000-8000-000000000000") == 0.0

    # -- score stored in metadata on compute --

    def test_score_stored_in_metadata(self, db):
        """compute_okr_score stores result in KR metadata."""
        kr_uuid = _register(db, "key_result", "kr1", "KR milestone",
                            metadata={"metric_type": "milestone"})
        _register(db, "feature", "f1", "F1",
                  parent_type_id="key_result:kr1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="key_result:kr1", status="active")

        compute_okr_score(db, kr_uuid)

        entity = db.get_entity_by_uuid(kr_uuid)
        meta = json.loads(entity["metadata"])
        assert meta["score"] == pytest.approx(0.5)

    def test_score_preserves_existing_metadata(self, db):
        """Storing score merges into existing metadata."""
        kr_uuid = _register(db, "key_result", "kr1", "KR milestone",
                            metadata={"metric_type": "milestone", "priority": "high"})
        _register(db, "feature", "f1", "F1",
                  parent_type_id="key_result:kr1", status="completed")

        compute_okr_score(db, kr_uuid)

        entity = db.get_entity_by_uuid(kr_uuid)
        meta = json.loads(entity["metadata"])
        assert meta["score"] == pytest.approx(1.0)
        assert meta["priority"] == "high"
        assert meta["metric_type"] == "milestone"
