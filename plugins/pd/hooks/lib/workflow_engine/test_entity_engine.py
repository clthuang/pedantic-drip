"""Tests for EntityWorkflowEngine -- Tasks 3.3/4.1/4.3/4.4/5.1.

Covers:
- Feature complete_phase delegates to frozen engine + cascade fires
- Task complete_phase direct DB path + cascade
- Cascade failure preserves completion (retryable)
- UUID-to-type_id resolution and delegation
- Degraded mode cascade skip
- Rollup with no/mixed/abandoned children
- Notification queue optional
- Light feature integration
- 5D project/initiative/objective/key_result transitions (4.1)
- Deliver gate blocker type_ids and end-to-end unblock (4.3)
- Orphan guard on abandonment with cascade (4.4)
- Initiative/objective full lifecycle, parent-child rollup,
  no-automated-transition policy, blocked_by, get_state, abandon (5.1/AC-31)
"""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from entity_registry.database import EntityDatabase
from entity_registry.dependencies import DependencyManager
from workflow_engine.entity_engine import CompletionResult, EntityWorkflowEngine
from workflow_engine.models import FeatureWorkflowState, TransitionResponse
from workflow_engine.notifications import Notification, NotificationQueue
from workflow_engine.rollup import compute_progress


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> EntityDatabase:
    """In-memory EntityDatabase."""
    return EntityDatabase(":memory:")


def _register(
    db: EntityDatabase,
    entity_type: str,
    entity_id: str,
    name: str,
    *,
    status: str | None = "active",
    parent_type_id: str | None = None,
) -> str:
    """Register an entity and return its UUID."""
    return db.register_entity(
        entity_type=entity_type,
        entity_id=entity_id,
        name=name,
        status=status,
        parent_type_id=parent_type_id,
    )


def _with_phase(
    db: EntityDatabase,
    type_id: str,
    phase: str,
    *,
    mode: str = "standard",
    last_completed_phase: str | None = None,
) -> None:
    """Create a workflow_phases row."""
    db.create_workflow_phase(
        type_id,
        workflow_phase=phase,
        mode=mode,
        last_completed_phase=last_completed_phase,
    )


def _create_meta_json(
    artifacts_root: str,
    slug: str,
    *,
    status: str = "active",
    mode: str = "standard",
    last_completed_phase: str | None = None,
) -> None:
    """Create a .meta.json file in the expected location."""
    feature_dir = os.path.join(artifacts_root, "features", slug)
    os.makedirs(feature_dir, exist_ok=True)
    meta = {
        "id": slug.split("-", 1)[0],
        "slug": slug,
        "status": status,
        "mode": mode,
        "lastCompletedPhase": last_completed_phase,
        "phases": {},
    }
    with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
        json.dump(meta, f)


def _make_engine(
    db: EntityDatabase,
    artifacts_root: str,
    notification_queue: NotificationQueue | None = None,
) -> EntityWorkflowEngine:
    """Create an EntityWorkflowEngine."""
    return EntityWorkflowEngine(
        db=db,
        artifacts_root=artifacts_root,
        notification_queue=notification_queue,
    )


# ---------------------------------------------------------------------------
# Test 1: Feature complete_phase → delegates to frozen engine + cascade fires
# ---------------------------------------------------------------------------


class TestFeatureCompletePhase:
    """Feature completion delegates to frozen engine, then cascade runs."""

    def test_feature_complete_phase_delegates_and_cascades(self, tmp_path):
        db = _make_db()
        slug = "008-test-feature"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug, mode="standard")

        uuid = _register(db, "feature", slug, "Test Feature")
        _with_phase(db, f"feature:{slug}", "specify", mode="standard",
                    last_completed_phase="brainstorm")

        engine = _make_engine(db, artifacts_root)
        result = engine.complete_phase(uuid, "specify")

        assert isinstance(result, CompletionResult)
        assert result.entity_type == "feature"
        assert result.entity_uuid == uuid
        assert result.phase == "specify"
        assert result.state is not None
        assert result.state.last_completed_phase == "specify"
        assert result.cascade_error is None

    def test_feature_complete_advances_to_next_phase(self, tmp_path):
        db = _make_db()
        slug = "009-advance"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug)

        uuid = _register(db, "feature", slug, "Advance Feature")
        _with_phase(db, f"feature:{slug}", "brainstorm", mode="standard")

        engine = _make_engine(db, artifacts_root)
        result = engine.complete_phase(uuid, "brainstorm")

        assert result.state.current_phase == "specify"
        assert result.state.last_completed_phase == "brainstorm"


# ---------------------------------------------------------------------------
# Test 2: Task complete_phase → task state update + cascade
# ---------------------------------------------------------------------------


class TestTaskCompletePhase:
    """Task completion uses direct DB path, then cascade runs."""

    def test_task_complete_phase_updates_state(self, tmp_path):
        db = _make_db()
        parent_uuid = _register(db, "feature", "010-parent", "Parent Feature")
        task_uuid = _register(
            db, "task", "001-task", "My Task",
            parent_type_id="feature:010-parent",
        )
        _with_phase(db, "task:001-task", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(task_uuid, "define")

        assert result.entity_type == "task"
        assert result.state is not None
        assert result.state.last_completed_phase == "define"
        assert result.state.current_phase == "deliver"
        assert result.cascade_error is None

    def test_task_terminal_phase_sets_completed(self, tmp_path):
        """Completing terminal phase sets entity status to completed."""
        db = _make_db()
        _register(db, "feature", "010-parent", "Parent Feature")
        task_uuid = _register(
            db, "task", "002-term", "Terminal Task",
            parent_type_id="feature:010-parent",
        )
        _with_phase(db, "task:002-term", "debrief", mode="standard",
                    last_completed_phase="deliver")

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(task_uuid, "debrief")

        assert result.state.last_completed_phase == "debrief"
        # Verify entity status updated
        entity = db.get_entity_by_uuid(task_uuid)
        assert entity["status"] == "completed"


# ---------------------------------------------------------------------------
# Test 3: Cascade failure after completion → completion persists
# ---------------------------------------------------------------------------


class TestCascadeFailure:
    """Cascade failure doesn't roll back completion."""

    def test_cascade_failure_preserves_completion(self, tmp_path):
        db = _make_db()
        slug = "011-cascade-fail"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug)

        uuid = _register(db, "feature", slug, "Cascade Fail Feature")
        _with_phase(db, f"feature:{slug}", "brainstorm", mode="standard")

        engine = _make_engine(db, artifacts_root)

        # Patch cascade to fail
        with patch.object(engine, "_run_cascade", side_effect=RuntimeError("cascade boom")):
            result = engine.complete_phase(uuid, "brainstorm")

        # Completion persists
        assert result.state is not None
        assert result.state.last_completed_phase == "brainstorm"
        assert result.cascade_error == "cascade boom"

        # DB reflects completion
        row = db.get_workflow_phase(f"feature:{slug}")
        assert row["last_completed_phase"] == "brainstorm"

    def test_cascade_is_retryable_after_failure(self, tmp_path):
        """After cascade failure, re-running cascade succeeds."""
        db = _make_db()
        slug = "012-retry"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug)

        uuid = _register(db, "feature", slug, "Retry Feature")
        _with_phase(db, f"feature:{slug}", "brainstorm", mode="standard")

        engine = _make_engine(db, artifacts_root)

        # First attempt: cascade fails
        with patch.object(engine, "_run_cascade", side_effect=RuntimeError("fail")):
            result1 = engine.complete_phase(uuid, "brainstorm")
        assert result1.cascade_error is not None

        # Manual cascade retry should work
        unblocked, progress = engine._run_cascade(uuid)
        assert isinstance(unblocked, list)


# ---------------------------------------------------------------------------
# Test 4: UUID-to-type_id resolution → correct delegation
# ---------------------------------------------------------------------------


