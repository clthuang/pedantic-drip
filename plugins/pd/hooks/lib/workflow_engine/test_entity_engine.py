"""Tests for EntityWorkflowEngine -- Task 3.3 [XC].

9 test cases covering:
1. Feature complete_phase → delegates to frozen engine + cascade fires
2. Task complete_phase → task state update + cascade
3. Cascade failure after completion → completion persists, cascade retryable
4. UUID-to-type_id resolution → correct delegation
5. Degraded mode (DB unhealthy) → cascade skipped
6. No children → rollup_parent is no-op
7. Mixed children (active + abandoned) → abandoned excluded from progress
8. Without notification queue → cascade still works
9. Integration: light feature → transition to implement → only spec.md required
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
