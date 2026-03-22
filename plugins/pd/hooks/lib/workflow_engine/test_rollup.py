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
    compute_objective_score,
    compute_okr_score,
    compute_progress,
    compute_traffic_light,
    get_ancestor_progress,
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


# -----------------------------------------------------------------------
# compute_objective_score() — AC-34
# -----------------------------------------------------------------------

class TestComputeObjectiveScore:
    """Tests for compute_objective_score() — objective rollup from child KR scores."""

    def test_ac34_verification_scenario(self, db):
        """AC-34 verification: 3 KRs (0.8, 0.5, 1.0) → 0.77 → Green."""
        obj_uuid = _register(db, "objective", "o1", "Reliability Objective")
        _register(db, "key_result", "kr1", "KR A",
                  parent_type_id="objective:o1",
                  metadata={"metric_type": "baseline_target", "score": 0.8})
        _register(db, "key_result", "kr2", "KR B",
                  parent_type_id="objective:o1",
                  metadata={"metric_type": "baseline_target", "score": 0.5})
        _register(db, "key_result", "kr3", "KR C",
                  parent_type_id="objective:o1",
                  metadata={"metric_type": "baseline_target", "score": 1.0})

        score = compute_objective_score(db, obj_uuid)
        assert score == pytest.approx(0.77, abs=0.01)

        # Check stored metadata
        obj = db.get_entity_by_uuid(obj_uuid)
        meta = json.loads(obj["metadata"])
        assert meta["score"] == pytest.approx(0.77, abs=0.01)
        assert meta["traffic_light"] == "GREEN"

    def test_no_children_returns_zero(self, db):
        """Objective with no KR children → 0.0."""
        obj_uuid = _register(db, "objective", "o1", "Empty Objective")
        score = compute_objective_score(db, obj_uuid)
        assert score == pytest.approx(0.0)

    def test_single_kr_child(self, db):
        """Objective with one KR → score equals that KR's score."""
        obj_uuid = _register(db, "objective", "o1", "Single KR Obj")
        _register(db, "key_result", "kr1", "KR Solo",
                  parent_type_id="objective:o1",
                  metadata={"metric_type": "milestone"})
        # KR has no children → milestone score = 0.0
        score = compute_objective_score(db, obj_uuid)
        assert score == pytest.approx(0.0)

    def test_nonexistent_uuid_returns_zero(self, db):
        """Non-existent objective uuid → 0.0."""
        score = compute_objective_score(db, "00000000-0000-4000-8000-000000000000")
        assert score == pytest.approx(0.0)

    def test_abandoned_kr_children_excluded(self, db):
        """Abandoned KR children should be excluded from the average."""
        obj_uuid = _register(db, "objective", "o1", "Obj With Abandoned")
        _register(db, "key_result", "kr1", "KR Active",
                  parent_type_id="objective:o1", status="active",
                  metadata={"metric_type": "baseline_target", "score": 0.8})
        _register(db, "key_result", "kr2", "KR Abandoned",
                  parent_type_id="objective:o1", status="abandoned",
                  metadata={"metric_type": "baseline_target", "score": 0.0})

        score = compute_objective_score(db, obj_uuid)
        # Only kr1 counts: 0.8 / 1 = 0.8
        assert score == pytest.approx(0.8)

    def test_stores_traffic_light_red(self, db):
        """Low score → RED traffic light stored."""
        obj_uuid = _register(db, "objective", "o1", "Low Score Obj")
        _register(db, "key_result", "kr1", "KR Low",
                  parent_type_id="objective:o1",
                  metadata={"metric_type": "baseline_target", "score": 0.2})

        compute_objective_score(db, obj_uuid)

        obj = db.get_entity_by_uuid(obj_uuid)
        meta = json.loads(obj["metadata"])
        assert meta["traffic_light"] == "RED"

    def test_stores_traffic_light_yellow(self, db):
        """Mid-range score → YELLOW traffic light stored."""
        obj_uuid = _register(db, "objective", "o1", "Mid Score Obj")
        _register(db, "key_result", "kr1", "KR Mid",
                  parent_type_id="objective:o1",
                  metadata={"metric_type": "baseline_target", "score": 0.5})

        compute_objective_score(db, obj_uuid)

        obj = db.get_entity_by_uuid(obj_uuid)
        meta = json.loads(obj["metadata"])
        assert meta["traffic_light"] == "YELLOW"

    def test_preserves_existing_objective_metadata(self, db):
        """Score and traffic_light merge into existing metadata."""
        obj_uuid = _register(db, "objective", "o1", "Obj With Meta",
                             metadata={"team": "platform", "priority": 1})
        _register(db, "key_result", "kr1", "KR",
                  parent_type_id="objective:o1",
                  metadata={"metric_type": "baseline_target", "score": 0.9})

        compute_objective_score(db, obj_uuid)

        obj = db.get_entity_by_uuid(obj_uuid)
        meta = json.loads(obj["metadata"])
        assert meta["score"] == pytest.approx(0.9)
        assert meta["traffic_light"] == "GREEN"
        assert meta["team"] == "platform"
        assert meta["priority"] == 1

    def test_uses_compute_okr_score_for_each_kr(self, db):
        """KR scores are computed via compute_okr_score (milestone with children)."""
        obj_uuid = _register(db, "objective", "o1", "Milestone Obj")
        kr_uuid = _register(db, "key_result", "kr1", "KR Milestone",
                            parent_type_id="objective:o1",
                            metadata={"metric_type": "milestone"})
        _register(db, "feature", "f1", "F1",
                  parent_type_id="key_result:kr1", status="completed")
        _register(db, "feature", "f2", "F2",
                  parent_type_id="key_result:kr1", status="active")

        score = compute_objective_score(db, obj_uuid)
        # milestone: 1/2 = 0.5
        assert score == pytest.approx(0.5)

    def test_mixed_metric_types(self, db):
        """Objective with KRs of different metric types."""
        obj_uuid = _register(db, "objective", "o1", "Mixed Obj")
        # milestone KR: 1/1 = 1.0
        _register(db, "key_result", "kr1", "KR Milestone",
                  parent_type_id="objective:o1",
                  metadata={"metric_type": "milestone"})
        _register(db, "feature", "f1", "F1",
                  parent_type_id="key_result:kr1", status="completed")
        # baseline_target KR: manual score 0.5
        _register(db, "key_result", "kr2", "KR Target",
                  parent_type_id="objective:o1",
                  metadata={"metric_type": "baseline_target", "score": 0.5})

        score = compute_objective_score(db, obj_uuid)
        # (1.0 + 0.5) / 2 = 0.75
        assert score == pytest.approx(0.75)

    def test_non_kr_children_ignored(self, db):
        """Only key_result children are used for objective scoring."""
        obj_uuid = _register(db, "objective", "o1", "Obj With Mixed Children")
        _register(db, "key_result", "kr1", "KR",
                  parent_type_id="objective:o1",
                  metadata={"metric_type": "baseline_target", "score": 0.8})
        # A feature directly under the objective (should be ignored)
        _register(db, "feature", "f1", "Direct Feature",
                  parent_type_id="objective:o1", status="active")

        score = compute_objective_score(db, obj_uuid)
        # Only kr1 counts: 0.8
        assert score == pytest.approx(0.8)