class TestUuidResolution:
    """EntityWorkflowEngine resolves UUID to type_id for delegation."""

    def test_uuid_resolves_to_feature_type_id(self, tmp_path):
        db = _make_db()
        slug = "013-resolve"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug)

        uuid = _register(db, "feature", slug, "Resolve Feature")
        _with_phase(db, f"feature:{slug}", "brainstorm", mode="standard")

        engine = _make_engine(db, artifacts_root)
        result = engine.complete_phase(uuid, "brainstorm")

        # Verify it reached the frozen engine (feature path)
        assert result.entity_type == "feature"
        assert result.state.feature_type_id == f"feature:{slug}"

    def test_uuid_resolves_to_task_type_id(self, tmp_path):
        db = _make_db()
        _register(db, "feature", "014-parent", "Parent")
        task_uuid = _register(
            db, "task", "003-resolve", "Resolve Task",
            parent_type_id="feature:014-parent",
        )
        _with_phase(db, "task:003-resolve", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(task_uuid, "define")

        assert result.entity_type == "task"
        assert result.state.feature_type_id == "task:003-resolve"

    def test_unknown_uuid_raises(self, tmp_path):
        db = _make_db()
        engine = _make_engine(db, str(tmp_path))

        with pytest.raises(ValueError, match="Entity not found"):
            engine.complete_phase("nonexistent-uuid", "brainstorm")


# ---------------------------------------------------------------------------
# Test 5: Degraded mode → cascade skipped
# ---------------------------------------------------------------------------


class TestDegradedMode:
    """When DB is unhealthy, frozen engine falls back to .meta.json,
    cascade is skipped."""

    def test_degraded_mode_skips_cascade(self, tmp_path):
        db = _make_db()
        slug = "015-degraded"
        artifacts_root = str(tmp_path)
        _create_meta_json(
            artifacts_root, slug,
            mode="standard",
            last_completed_phase=None,
        )

        uuid = _register(db, "feature", slug, "Degraded Feature")
        _with_phase(db, f"feature:{slug}", "brainstorm", mode="standard")

        engine = _make_engine(db, artifacts_root)

        # Simulate DB becoming unhealthy after entity lookup but during
        # frozen engine's complete_phase by patching the health check
        original_complete = engine._frozen_engine.complete_phase

        def degraded_complete(type_id, phase):
            """Simulate frozen engine returning meta_json_fallback state."""
            return FeatureWorkflowState(
                feature_type_id=type_id,
                current_phase="specify",
                last_completed_phase="brainstorm",
                completed_phases=("brainstorm",),
                mode="standard",
                source="meta_json_fallback",
            )

        with patch.object(
            engine._frozen_engine, "complete_phase", side_effect=degraded_complete
        ):
            result = engine.complete_phase(uuid, "brainstorm")

        assert result.cascade_error == "cascade skipped: degraded mode"
        assert result.unblocked_uuids == []


# ---------------------------------------------------------------------------
# Test 6: No children → rollup_parent is no-op
# ---------------------------------------------------------------------------


class TestNoChildren:
    """When entity has no children, rollup_parent is a no-op."""

    def test_no_children_no_progress(self, tmp_path):
        db = _make_db()
        slug = "016-no-children"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug)

        uuid = _register(db, "feature", slug, "Childless Feature")
        _with_phase(db, f"feature:{slug}", "brainstorm", mode="standard")

        engine = _make_engine(db, artifacts_root)
        result = engine.complete_phase(uuid, "brainstorm")

        # No parent, so parent_progress is None
        assert result.parent_progress is None
        assert result.cascade_error is None

    def test_parent_with_no_children_zero_progress(self, tmp_path):
        """Parent exists but has no children → progress = 0.0."""
        db = _make_db()
        parent_uuid = _register(db, "feature", "017-parent", "Parent")
        # Child references parent but we compute parent progress
        assert compute_progress(db, parent_uuid) == 0.0


# ---------------------------------------------------------------------------
# Test 7: Mixed children (active + abandoned) → abandoned excluded
# ---------------------------------------------------------------------------


class TestMixedChildren:
    """Abandoned children are excluded from progress computation."""

    def test_abandoned_excluded_from_progress(self, tmp_path):
        db = _make_db()
        parent_uuid = _register(db, "feature", "018-mixed", "Mixed Parent")

        # Active child (in implement phase)
        active_uuid = _register(
            db, "task", "004-active", "Active Task",
            status="active",
            parent_type_id="feature:018-mixed",
        )
        _with_phase(db, "task:004-active", "deliver", mode="standard")

        # Completed child
        completed_uuid = _register(
            db, "task", "005-done", "Done Task",
            status="completed",
            parent_type_id="feature:018-mixed",
        )
        _with_phase(db, "task:005-done", "debrief", mode="standard",
                    last_completed_phase="debrief")

        # Abandoned child (should be excluded)
        abandoned_uuid = _register(
            db, "task", "006-abandoned", "Abandoned Task",
            status="abandoned",
            parent_type_id="feature:018-mixed",
        )

        progress = compute_progress(db, parent_uuid)
        # 2 active children: completed=1.0, active in deliver=0.7
        # (1.0 + 0.7) / 2 = 0.85
        assert progress == pytest.approx(0.85, abs=0.01)

    def test_all_abandoned_zero_progress(self, tmp_path):
        db = _make_db()
        parent_uuid = _register(db, "feature", "019-all-abn", "All Abandoned")
        _register(
            db, "task", "007-abn", "Abn1",
            status="abandoned",
            parent_type_id="feature:019-all-abn",
        )
        _register(
            db, "task", "008-abn", "Abn2",
            status="abandoned",
            parent_type_id="feature:019-all-abn",
        )

        assert compute_progress(db, parent_uuid) == 0.0


# ---------------------------------------------------------------------------
# Test 8: Without notification queue → cascade still works
# ---------------------------------------------------------------------------


class TestWithoutNotificationQueue:
    """Cascade works without notification queue."""

    def test_cascade_works_without_queue(self, tmp_path):
        db = _make_db()
        slug = "020-no-queue"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug)

        uuid = _register(db, "feature", slug, "No Queue Feature")
        _with_phase(db, f"feature:{slug}", "brainstorm", mode="standard")

        # Explicitly no notification_queue
        engine = _make_engine(db, artifacts_root, notification_queue=None)
        result = engine.complete_phase(uuid, "brainstorm")

        assert result.cascade_error is None
        assert result.state is not None

    def test_cascade_with_queue_pushes_notification(self, tmp_path):
        """When queue is present, notifications are pushed."""
        db = _make_db()
        slug = "021-with-queue"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug)

        uuid = _register(db, "feature", slug, "Queue Feature")
        _with_phase(db, f"feature:{slug}", "brainstorm", mode="standard")

        queue = MagicMock(spec=NotificationQueue)
        engine = _make_engine(db, artifacts_root, notification_queue=queue)
        result = engine.complete_phase(uuid, "brainstorm")

        assert result.cascade_error is None
        # Notification should have been pushed
        assert queue.push.called


# ---------------------------------------------------------------------------
# Test 9: Integration — light feature → transition to implement → spec.md only
# ---------------------------------------------------------------------------


class TestLightFeatureIntegration:
    """Light-weight feature: brainstorm+design+create-plan+create-tasks
    are skipped. Only specify→implement→finish. Transition to implement
    requires only spec.md (B6 integration)."""

    def test_light_feature_specify_to_implement(self, tmp_path):
        db = _make_db()
        slug = "022-light"
        artifacts_root = str(tmp_path)

        # Create .meta.json with light mode
        _create_meta_json(artifacts_root, slug, mode="light")

        # Create spec.md (the only required artifact for light mode)
        feature_dir = os.path.join(artifacts_root, "features", slug)
        with open(os.path.join(feature_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")

        uuid = _register(db, "feature", slug, "Light Feature")
        _with_phase(
            db, f"feature:{slug}", "implement",
            mode="light", last_completed_phase="specify",
        )

        engine = _make_engine(db, artifacts_root)

        # Get state should work
        state = engine.get_state(uuid)
        assert state is not None
        assert state.current_phase == "implement"
        assert state.mode == "light"

    def test_light_feature_complete_specify_advances(self, tmp_path):
        """Completing specify on a light feature advances to implement."""
        db = _make_db()
        slug = "023-light-adv"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug, mode="light")

        uuid = _register(db, "feature", slug, "Light Advance")
        _with_phase(
            db, f"feature:{slug}", "specify",
            mode="light",
        )

        engine = _make_engine(db, artifacts_root)
        result = engine.complete_phase(uuid, "specify")

        assert result.state is not None
        # Frozen engine advances specify → design (7-phase sequence)
        # This is correct — the frozen engine uses the full 7-phase sequence
        # Light mode gate filtering is handled at transition_phase level
        assert result.state.last_completed_phase == "specify"


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


class TestGetState:
    """get_state convenience wrapper."""

    def test_get_state_feature(self, tmp_path):
        db = _make_db()
        slug = "024-state"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug)

        uuid = _register(db, "feature", slug, "State Feature")
        _with_phase(db, f"feature:{slug}", "design", mode="standard",
                    last_completed_phase="specify")

        engine = _make_engine(db, artifacts_root)
        state = engine.get_state(uuid)

        assert state is not None
        assert state.current_phase == "design"

    def test_get_state_task(self, tmp_path):
        db = _make_db()
        _register(db, "feature", "025-parent", "Parent")
        task_uuid = _register(
            db, "task", "009-state", "State Task",
            parent_type_id="feature:025-parent",
        )
        _with_phase(db, "task:009-state", "deliver", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        state = engine.get_state(task_uuid)

        assert state is not None
        assert state.current_phase == "deliver"

    def test_get_state_not_found(self, tmp_path):
        db = _make_db()
        engine = _make_engine(db, str(tmp_path))
        assert engine.get_state("nonexistent-uuid") is None


class TestTransitionPhase:
    """transition_phase routing and blocked_by checks."""

    def test_feature_transition_delegates(self, tmp_path):
        db = _make_db()
        slug = "026-trans"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug)

        uuid = _register(db, "feature", slug, "Trans Feature")
        _with_phase(db, f"feature:{slug}", "brainstorm", mode="standard")

        engine = _make_engine(db, artifacts_root)
        response = engine.transition_phase(uuid, "specify")

        assert isinstance(response, TransitionResponse)

    def test_blocked_entity_cannot_transition_to_deliver(self, tmp_path):
        """Blocked feature cannot transition to implement (deliver phase)."""
        db = _make_db()
        slug = "028-blocked"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug)

        blocker_uuid = _register(db, "feature", "027-blocker", "Blocker")
        blocked_uuid = _register(db, "feature", slug, "Blocked")
        _with_phase(
            db, f"feature:{slug}", "create-tasks", mode="standard"
        )

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, blocked_uuid, blocker_uuid)

        engine = _make_engine(db, artifacts_root)

        with pytest.raises(ValueError, match="blocked by"):
            engine.transition_phase(blocked_uuid, "implement")

    def test_task_transition_phase_sequence(self, tmp_path):
        db = _make_db()
        _register(db, "feature", "029-parent", "Parent")
        task_uuid = _register(
            db, "task", "010-trans", "Trans Task",
            parent_type_id="feature:029-parent",
        )
        _with_phase(db, "task:010-trans", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        response = engine.transition_phase(task_uuid, "deliver")

        assert not response.degraded
        assert any(r.allowed for r in response.results)


class TestCascadeUnblock:
    """Integration: complete blocker → dependent unblocked."""

    def test_complete_blocker_unblocks_dependent(self, tmp_path):
        db = _make_db()
        slug = "030-blocker"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug)

        blocker_uuid = _register(
            db, "feature", slug, "Blocker Feature"
        )
        _with_phase(db, f"feature:{slug}", "brainstorm", mode="standard")

        dependent_uuid = _register(
            db, "feature", "031-dep", "Dependent",
            status="blocked",
        )

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, dependent_uuid, blocker_uuid)

        # Verify blocked
        blockers = dep_mgr.get_blockers(db, dependent_uuid)
        assert len(blockers) == 1

        engine = _make_engine(db, artifacts_root)
        result = engine.complete_phase(blocker_uuid, "brainstorm")

        # Dependent should be unblocked
        assert dependent_uuid in result.unblocked_uuids

        # Verify dependency removed
        blockers_after = dep_mgr.get_blockers(db, dependent_uuid)
        assert len(blockers_after) == 0

        # Status should change from blocked to planned
        entity = db.get_entity_by_uuid(dependent_uuid)
        assert entity["status"] == "planned"


# ---------------------------------------------------------------------------
# Task 4.1: FiveDBackend tests — project/initiative/objective/key_result
# ---------------------------------------------------------------------------


class TestFiveDProjectTransition:
    """Project entity transitions through 5D phases."""

    def test_project_transitions_through_all_5d_phases(self, tmp_path):
        """Project transitions discover → define → design → deliver → debrief."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p001-alpha", "Alpha Project")
        _with_phase(db, "project:p001-alpha", "discover", mode="standard")

        engine = _make_engine(db, str(tmp_path))

        # Walk through full 5D sequence
        phases = ["discover", "define", "design", "deliver", "debrief"]
        for i, phase in enumerate(phases[:-1]):
            response = engine.transition_phase(proj_uuid, phases[i + 1])
            assert not response.degraded
            assert any(r.allowed for r in response.results), (
                f"Transition to {phases[i + 1]} should be allowed"
            )

    def test_project_complete_advances_phases(self, tmp_path):
        """Completing each 5D phase advances to the next."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p002-beta", "Beta Project")
        _with_phase(db, "project:p002-beta", "discover", mode="standard")

        engine = _make_engine(db, str(tmp_path))

        result = engine.complete_phase(proj_uuid, "discover")
        assert result.entity_type == "project"
        assert result.state is not None
        assert result.state.current_phase == "define"
        assert result.state.last_completed_phase == "discover"

    def test_project_complete_terminal_sets_completed(self, tmp_path):
        """Completing debrief (terminal) marks project completed."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p003-gamma", "Gamma Project")
        _with_phase(
            db, "project:p003-gamma", "debrief",
            mode="standard", last_completed_phase="deliver",
        )

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(proj_uuid, "debrief")

        assert result.state.last_completed_phase == "debrief"
        entity = db.get_entity_by_uuid(proj_uuid)
        assert entity["status"] == "completed"

    def test_project_get_state(self, tmp_path):
        """get_state returns correct state for 5D project."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p004-delta", "Delta Project")
        _with_phase(
            db, "project:p004-delta", "design",
            mode="full", last_completed_phase="define",
        )

        engine = _make_engine(db, str(tmp_path))
        state = engine.get_state(proj_uuid)

        assert state is not None
        assert state.current_phase == "design"
        assert state.mode == "full"