# -----------------------------------------------------------------------
# get_ancestor_progress() — Task 6.4, AC-37
# -----------------------------------------------------------------------

class TestGetAncestorProgress:
    """Tests for get_ancestor_progress() — cross-level progress view."""

    def test_no_parent_returns_empty(self, db):
        """Entity with no parent → empty list."""
        uuid = _register(db, "feature", "f1", "Feature 1")
        result = get_ancestor_progress(db, uuid)
        assert result == []

    def test_single_parent(self, db):
        """Entity with one parent → single entry."""
        proj_uuid = _register(db, "project", "p1", "Project 1")
        db.update_entity("project:p1", metadata={"progress": 0.65, "traffic_light": "YELLOW"})
        feat_uuid = _register(db, "feature", "f1", "Feature 1",
                              parent_type_id="project:p1")

        result = get_ancestor_progress(db, feat_uuid)
        assert len(result) == 1
        assert result[0]["type_id"] == "project:p1"
        assert result[0]["name"] == "Project 1"
        assert result[0]["progress"] == pytest.approx(0.65)
        assert result[0]["traffic_light"] == "YELLOW"
        assert result[0]["depth"] == 1

    def test_full_hierarchy(self, db):
        """initiative → objective → KR → project → feature: returns 4 ancestors."""
        init_uuid = _register(db, "initiative", "i1", "Initiative Alpha")
        db.update_entity("initiative:i1", metadata={"progress": 0.5, "traffic_light": "YELLOW"})

        obj_uuid = _register(db, "objective", "o1", "Objective Beta",
                             parent_type_id="initiative:i1")
        db.update_entity("objective:o1", metadata={"progress": 0.7, "traffic_light": "GREEN"})

        kr_uuid = _register(db, "key_result", "kr1", "KR Gamma",
                            parent_type_id="objective:o1")
        db.update_entity("key_result:kr1", metadata={"progress": 0.3, "traffic_light": "RED"})

        proj_uuid = _register(db, "project", "p1", "Project Delta",
                              parent_type_id="key_result:kr1")
        db.update_entity("project:p1", metadata={"progress": 0.85, "traffic_light": "GREEN"})

        feat_uuid = _register(db, "feature", "f1", "Feature Epsilon",
                              parent_type_id="project:p1")

        result = get_ancestor_progress(db, feat_uuid)
        assert len(result) == 4

        # Nearest first
        assert result[0]["type_id"] == "project:p1"
        assert result[0]["depth"] == 1
        assert result[0]["progress"] == pytest.approx(0.85)

        assert result[1]["type_id"] == "key_result:kr1"
        assert result[1]["depth"] == 2

        assert result[2]["type_id"] == "objective:o1"
        assert result[2]["depth"] == 3

        assert result[3]["type_id"] == "initiative:i1"
        assert result[3]["depth"] == 4
        assert result[3]["progress"] == pytest.approx(0.5)

    def test_max_depth_5(self, db):
        """Chain deeper than 5 → stops at 5 ancestors."""
        # Build a chain of 7 entities (6 parents above the leaf)
        prev_type_id = None
        uuids = []
        for i in range(7):
            etype = "project" if i % 2 == 0 else "feature"
            eid = f"e{i}"
            uuid = _register(db, etype, eid, f"Entity {i}",
                             parent_type_id=prev_type_id, status="active")
            db.update_entity(f"{etype}:{eid}", metadata={"progress": 0.1 * i, "traffic_light": "RED"})
            prev_type_id = f"{etype}:{eid}"
            uuids.append(uuid)

        result = get_ancestor_progress(db, uuids[-1])
        assert len(result) == 5  # max depth

    def test_missing_progress_returns_none(self, db):
        """Ancestor with no stored progress → progress=None, traffic_light=None."""
        proj_uuid = _register(db, "project", "p1", "Project 1")
        # No metadata update → no progress stored
        feat_uuid = _register(db, "feature", "f1", "Feature 1",
                              parent_type_id="project:p1")

        result = get_ancestor_progress(db, feat_uuid)
        assert len(result) == 1
        assert result[0]["progress"] is None
        assert result[0]["traffic_light"] is None

    def test_nonexistent_uuid_returns_empty(self, db):
        """Non-existent entity UUID → empty list."""
        result = get_ancestor_progress(db, "00000000-0000-4000-8000-000000000000")
        assert result == []

    def test_full_hierarchy_with_rollup(self, db):
        """End-to-end: build hierarchy, rollup, then verify ancestor progress view."""
        # Build: initiative → project → feature (completed)
        init_uuid = _register(db, "initiative", "i1", "Init")
        proj_uuid = _register(db, "project", "p1", "Proj",
                              parent_type_id="initiative:i1", status="active")
        _with_phase(db, "project:p1", "deliver")
        feat_uuid = _register(db, "feature", "f1", "Feat",
                              parent_type_id="project:p1", status="completed")

        # Run rollup from leaf to populate stored values
        rollup_parent(db, feat_uuid)

        # Now check ancestor progress from the feature
        result = get_ancestor_progress(db, feat_uuid)
        assert len(result) == 2

        # Project: 1 completed child → 1.0
        assert result[0]["type_id"] == "project:p1"
        assert result[0]["progress"] == pytest.approx(1.0)
        assert result[0]["traffic_light"] == "GREEN"

        # Initiative: 1 active child in deliver → 0.7
        assert result[1]["type_id"] == "initiative:i1"
        assert result[1]["progress"] == pytest.approx(0.7)
        assert result[1]["traffic_light"] == "GREEN"