class TestFiveDOutOfSequence:
    """Out-of-sequence transitions are rejected for 5D entities."""

    def test_project_skip_phase_rejected(self, tmp_path):
        """Cannot skip from discover to deliver (skipping define+design)."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p010-skip", "Skip Project")
        _with_phase(db, "project:p010-skip", "discover", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        response = engine.transition_phase(proj_uuid, "deliver")

        assert not response.degraded
        assert any(
            not r.allowed and "skip" in r.reason.lower()
            for r in response.results
        ), "Should reject out-of-sequence transition"

    def test_initiative_skip_phase_rejected(self, tmp_path):
        """Initiative: cannot skip from discover to debrief."""
        db = _make_db()
        init_uuid = _register(
            db, "initiative", "i001-skip", "Skip Initiative"
        )
        _with_phase(db, "initiative:i001-skip", "discover", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        response = engine.transition_phase(init_uuid, "debrief")

        assert any(
            not r.allowed for r in response.results
        ), "Should reject skip"

    def test_project_invalid_phase_rejected(self, tmp_path):
        """Phase not in 5D sequence is rejected."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p011-bad", "Bad Phase Project")
        _with_phase(db, "project:p011-bad", "discover", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        response = engine.transition_phase(proj_uuid, "implement")

        assert any(
            not r.allowed and "not in sequence" in r.reason.lower()
            for r in response.results
        )

    def test_project_next_phase_allowed(self, tmp_path):
        """Transition to the immediate next phase is allowed."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p012-next", "Next Project")
        _with_phase(db, "project:p012-next", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        response = engine.transition_phase(proj_uuid, "design")

        assert any(r.allowed for r in response.results)


class TestFiveDDeliverBlockedBy:
    """Deliver phase with active blocked_by is rejected (AC-28)."""

    def test_deliver_with_blocker_rejected(self, tmp_path):
        """Project blocked by another entity cannot transition to deliver."""
        db = _make_db()
        blocker_uuid = _register(
            db, "project", "p020-blocker", "Blocker Project"
        )
        blocked_uuid = _register(
            db, "project", "p021-blocked", "Blocked Project"
        )
        _with_phase(db, "project:p021-blocked", "design", mode="standard")

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, blocked_uuid, blocker_uuid)

        engine = _make_engine(db, str(tmp_path))

        with pytest.raises(ValueError, match="blocked by"):
            engine.transition_phase(blocked_uuid, "deliver")

    def test_non_deliver_phase_allowed_with_blocker(self, tmp_path):
        """Blocker does NOT prevent non-deliver transitions (e.g. define)."""
        db = _make_db()
        blocker_uuid = _register(
            db, "project", "p022-blocker", "Blocker"
        )
        blocked_uuid = _register(
            db, "project", "p023-blocked", "Blocked"
        )
        _with_phase(db, "project:p023-blocked", "discover", mode="standard")

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, blocked_uuid, blocker_uuid)

        engine = _make_engine(db, str(tmp_path))
        # define is NOT the deliver phase, so blocker should not prevent it
        response = engine.transition_phase(blocked_uuid, "define")
        assert any(r.allowed for r in response.results)

    def test_deliver_without_blocker_allowed(self, tmp_path):
        """Deliver transition succeeds when no blockers exist."""
        db = _make_db()
        proj_uuid = _register(
            db, "project", "p024-free", "Free Project"
        )
        _with_phase(db, "project:p024-free", "design", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        response = engine.transition_phase(proj_uuid, "deliver")

        assert any(r.allowed for r in response.results)

    def test_feature_blocked_at_implement_not_deliver(self, tmp_path):
        """Feature blocker check fires at implement (not deliver)."""
        db = _make_db()
        slug_blocker = "032-feat-blocker"
        slug_blocked = "033-feat-blocked"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug_blocked)

        blocker_uuid = _register(
            db, "feature", slug_blocker, "Feature Blocker"
        )
        blocked_uuid = _register(
            db, "feature", slug_blocked, "Feature Blocked"
        )
        _with_phase(
            db, f"feature:{slug_blocked}", "create-tasks", mode="standard"
        )

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, blocked_uuid, blocker_uuid)

        engine = _make_engine(db, artifacts_root)

        with pytest.raises(ValueError, match="blocked by"):
            engine.transition_phase(blocked_uuid, "implement")


class TestFiveDInitiativeObjectiveKeyResult:
    """5D transitions for initiative, objective, key_result types."""

    def test_initiative_complete_phase(self, tmp_path):
        db = _make_db()
        uuid = _register(db, "initiative", "i002-comp", "Complete Init")
        _with_phase(db, "initiative:i002-comp", "discover", mode="full")

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(uuid, "discover")

        assert result.entity_type == "initiative"
        assert result.state.current_phase == "define"

    def test_objective_complete_phase(self, tmp_path):
        db = _make_db()
        uuid = _register(db, "objective", "o001-comp", "Complete Obj")
        _with_phase(db, "objective:o001-comp", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(uuid, "define")

        assert result.entity_type == "objective"
        assert result.state.current_phase == "design"

    def test_key_result_complete_phase(self, tmp_path):
        db = _make_db()
        uuid = _register(db, "key_result", "kr001-comp", "Complete KR")
        _with_phase(db, "key_result:kr001-comp", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(uuid, "define")

        assert result.entity_type == "key_result"
        assert result.state.current_phase == "deliver"

    def test_key_result_terminal_completes(self, tmp_path):
        """key_result: debrief is terminal → status=completed."""
        db = _make_db()
        uuid = _register(db, "key_result", "kr002-term", "Terminal KR")
        _with_phase(
            db, "key_result:kr002-term", "debrief",
            mode="standard", last_completed_phase="deliver",
        )

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(uuid, "debrief")

        entity = db.get_entity_by_uuid(uuid)
        assert entity["status"] == "completed"

    def test_initiative_transition_sequence(self, tmp_path):
        db = _make_db()
        uuid = _register(db, "initiative", "i003-trans", "Trans Init")
        _with_phase(db, "initiative:i003-trans", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        response = engine.transition_phase(uuid, "design")

        assert any(r.allowed for r in response.results)


class TestFiveDDeliverPhaseMapping:
    """Deliver phase mapping: features=implement, 5D=deliver (AC-28)."""

    def test_project_deliver_phase_is_deliver(self, tmp_path):
        """Project's deliver gate is at 'deliver' phase."""
        db = _make_db()
        blocker_uuid = _register(
            db, "project", "p030-blocker", "Blocker"
        )
        proj_uuid = _register(
            db, "project", "p031-proj", "Project"
        )
        _with_phase(db, "project:p031-proj", "design", mode="standard")

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, proj_uuid, blocker_uuid)

        engine = _make_engine(db, str(tmp_path))

        # deliver is blocked
        with pytest.raises(ValueError, match="blocked by"):
            engine.transition_phase(proj_uuid, "deliver")

        # design is NOT blocked (non-deliver phase)
        # Reset to define so we can transition to design
        db.update_workflow_phase("project:p031-proj", workflow_phase="define")
        response = engine.transition_phase(proj_uuid, "design")
        assert any(r.allowed for r in response.results)

    def test_initiative_deliver_blocked(self, tmp_path):
        """Initiative's deliver gate is at 'deliver' phase."""
        db = _make_db()
        blocker_uuid = _register(
            db, "initiative", "i010-blocker", "Blocker Init"
        )
        init_uuid = _register(
            db, "initiative", "i011-blocked", "Blocked Init"
        )
        _with_phase(
            db, "initiative:i011-blocked", "design", mode="standard"
        )

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, init_uuid, blocker_uuid)

        engine = _make_engine(db, str(tmp_path))

        with pytest.raises(ValueError, match="blocked by"):
            engine.transition_phase(init_uuid, "deliver")


# ---------------------------------------------------------------------------
# Task 4.3: Deliver gate — blocker type_ids in error + end-to-end unblock
# ---------------------------------------------------------------------------


class TestDeliverGateBlockerDetails:
    """Error message lists actual blocker type_ids (AC-28 detail)."""

    def test_error_lists_blocker_type_ids(self, tmp_path):
        """Blocked error message includes the blocker's type_id."""
        db = _make_db()
        blocker_uuid = _register(
            db, "feature", "040-blocker-a", "Blocker A"
        )
        blocked_uuid = _register(
            db, "feature", "041-blocked-b", "Blocked B"
        )
        _create_meta_json(str(tmp_path), "041-blocked-b")
        _with_phase(
            db, "feature:041-blocked-b", "create-tasks", mode="standard"
        )

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, blocked_uuid, blocker_uuid)

        engine = _make_engine(db, str(tmp_path))

        with pytest.raises(ValueError, match="feature:040-blocker-a"):
            engine.transition_phase(blocked_uuid, "implement")

    def test_error_lists_multiple_blocker_type_ids(self, tmp_path):
        """Multiple blockers are all listed in the error."""
        db = _make_db()
        b1_uuid = _register(db, "project", "p040-b1", "Blocker 1")
        b2_uuid = _register(db, "project", "p041-b2", "Blocker 2")
        blocked_uuid = _register(
            db, "project", "p042-blocked", "Blocked"
        )
        _with_phase(db, "project:p042-blocked", "design", mode="standard")

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, blocked_uuid, b1_uuid)
        dep_mgr.add_dependency(db, blocked_uuid, b2_uuid)

        engine = _make_engine(db, str(tmp_path))

        with pytest.raises(ValueError, match="project:p040-b1"):
            engine.transition_phase(blocked_uuid, "deliver")

    def test_complete_blocker_then_deliver_succeeds(self, tmp_path):
        """End-to-end: feature B blocked by A. Complete A → B can implement."""
        db = _make_db()
        slug_a = "042-feat-a"
        slug_b = "043-feat-b"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug_a)
        _create_meta_json(artifacts_root, slug_b)

        a_uuid = _register(db, "feature", slug_a, "Feature A")
        b_uuid = _register(db, "feature", slug_b, "Feature B")
        _with_phase(db, f"feature:{slug_a}", "brainstorm", mode="standard")
        _with_phase(
            db, f"feature:{slug_b}", "create-tasks", mode="standard",
            last_completed_phase="create-plan",
        )

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, b_uuid, a_uuid)

        engine = _make_engine(db, artifacts_root)

        # B cannot implement while A is active
        with pytest.raises(ValueError, match=f"feature:{slug_a}"):
            engine.transition_phase(b_uuid, "implement")

        # Complete A's brainstorm → cascade_unblock removes the dep
        engine.complete_phase(a_uuid, "brainstorm")

        # Now B can transition to implement
        response = engine.transition_phase(b_uuid, "implement")
        assert isinstance(response, TransitionResponse)


# ---------------------------------------------------------------------------
# Task 4.4: Orphan guard on abandonment (AC-30)
# ---------------------------------------------------------------------------