# ---------------------------------------------------------------------------
# Weighted objective scoring tests (gap remediation)
# ---------------------------------------------------------------------------


class TestComputeObjectiveScoreWeighted:
    """Tests for compute_objective_score with weighted KRs."""

    def test_weighted_average(self, db):
        """KR1(completed, weight=2.0) + KR2(active/no-phase, weight=1.0) → weighted."""
        obj_uuid = _register(db, "objective", "o1", "Objective 1")
        _register(db, "key_result", "kr1", "KR 1",
                  parent_type_id="objective:o1", status="completed",
                  metadata={"metric_type": "baseline_target", "score": 1.0, "weight": 2.0})
        _register(db, "key_result", "kr2", "KR 2",
                  parent_type_id="objective:o1", status="active",
                  metadata={"metric_type": "baseline_target", "score": 0.0, "weight": 1.0})
        # KR1 score=1.0 (baseline_target), KR2 score=0.0 (baseline_target)
        # weighted: (1.0*2.0 + 0.0*1.0) / (2.0+1.0) = 2/3
        score = compute_objective_score(db, obj_uuid)
        assert score == pytest.approx(2.0 / 3.0, abs=0.01)

    def test_default_weights_backward_compat(self, db):
        """No weights → equal average."""
        obj_uuid = _register(db, "objective", "o2", "Objective 2")
        _register(db, "key_result", "kr-a", "KR A",
                  parent_type_id="objective:o2", status="active",
                  metadata={"metric_type": "baseline_target", "score": 1.0})
        _register(db, "key_result", "kr-b", "KR B",
                  parent_type_id="objective:o2", status="active",
                  metadata={"metric_type": "baseline_target", "score": 0.0})
        # (1.0 + 0.0) / 2 = 0.5
        score = compute_objective_score(db, obj_uuid)
        assert score == pytest.approx(0.5)

    def test_all_weights_zero(self, db):
        """All KRs weight=0.0 → returns 0.0 (no ZeroDivisionError)."""
        obj_uuid = _register(db, "objective", "o3", "Objective 3")
        _register(db, "key_result", "kr-z1", "KR Z1",
                  parent_type_id="objective:o3", status="completed",
                  metadata={"metric_type": "baseline_target", "score": 1.0, "weight": 0.0})
        score = compute_objective_score(db, obj_uuid)
        assert score == 0.0

    def test_mixed_weights(self, db):
        """Weight=3 completed + weight=1 zero-score → 0.75."""
        obj_uuid = _register(db, "objective", "o6", "Objective 6")
        _register(db, "key_result", "kr-w3", "KR W3",
                  parent_type_id="objective:o6", status="active",
                  metadata={"metric_type": "baseline_target", "score": 1.0, "weight": 3.0})
        _register(db, "key_result", "kr-w1", "KR W1",
                  parent_type_id="objective:o6", status="active",
                  metadata={"metric_type": "baseline_target", "score": 0.0, "weight": 1.0})
        # (1.0*3.0 + 0.0*1.0) / (3.0+1.0) = 0.75
        score = compute_objective_score(db, obj_uuid)
        assert score == pytest.approx(0.75)

    def test_invalid_weight_defaults_to_one(self, db):
        """Non-numeric weight defaults to 1.0."""
        obj_uuid = _register(db, "objective", "o7", "Objective 7")
        _register(db, "key_result", "kr-bad-w", "Bad Weight KR",
                  parent_type_id="objective:o7", status="active",
                  metadata={"metric_type": "baseline_target", "score": 1.0, "weight": "heavy"})
        score = compute_objective_score(db, obj_uuid)
        assert score == pytest.approx(1.0)

    def test_weight_int_accepted(self, db):
        """Integer weight is accepted and converted to float."""
        obj_uuid = _register(db, "objective", "o8", "Objective 8")
        _register(db, "key_result", "kr-int", "Int Weight KR",
                  parent_type_id="objective:o8", status="active",
                  metadata={"metric_type": "baseline_target", "score": 1.0, "weight": 2})
        score = compute_objective_score(db, obj_uuid)
        assert score == pytest.approx(1.0)