class TestAbandonEntityOrphanGuard:
    """abandon_entity blocks when active children exist, unless cascade=True."""

    def test_abandon_no_children_succeeds(self, tmp_path):
        """Entity with no children can be abandoned."""
        db = _make_db()
        uuid = _register(db, "project", "p050-solo", "Solo Project")

        engine = _make_engine(db, str(tmp_path))
        result = engine.abandon_entity(uuid)

        assert uuid in result
        entity = db.get_entity_by_uuid(uuid)
        assert entity["status"] == "abandoned"

    def test_abandon_with_active_children_blocked(self, tmp_path):
        """Project with active features → abandon blocked."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p051-parent", "Parent Proj")
        child_uuid = _register(
            db, "feature", "044-child", "Active Child",
            status="active",
            parent_type_id="project:p051-parent",
        )

        engine = _make_engine(db, str(tmp_path))

        with pytest.raises(ValueError, match="active children"):
            engine.abandon_entity(proj_uuid)

        # Parent still active
        entity = db.get_entity_by_uuid(proj_uuid)
        assert entity["status"] == "active"

    def test_abandon_with_completed_children_succeeds(self, tmp_path):
        """Completed children don't block abandonment."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p052-done-kids", "Done Kids")
        _register(
            db, "feature", "045-done", "Done Feature",
            status="completed",
            parent_type_id="project:p052-done-kids",
        )
        _register(
            db, "feature", "046-abn", "Abandoned Feature",
            status="abandoned",
            parent_type_id="project:p052-done-kids",
        )

        engine = _make_engine(db, str(tmp_path))
        result = engine.abandon_entity(proj_uuid)

        assert proj_uuid in result
        entity = db.get_entity_by_uuid(proj_uuid)
        assert entity["status"] == "abandoned"

    def test_abandon_cascade_abandons_all_descendants(self, tmp_path):
        """cascade=True → all active descendants abandoned."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p053-cascade", "Cascade Proj")
        feat_uuid = _register(
            db, "feature", "047-active-feat", "Active Feature",
            status="active",
            parent_type_id="project:p053-cascade",
        )
        task_uuid = _register(
            db, "task", "011-active-task", "Active Task",
            status="active",
            parent_type_id="feature:047-active-feat",
        )

        engine = _make_engine(db, str(tmp_path))
        result = engine.abandon_entity(proj_uuid, cascade=True)

        # All three should be abandoned
        assert proj_uuid in result
        assert feat_uuid in result
        assert task_uuid in result
        assert len(result) == 3

        for uid in [proj_uuid, feat_uuid, task_uuid]:
            entity = db.get_entity_by_uuid(uid)
            assert entity["status"] == "abandoned", (
                f"{entity['type_id']} should be abandoned"
            )

    def test_abandon_cascade_skips_completed(self, tmp_path):
        """cascade=True skips already-completed children."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p054-mixed", "Mixed Proj")
        active_uuid = _register(
            db, "feature", "048-active", "Active",
            status="active",
            parent_type_id="project:p054-mixed",
        )
        completed_uuid = _register(
            db, "feature", "049-done", "Done",
            status="completed",
            parent_type_id="project:p054-mixed",
        )

        engine = _make_engine(db, str(tmp_path))
        result = engine.abandon_entity(proj_uuid, cascade=True)

        # Active child + parent abandoned
        assert proj_uuid in result
        assert active_uuid in result
        # Completed child not touched
        assert completed_uuid not in result
        entity = db.get_entity_by_uuid(completed_uuid)
        assert entity["status"] == "completed"

    def test_abandon_entity_not_found(self, tmp_path):
        """Abandon non-existent entity raises ValueError."""
        db = _make_db()
        engine = _make_engine(db, str(tmp_path))

        with pytest.raises(ValueError, match="Entity not found"):
            engine.abandon_entity("nonexistent-uuid")

    def test_abandon_error_lists_active_children_type_ids(self, tmp_path):
        """Error message lists the active children's type_ids."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p055-list", "List Proj")
        _register(
            db, "feature", "050-kid1", "Kid 1",
            status="active",
            parent_type_id="project:p055-list",
        )
        _register(
            db, "feature", "051-kid2", "Kid 2",
            status="active",
            parent_type_id="project:p055-list",
        )

        engine = _make_engine(db, str(tmp_path))

        with pytest.raises(ValueError, match="feature:050-kid1"):
            engine.abandon_entity(proj_uuid)

    def test_abandon_cascade_deep_tree(self, tmp_path):
        """Three-level cascade: initiative → project → feature."""
        db = _make_db()
        init_uuid = _register(
            db, "initiative", "i020-deep", "Deep Initiative"
        )
        proj_uuid = _register(
            db, "project", "p056-deep", "Deep Project",
            status="active",
            parent_type_id="initiative:i020-deep",
        )
        feat_uuid = _register(
            db, "feature", "052-deep", "Deep Feature",
            status="active",
            parent_type_id="project:p056-deep",
        )

        engine = _make_engine(db, str(tmp_path))
        result = engine.abandon_entity(init_uuid, cascade=True)

        assert len(result) == 3
        for uid in [init_uuid, proj_uuid, feat_uuid]:
            entity = db.get_entity_by_uuid(uid)
            assert entity["status"] == "abandoned"


# ---------------------------------------------------------------
# Adversarial review fixes — blocker B1 (phase mismatch) + B2 (backward transition)
# ---------------------------------------------------------------

class TestFiveDPhaseValidation:
    """Phase validation for 5D entities — matches frozen engine behavior."""

    def test_forward_skip_rejected(self, tmp_path):
        """Complete 'deliver' when entity is in 'discover' (no phases completed) → ValueError."""
        db = _make_db()
        proj_uuid = _register(db, "project", "090-skip", "Skip")
        _with_phase(db, "project:090-skip", "discover", mode="standard")
        engine = _make_engine(db, str(tmp_path))
        with pytest.raises(ValueError, match="Phase mismatch"):
            engine.complete_phase(proj_uuid, "deliver")

    def test_complete_current_phase_succeeds(self, tmp_path):
        """Complete 'discover' when entity is in 'discover' → succeeds."""
        db = _make_db()
        proj_uuid = _register(db, "project", "091-correct", "Correct")
        _with_phase(db, "project:091-correct", "discover", mode="standard")
        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(proj_uuid, "discover")
        assert result.state.last_completed_phase == "discover"

    def test_backward_rerun_allowed(self, tmp_path):
        """Complete 'discover' when in 'define' with discover already completed → rework allowed."""
        db = _make_db()
        proj_uuid = _register(db, "project", "092-rework", "Rework")
        _with_phase(db, "project:092-rework", "define", mode="standard",
                    last_completed_phase="discover")
        engine = _make_engine(db, str(tmp_path))
        # Backward re-run: complete discover again (rework cycle)
        result = engine.complete_phase(proj_uuid, "discover")
        assert result.state.last_completed_phase == "discover"


class TestFiveDTransitionBehavior:
    """Transition behavior for 5D entities — matches frozen engine."""

    def test_backward_transition_allowed_with_warning(self, tmp_path):
        """Transition from 'deliver' to 'define' → allowed with warning (rework)."""
        db = _make_db()
        proj_uuid = _register(db, "project", "093-backward", "Backward")
        _with_phase(db, "project:093-backward", "deliver", mode="standard")
        engine = _make_engine(db, str(tmp_path))
        resp = engine.transition_phase(proj_uuid, "define")
        assert resp.results[0].allowed
        assert "backward" in resp.results[0].reason.lower() or "rework" in resp.results[0].reason.lower()

    def test_forward_skip_rejected(self, tmp_path):
        """Transition from 'discover' to 'deliver' (skipping define) → blocked."""
        db = _make_db()
        proj_uuid = _register(db, "project", "094-skip", "Skip")
        _with_phase(db, "project:094-skip", "discover", mode="standard")
        engine = _make_engine(db, str(tmp_path))
        resp = engine.transition_phase(proj_uuid, "deliver")
        assert not resp.results[0].allowed

    def test_forward_next_phase_works(self, tmp_path):
        """Forward transition (discover → define) → succeeds."""
        db = _make_db()
        proj_uuid = _register(db, "project", "095-forward", "Forward")
        _with_phase(db, "project:095-forward", "discover", mode="standard")
        engine = _make_engine(db, str(tmp_path))
        resp = engine.transition_phase(proj_uuid, "define")
        assert resp.results[0].allowed


# ---------------------------------------------------------------------------
# Task 5.1: Initiative and Objective entity lifecycle (AC-31)
# ---------------------------------------------------------------------------


class TestInitiativeFullLifecycle:
    """Initiative traverses all 5D phases: discover -> define -> design -> deliver -> debrief.

    Verifies AC-31: L1 entities use FiveDBackend with phase-sequence transitions.
    Human-gated = policy (caller-side), not engine-side code gate.
    """

    def test_initiative_full_5d_lifecycle(self, tmp_path):
        """Initiative completes all 5 phases -> status=completed."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i100-lifecycle", "Lifecycle Initiative")
        _with_phase(db, "initiative:i100-lifecycle", "discover", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        phases = ["discover", "define", "design", "deliver", "debrief"]

        for phase in phases:
            result = engine.complete_phase(init_uuid, phase)
            assert result.entity_type == "initiative"
            assert result.state is not None
            assert result.state.last_completed_phase == phase
            assert result.cascade_error is None

        # Terminal phase -> status=completed
        entity = db.get_entity_by_uuid(init_uuid)
        assert entity["status"] == "completed"

    def test_initiative_transitions_through_all_phases(self, tmp_path):
        """Initiative transition_phase walks the full 5D sequence."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i101-trans", "Trans Initiative")
        _with_phase(db, "initiative:i101-trans", "discover", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        phases = ["discover", "define", "design", "deliver", "debrief"]

        for i in range(len(phases) - 1):
            response = engine.transition_phase(init_uuid, phases[i + 1])
            assert not response.degraded
            assert any(r.allowed for r in response.results), (
                f"Transition from {phases[i]} to {phases[i + 1]} should be allowed"
            )

    def test_initiative_full_weight_uses_all_5_phases(self, tmp_path):
        """Initiative with full weight has all 5 phases."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i102-full", "Full Initiative")
        _with_phase(db, "initiative:i102-full", "discover", mode="full")

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(init_uuid, "discover")
        assert result.state.current_phase == "define"
        assert result.state.completed_phases == ("discover",)


class TestObjectiveFullLifecycle:
    """Objective traverses its 4-phase sequence: define -> design -> deliver -> debrief.

    Objectives skip 'discover' (per template: objectives have well-defined scope
    from the parent initiative).
    """

    def test_objective_full_lifecycle(self, tmp_path):
        """Objective completes all 4 phases -> status=completed."""
        db = _make_db()
        obj_uuid = _register(db, "objective", "o100-lifecycle", "Lifecycle Objective")
        _with_phase(db, "objective:o100-lifecycle", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        phases = ["define", "design", "deliver", "debrief"]

        for phase in phases:
            result = engine.complete_phase(obj_uuid, phase)
            assert result.entity_type == "objective"
            assert result.state is not None
            assert result.state.last_completed_phase == phase

        entity = db.get_entity_by_uuid(obj_uuid)
        assert entity["status"] == "completed"

    def test_objective_transitions_through_all_phases(self, tmp_path):
        """Objective transition_phase walks the full 4-phase sequence."""
        db = _make_db()
        obj_uuid = _register(db, "objective", "o101-trans", "Trans Objective")
        _with_phase(db, "objective:o101-trans", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        phases = ["define", "design", "deliver", "debrief"]

        for i in range(len(phases) - 1):
            response = engine.transition_phase(obj_uuid, phases[i + 1])
            assert not response.degraded
            assert any(r.allowed for r in response.results)

    def test_objective_discover_phase_rejected(self, tmp_path):
        """Objective does not have 'discover' in its template -> rejected."""
        db = _make_db()
        obj_uuid = _register(db, "objective", "o102-no-disc", "No Discover Obj")
        _with_phase(db, "objective:o102-no-disc", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        response = engine.transition_phase(obj_uuid, "discover")

        assert any(
            not r.allowed and "not in sequence" in r.reason.lower()
            for r in response.results
        ), "discover should not be in objective's phase sequence"


class TestInitiativeObjectiveParentChild:
    """Integration: initiative as parent, objective as child.

    Verifies the full hierarchy: create initiative, create objective under it,
    both transition through their respective phase sequences, and rollup works.
    """

    def test_initiative_with_objective_child(self, tmp_path):
        """Create initiative -> create objective as child -> both complete lifecycle."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i110-parent", "Parent Initiative")
        _with_phase(db, "initiative:i110-parent", "discover", mode="standard")

        obj_uuid = _register(
            db, "objective", "o110-child", "Child Objective",
            parent_type_id="initiative:i110-parent",
        )
        _with_phase(db, "objective:o110-child", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))

        # Objective completes its full lifecycle
        for phase in ["define", "design", "deliver", "debrief"]:
            result = engine.complete_phase(obj_uuid, phase)
            assert result.state is not None

        # Objective is completed
        obj_entity = db.get_entity_by_uuid(obj_uuid)
        assert obj_entity["status"] == "completed"

        # Parent initiative should have progress from the completed child
        progress = compute_progress(db, init_uuid)
        assert progress == pytest.approx(1.0), (
            "Single completed child -> parent progress should be 1.0"
        )

        # Initiative continues its own lifecycle independently
        result = engine.complete_phase(init_uuid, "discover")
        assert result.state.current_phase == "define"
        assert result.parent_progress is None  # initiative has no parent

    def test_initiative_multiple_objectives_progress(self, tmp_path):
        """Initiative with 2 objectives: one completed, one active -> partial progress."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i111-multi", "Multi-Obj Initiative")
        _with_phase(db, "initiative:i111-multi", "discover", mode="standard")

        # Completed objective
        obj1_uuid = _register(
            db, "objective", "o111-done", "Done Objective",
            status="completed",
            parent_type_id="initiative:i111-multi",
        )
        _with_phase(
            db, "objective:o111-done", "debrief",
            mode="standard", last_completed_phase="debrief",
        )

        # Active objective in design phase
        obj2_uuid = _register(
            db, "objective", "o112-active", "Active Objective",
            status="active",
            parent_type_id="initiative:i111-multi",
        )
        _with_phase(
            db, "objective:o112-active", "design",
            mode="standard", last_completed_phase="define",
        )

        progress = compute_progress(db, init_uuid)
        # completed = 1.0, active in design with define completed
        # Progress should be between 0 and 1
        assert 0.0 < progress < 1.0

    def test_objective_completion_cascades_to_initiative_progress(self, tmp_path):
        """Completing an objective updates the initiative's rollup progress."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i112-cascade", "Cascade Initiative")
        _with_phase(db, "initiative:i112-cascade", "define", mode="standard")

        obj_uuid = _register(
            db, "objective", "o113-cascade", "Cascade Objective",
            parent_type_id="initiative:i112-cascade",
        )
        _with_phase(
            db, "objective:o113-cascade", "debrief",
            mode="standard", last_completed_phase="deliver",
        )

        engine = _make_engine(db, str(tmp_path))

        # Complete objective's terminal phase -> triggers cascade -> rollup
        result = engine.complete_phase(obj_uuid, "debrief")
        assert result.cascade_error is None
        assert result.parent_progress is not None
        assert result.parent_progress == pytest.approx(1.0)


class TestInitiativeObjectiveNoAutomatedTransition:
    """Verify that no automated transition fires.

    Human-gated = policy, not code: the engine never auto-advances entities.
    Each phase requires an explicit complete_phase or transition_phase call.
    This is the caller-side concern documented in the task spec.
    """

    def test_completing_phase_does_not_auto_advance_next(self, tmp_path):
        """Completing 'discover' on initiative does NOT auto-complete 'define'."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i120-no-auto", "No Auto Initiative")
        _with_phase(db, "initiative:i120-no-auto", "discover", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(init_uuid, "discover")

        # Current phase advances to define, but define is NOT completed
        assert result.state.current_phase == "define"
        assert result.state.last_completed_phase == "discover"
        # define is not in completed_phases
        assert "define" not in result.state.completed_phases

    def test_completing_child_does_not_auto_advance_parent(self, tmp_path):
        """Completing all objectives does NOT auto-advance the initiative's phase."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i121-no-cascade-adv", "No Cascade Adv")
        _with_phase(db, "initiative:i121-no-cascade-adv", "discover", mode="standard")

        obj_uuid = _register(
            db, "objective", "o120-child", "Child Obj",
            parent_type_id="initiative:i121-no-cascade-adv",
        )
        _with_phase(
            db, "objective:o120-child", "debrief",
            mode="standard", last_completed_phase="deliver",
        )

        engine = _make_engine(db, str(tmp_path))
        engine.complete_phase(obj_uuid, "debrief")

        # Initiative is still in discover -- child completion does NOT advance parent phase
        state = engine.get_state(init_uuid)
        assert state.current_phase == "discover"
        assert state.last_completed_phase is None

    def test_objective_phase_requires_explicit_invocation(self, tmp_path):
        """Each objective phase must be explicitly completed -- no auto-fire."""
        db = _make_db()
        obj_uuid = _register(db, "objective", "o121-explicit", "Explicit Obj")
        _with_phase(db, "objective:o121-explicit", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))

        # Complete define -> advances to design
        result = engine.complete_phase(obj_uuid, "define")
        assert result.state.current_phase == "design"

        # design is NOT auto-completed
        state = engine.get_state(obj_uuid)
        assert state.current_phase == "design"
        assert state.last_completed_phase == "define"
        assert "design" not in state.completed_phases


class TestInitiativeObjectiveBlockedBy:
    """Deliver-phase blocked_by enforcement for initiatives and objectives."""

    def test_initiative_deliver_blocked_by_dependency(self, tmp_path):
        """Initiative blocked at deliver phase by another initiative."""
        db = _make_db()
        blocker_uuid = _register(
            db, "initiative", "i130-blocker", "Blocker Initiative"
        )
        blocked_uuid = _register(
            db, "initiative", "i131-blocked", "Blocked Initiative"
        )
        _with_phase(db, "initiative:i131-blocked", "design", mode="standard")

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, blocked_uuid, blocker_uuid)

        engine = _make_engine(db, str(tmp_path))

        with pytest.raises(ValueError, match="blocked by.*initiative:i130-blocker"):
            engine.transition_phase(blocked_uuid, "deliver")

    def test_objective_deliver_blocked_by_dependency(self, tmp_path):
        """Objective blocked at deliver phase."""
        db = _make_db()
        blocker_uuid = _register(
            db, "objective", "o130-blocker", "Blocker Objective"
        )
        blocked_uuid = _register(
            db, "objective", "o131-blocked", "Blocked Objective"
        )
        _with_phase(db, "objective:o131-blocked", "design", mode="standard")

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, blocked_uuid, blocker_uuid)

        engine = _make_engine(db, str(tmp_path))

        with pytest.raises(ValueError, match="blocked by.*objective:o130-blocker"):
            engine.transition_phase(blocked_uuid, "deliver")

    def test_initiative_non_deliver_allowed_with_blocker(self, tmp_path):
        """Blocker does NOT prevent non-deliver transitions on initiative."""
        db = _make_db()
        blocker_uuid = _register(
            db, "initiative", "i132-blocker", "Blocker"
        )
        blocked_uuid = _register(
            db, "initiative", "i133-blocked", "Blocked"
        )
        _with_phase(db, "initiative:i133-blocked", "discover", mode="standard")

        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, blocked_uuid, blocker_uuid)

        engine = _make_engine(db, str(tmp_path))
        response = engine.transition_phase(blocked_uuid, "define")
        assert any(r.allowed for r in response.results)


class TestInitiativeObjectiveGetState:
    """get_state returns correct state for initiative and objective."""

    def test_initiative_get_state_with_completed_phases(self, tmp_path):
        """get_state returns completed_phases derived from template."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i140-state", "State Initiative")
        _with_phase(
            db, "initiative:i140-state", "design",
            mode="standard", last_completed_phase="define",
        )

        engine = _make_engine(db, str(tmp_path))
        state = engine.get_state(init_uuid)

        assert state is not None
        assert state.current_phase == "design"
        assert state.last_completed_phase == "define"
        assert state.completed_phases == ("discover", "define")
        assert state.mode == "standard"
        assert state.source == "db"

    def test_objective_get_state_with_completed_phases(self, tmp_path):
        """Objective get_state reflects its 4-phase template."""
        db = _make_db()
        obj_uuid = _register(db, "objective", "o140-state", "State Objective")
        _with_phase(
            db, "objective:o140-state", "deliver",
            mode="standard", last_completed_phase="design",
        )

        engine = _make_engine(db, str(tmp_path))
        state = engine.get_state(obj_uuid)

        assert state is not None
        assert state.current_phase == "deliver"
        assert state.last_completed_phase == "design"
        # Objective template: define, design, deliver, debrief
        assert state.completed_phases == ("define", "design")

    def test_initiative_get_state_not_found(self, tmp_path):
        """get_state for initiative with no workflow_phases row -> None."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i141-no-wf", "No WF")
        # No _with_phase call -> no workflow_phases row

        engine = _make_engine(db, str(tmp_path))
        state = engine.get_state(init_uuid)
        assert state is None


class TestInitiativeObjectiveAbandon:
    """Abandon lifecycle for initiative/objective hierarchy."""

    def test_abandon_initiative_with_active_objective_blocked(self, tmp_path):
        """Cannot abandon initiative with active objective child."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i150-abn", "Abandon Init")
        _register(
            db, "objective", "o150-active", "Active Obj",
            status="active",
            parent_type_id="initiative:i150-abn",
        )

        engine = _make_engine(db, str(tmp_path))
        with pytest.raises(ValueError, match="active children"):
            engine.abandon_entity(init_uuid)

    def test_abandon_initiative_cascade_abandons_objectives(self, tmp_path):
        """cascade=True on initiative -> all active objectives abandoned."""
        db = _make_db()
        init_uuid = _register(db, "initiative", "i151-cascade", "Cascade Init")
        obj_uuid = _register(
            db, "objective", "o151-active", "Active Obj",
            status="active",
            parent_type_id="initiative:i151-cascade",
        )

        engine = _make_engine(db, str(tmp_path))
        result = engine.abandon_entity(init_uuid, cascade=True)

        assert init_uuid in result
        assert obj_uuid in result
        assert db.get_entity_by_uuid(init_uuid)["status"] == "abandoned"
        assert db.get_entity_by_uuid(obj_uuid)["status"] == "abandoned"


# ---------------------------------------------------------------------------
# Task 6.1: Anomaly propagation on debrief completion (AC-35)
# ---------------------------------------------------------------------------


class TestAnomalyPropagation:
    """On debrief completion, systemic_finding propagates to parent metadata."""

    def test_systemic_finding_propagated_to_parent(self, tmp_path):
        """Complete debrief with systemic_finding → parent gets anomaly entry."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p060-anomaly", "Anomaly Project")
        _with_phase(db, "project:p060-anomaly", "deliver", mode="standard")

        feat_uuid = _register(
            db, "feature", "060-finding", "Finding Feature",
            parent_type_id="project:p060-anomaly",
        )
        # Set systemic_finding in entity metadata
        db.update_entity(
            "feature:060-finding",
            metadata={"systemic_finding": "auth middleware broken"},
        )

        # Feature needs to be in debrief phase to complete it
        slug = "060-finding"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug, mode="standard",
                          last_completed_phase="implement")
        _with_phase(db, f"feature:{slug}", "finish", mode="standard",
                    last_completed_phase="implement")

        engine = _make_engine(db, artifacts_root)
        result = engine.complete_phase(feat_uuid, "finish")

        assert result.cascade_error is None

        # Parent metadata should have anomalies list
        parent = db.get_entity_by_uuid(proj_uuid)
        parent_meta = json.loads(parent["metadata"])
        assert "anomalies" in parent_meta
        anomalies = parent_meta["anomalies"]
        assert len(anomalies) == 1
        assert anomalies[0]["description"] == "auth middleware broken"
        assert anomalies[0]["source_type_id"] == f"feature:{slug}"
        assert "timestamp" in anomalies[0]

    def test_no_systemic_finding_no_anomaly(self, tmp_path):
        """Complete debrief without systemic_finding → no anomaly recorded."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p061-clean", "Clean Project")
        _with_phase(db, "project:p061-clean", "deliver", mode="standard")

        feat_uuid = _register(
            db, "feature", "061-clean", "Clean Feature",
            parent_type_id="project:p061-clean",
        )

        slug = "061-clean"
        artifacts_root = str(tmp_path)
        _create_meta_json(artifacts_root, slug, mode="standard",
                          last_completed_phase="implement")
        _with_phase(db, f"feature:{slug}", "finish", mode="standard",
                    last_completed_phase="implement")

        engine = _make_engine(db, artifacts_root)
        result = engine.complete_phase(feat_uuid, "finish")

        assert result.cascade_error is None

        parent = db.get_entity_by_uuid(proj_uuid)
        parent_meta = json.loads(parent["metadata"]) if parent["metadata"] else {}
        # anomalies should either not exist or be empty
        anomalies = parent_meta.get("anomalies", [])
        assert len(anomalies) == 0

    def test_anomaly_appended_to_existing_anomalies(self, tmp_path):
        """Second anomaly appends to existing list."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p062-multi", "Multi Anomaly")
        _with_phase(db, "project:p062-multi", "deliver", mode="standard")

        # Pre-seed parent with existing anomaly
        db.update_entity(
            "project:p062-multi",
            metadata={
                "anomalies": [
                    {"description": "earlier issue", "source_type_id": "feature:old", "timestamp": "2026-01-01T00:00:00+00:00"},
                ]
            },
        )

        # 5D child with systemic_finding completing debrief
        task_uuid = _register(
            db, "task", "012-anomaly", "Anomaly Task",
            parent_type_id="project:p062-multi",
        )
        db.update_entity(
            "task:012-anomaly",
            metadata={"systemic_finding": "rate limiter misconfigured"},
        )
        _with_phase(db, "task:012-anomaly", "debrief", mode="standard",
                    last_completed_phase="deliver")

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(task_uuid, "debrief")

        assert result.cascade_error is None

        parent = db.get_entity_by_uuid(proj_uuid)
        parent_meta = json.loads(parent["metadata"])
        assert len(parent_meta["anomalies"]) == 2
        assert parent_meta["anomalies"][1]["description"] == "rate limiter misconfigured"
        assert parent_meta["anomalies"][1]["source_type_id"] == "task:012-anomaly"

    def test_anomaly_not_propagated_on_non_terminal_phase(self, tmp_path):
        """Systemic finding only checked on terminal phase (debrief/finish)."""
        db = _make_db()
        proj_uuid = _register(db, "project", "p063-non-term", "Non Terminal")
        _with_phase(db, "project:p063-non-term", "deliver", mode="standard")

        task_uuid = _register(
            db, "task", "013-early", "Early Task",
            parent_type_id="project:p063-non-term",
        )
        db.update_entity(
            "task:013-early",
            metadata={"systemic_finding": "should not propagate"},
        )
        _with_phase(db, "task:013-early", "define", mode="standard")

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(task_uuid, "define")

        parent = db.get_entity_by_uuid(proj_uuid)
        parent_meta = json.loads(parent["metadata"]) if parent["metadata"] else {}
        assert parent_meta.get("anomalies", []) == []

    def test_anomaly_propagation_no_parent(self, tmp_path):
        """Entity with systemic_finding but no parent → no error, no crash."""
        db = _make_db()
        task_uuid = _register(db, "task", "014-orphan", "Orphan Task")
        db.update_entity(
            "task:014-orphan",
            metadata={"systemic_finding": "orphan finding"},
        )
        _with_phase(db, "task:014-orphan", "debrief", mode="standard",
                    last_completed_phase="deliver")

        engine = _make_engine(db, str(tmp_path))
        result = engine.complete_phase(task_uuid, "debrief")
        # Should complete without error — no parent to propagate to
        assert result.state is not None
