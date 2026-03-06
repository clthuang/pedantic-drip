"""Tests for WorkflowStateEngine -- Phases 1-8."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from entity_registry.database import EntityDatabase
from transition_gate import PHASE_SEQUENCE
from transition_gate.constants import COMMAND_PHASES, HARD_PREREQUISITES

from transition_gate.models import Severity, TransitionResult

from workflow_engine import FeatureWorkflowState, WorkflowStateEngine
from workflow_engine.models import TransitionResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> EntityDatabase:
    """Create an in-memory EntityDatabase."""
    return EntityDatabase(":memory:")


def _register_feature(
    db: EntityDatabase,
    slug: str = "008-test-feature",
    status: str | None = "active",
) -> str:
    """Register a feature entity and return the type_id."""
    type_id = f"feature:{slug}"
    db.register_entity(
        entity_type="feature",
        entity_id=slug,
        name=f"Test Feature {slug}",
        status=status,
    )
    return type_id


def _create_meta_json(
    tmp_path,
    slug: str = "008-test-feature",
    *,
    status: str = "active",
    mode: str | None = "standard",
    last_completed_phase: str | None = None,
) -> None:
    """Create a .meta.json file in the expected location."""
    feature_dir = tmp_path / "features" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": slug.split("-", 1)[0],
        "slug": slug,
        "status": status,
        "mode": mode,
        "lastCompletedPhase": last_completed_phase,
        "phases": {},
    }
    (feature_dir / ".meta.json").write_text(json.dumps(meta))


def _setup_engine(
    tmp_path,
    slug: str = "008-test-feature",
    *,
    status: str = "active",
    workflow_phase: str | None = None,
    last_completed_phase: str | None = None,
    mode: str | None = "standard",
    create_wp: bool = True,
) -> tuple[WorkflowStateEngine, EntityDatabase, str]:
    """Full setup: DB + entity + workflow_phase row + engine."""
    db = _make_db()
    type_id = _register_feature(db, slug, status=status)
    if create_wp:
        db.create_workflow_phase(
            type_id,
            workflow_phase=workflow_phase,
            last_completed_phase=last_completed_phase,
            mode=mode,
        )
    engine = WorkflowStateEngine(db, str(tmp_path))
    return engine, db, type_id


# ===========================================================================
# Phase 1: Models
# ===========================================================================


class TestModels:
    """Task 1.2/1.3: FeatureWorkflowState frozen dataclass tests."""

    def test_frozen_attribute_raises(self) -> None:
        state = FeatureWorkflowState(
            feature_type_id="feature:001-test",
            current_phase="specify",
            last_completed_phase="brainstorm",
            completed_phases=("brainstorm",),
            mode="standard",
            source="db",
        )
        with pytest.raises(FrozenInstanceError):
            state.current_phase = "design"  # type: ignore[misc]

    def test_completed_phases_tuple_immutable(self) -> None:
        state = FeatureWorkflowState(
            feature_type_id="feature:001-test",
            current_phase="specify",
            last_completed_phase="brainstorm",
            completed_phases=("brainstorm",),
            mode="standard",
            source="db",
        )
        # Tuple is immutable -- cannot append or modify
        assert isinstance(state.completed_phases, tuple)
        with pytest.raises(AttributeError):
            state.completed_phases.append("specify")  # type: ignore[attr-defined]


# ===========================================================================
# Phase 2: Private Helpers
# ===========================================================================


class TestHelpers:
    """Tasks 2.1-2.8: Private helper tests."""

    # -- _extract_slug (2.1/2.2) --

    def test_extract_slug_valid(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        assert engine._extract_slug("feature:008-foo") == "008-foo"

    def test_extract_slug_missing_colon(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        with pytest.raises(ValueError, match="missing ':'"):
            engine._extract_slug("feature-008-foo")

    def test_extract_slug_empty(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        with pytest.raises(ValueError, match="empty slug"):
            engine._extract_slug("feature:")

    # -- _derive_completed_phases (2.3/2.4) --

    def test_derive_completed_phases_none(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        assert engine._derive_completed_phases(None) == ()

    def test_derive_completed_phases_specify(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        result = engine._derive_completed_phases("specify")
        assert result == ("brainstorm", "specify")

    def test_derive_completed_phases_finish(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        result = engine._derive_completed_phases("finish")
        expected = tuple(p.value for p in PHASE_SEQUENCE)
        assert result == expected
        assert len(result) == 7

    def test_derive_completed_phases_unknown(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        with pytest.raises(ValueError, match="Unknown phase"):
            engine._derive_completed_phases("nonexistent")

    # -- _next_phase_value (2.5/2.6) --

    def test_next_phase_value_specify_to_design(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        assert engine._next_phase_value("specify") == "design"

    def test_next_phase_value_finish_returns_none(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        assert engine._next_phase_value("finish") is None

    def test_next_phase_value_unknown(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        with pytest.raises(ValueError, match="Unknown phase"):
            engine._next_phase_value("nonexistent")

    # -- _get_existing_artifacts (2.7/2.8) --

    def test_hard_prerequisites_import(self) -> None:
        """Verify HARD_PREREQUISITES is importable and is a dict."""
        assert isinstance(HARD_PREREQUISITES, dict)

    def test_get_existing_artifacts_some_present(self, tmp_path) -> None:
        feature_dir = tmp_path / "features" / "008-foo"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec")
        (feature_dir / "design.md").write_text("# Design")

        engine = WorkflowStateEngine(_make_db(), str(tmp_path))
        result = engine._get_existing_artifacts("008-foo")
        assert "spec.md" in result
        assert "design.md" in result
        assert "plan.md" not in result

    def test_get_existing_artifacts_none_present(self, tmp_path) -> None:
        feature_dir = tmp_path / "features" / "008-foo"
        feature_dir.mkdir(parents=True)

        engine = WorkflowStateEngine(_make_db(), str(tmp_path))
        result = engine._get_existing_artifacts("008-foo")
        assert result == []

    def test_get_existing_artifacts_all_present(self, tmp_path) -> None:
        feature_dir = tmp_path / "features" / "008-foo"
        feature_dir.mkdir(parents=True)

        # Create all artifacts from HARD_PREREQUISITES
        all_artifacts: set[str] = set()
        for artifacts_list in HARD_PREREQUISITES.values():
            all_artifacts.update(artifacts_list)

        for name in all_artifacts:
            (feature_dir / name).write_text(f"# {name}")

        engine = WorkflowStateEngine(_make_db(), str(tmp_path))
        result = engine._get_existing_artifacts("008-foo")
        assert set(result) == all_artifacts

    # -- Guard IDs in gate evaluation (2.9) --

    def test_guard_ids_in_gate_results(self, tmp_path) -> None:
        """Guard IDs G-18, G-08, G-23, G-22 appear in gate evaluation results."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        state = engine.get_state(type_id)
        assert state is not None
        results = engine._evaluate_gates(
            state, "design", [], yolo_active=False
        )
        guard_ids = {r.guard_id for r in results}
        assert "G-18" in guard_ids
        assert "G-08" in guard_ids
        assert "G-23" in guard_ids
        assert "G-22" in guard_ids


# ===========================================================================
# Phase 3: State Reading + Hydration
# ===========================================================================


class TestHydration:
    """Tasks 3.1/3.2: _hydrate_from_meta_json tests."""

    def test_hydrate_active_status(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-active")
        _create_meta_json(
            tmp_path,
            "008-active",
            status="active",
            last_completed_phase="design",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.source == "meta_json"
        assert state.current_phase == "create-plan"  # next after design
        assert state.last_completed_phase == "design"
        assert state.completed_phases == ("brainstorm", "specify", "design")

    def test_hydrate_completed_status(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-done")
        _create_meta_json(
            tmp_path,
            "008-done",
            status="completed",
            last_completed_phase="implement",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.current_phase == "finish"
        assert state.source == "meta_json"

    def test_hydrate_planned_status(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-planned")
        _create_meta_json(
            tmp_path,
            "008-planned",
            status="planned",
            last_completed_phase="specify",  # stale data
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.current_phase is None
        assert state.last_completed_phase is None
        assert state.completed_phases == ()

    def test_hydrate_unknown_status(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-abandoned")
        _create_meta_json(
            tmp_path,
            "008-abandoned",
            status="abandoned",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.current_phase is None
        assert state.last_completed_phase is None

    def test_hydrate_missing_entity(self, tmp_path) -> None:
        db = _make_db()
        _create_meta_json(tmp_path, "008-noentity")
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json("feature:008-noentity")
        assert state is None

    def test_hydrate_missing_meta_json(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-nometa")
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)
        assert state is None

    def test_hydrate_malformed_meta_json(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-bad")
        _create_meta_json(
            tmp_path,
            "008-bad",
            status="active",
            last_completed_phase="invalid-phase",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)
        assert state is None

    def test_hydrate_concurrent_race(self, tmp_path) -> None:
        """ValueError 'already exists' -> fallback to get_workflow_phase."""
        db = _make_db()
        type_id = _register_feature(db, "008-race")
        _create_meta_json(
            tmp_path,
            "008-race",
            status="active",
            last_completed_phase="specify",
        )

        # Pre-create the workflow phase to simulate a race
        db.create_workflow_phase(
            type_id,
            workflow_phase="design",
            last_completed_phase="specify",
            mode="standard",
        )

        engine = WorkflowStateEngine(db, str(tmp_path))
        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.source == "meta_json"
        # Should fallback to get and get the existing row's data
        assert state.current_phase == "design"

    def test_hydrate_active_finished_edge(self, tmp_path) -> None:
        """Active + lastCompletedPhase='finish' -> workflow_phase='finish'."""
        db = _make_db()
        type_id = _register_feature(db, "008-edge")
        _create_meta_json(
            tmp_path,
            "008-edge",
            status="active",
            last_completed_phase="finish",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.current_phase == "finish"

    def test_hydrate_active_no_completed_phase(self, tmp_path) -> None:
        """Active + lastCompletedPhase=None -> workflow_phase=PHASE_SEQUENCE[0]."""
        db = _make_db()
        type_id = _register_feature(db, "008-new")
        _create_meta_json(
            tmp_path,
            "008-new",
            status="active",
            last_completed_phase=None,
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.current_phase == PHASE_SEQUENCE[0].value  # "brainstorm"
        assert state.last_completed_phase is None
        assert state.completed_phases == ()


class TestGetState:
    """Tasks 3.3/3.4: get_state tests."""

    def test_get_state_db_row_exists(self, tmp_path) -> None:
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )

        state = engine.get_state(type_id)

        assert state is not None
        assert state.source == "db"
        assert state.current_phase == "design"
        assert state.last_completed_phase == "specify"
        assert state.completed_phases == ("brainstorm", "specify")

    def test_get_state_db_missing_meta_exists(self, tmp_path) -> None:
        """SC-4 + SC-9: fallback to .meta.json, source='meta_json'."""
        db = _make_db()
        type_id = _register_feature(db, "008-fallback")
        _create_meta_json(
            tmp_path,
            "008-fallback",
            status="active",
            last_completed_phase="design",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine.get_state(type_id)

        assert state is not None
        assert state.source == "meta_json"
        assert state.current_phase == "create-plan"

    def test_get_state_both_missing_returns_none(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-empty")
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine.get_state(type_id)
        assert state is None

    def test_get_state_missing_feature_returns_none(self, tmp_path) -> None:
        """Entity not registered, no .meta.json -> returns None."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine.get_state("feature:999-nonexistent")
        assert state is None


# ===========================================================================
# Phase 4: Gate Evaluation
# ===========================================================================


class TestGateEvaluation:
    """Tasks 4.1/4.2: _evaluate_gates tests."""

    def test_gate_order_all_applicable(self, tmp_path) -> None:
        """All 4 gates run when last_completed_phase and current_phase are set."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        state = engine.get_state(type_id)
        assert state is not None

        results = engine._evaluate_gates(
            state, "create-plan", ["spec.md", "design.md"], yolo_active=False
        )

        # Should have 4 results: backward, hard, soft, validate
        assert len(results) == 4
        guard_ids = [r.guard_id for r in results]
        assert guard_ids[0] == "G-18"  # backward
        assert guard_ids[1] == "G-08"  # hard prereq
        assert guard_ids[2] == "G-23"  # soft prereq
        assert guard_ids[3] == "G-22"  # validate

    def test_skip_backward_when_last_completed_none(self, tmp_path) -> None:
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="brainstorm",
            last_completed_phase=None,
        )
        state = engine.get_state(type_id)
        assert state is not None

        results = engine._evaluate_gates(
            state, "brainstorm", [], yolo_active=False
        )

        # backward gate skipped, validate gate NOT skipped (current_phase is set)
        guard_ids = [r.guard_id for r in results]
        assert "G-18" not in guard_ids
        assert "G-08" in guard_ids
        assert "G-23" in guard_ids
        assert "G-22" in guard_ids

    def test_skip_validate_when_current_phase_none(self, tmp_path) -> None:
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase=None,
            last_completed_phase="specify",
        )
        state = engine.get_state(type_id)
        assert state is not None

        results = engine._evaluate_gates(
            state, "design", ["spec.md"], yolo_active=False
        )

        guard_ids = [r.guard_id for r in results]
        assert "G-22" not in guard_ids  # validate skipped
        assert "G-18" in guard_ids  # backward runs
        assert "G-08" in guard_ids
        assert "G-23" in guard_ids

    def test_yolo_overrides_soft_gates(self, tmp_path) -> None:
        """G-18/G-22/G-23 have yolo_behavior=auto_select, should get overridden."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        state = engine.get_state(type_id)
        assert state is not None

        results = engine._evaluate_gates(
            state, "create-plan", ["spec.md", "design.md"], yolo_active=True
        )

        # G-18, G-23, G-22 should be overridden (auto_select -> warn override)
        # G-08 has yolo_behavior=unchanged -> runs normally
        for r in results:
            if r.guard_id in ("G-18", "G-23", "G-22"):
                assert "YOLO" in r.reason or r.allowed is True
            if r.guard_id == "G-08":
                assert "YOLO" not in r.reason

    def test_yolo_does_not_override_hard_gate(self, tmp_path) -> None:
        """G-08 has yolo_behavior=unchanged, should NOT be overridden."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        state = engine.get_state(type_id)
        assert state is not None

        # Missing design.md -- hard prereq should fail even with YOLO
        results = engine._evaluate_gates(
            state, "create-plan", ["spec.md"], yolo_active=True
        )

        hard_result = [r for r in results if r.guard_id == "G-08"][0]
        assert hard_result.allowed is False
        assert "YOLO" not in hard_result.reason


# ===========================================================================
# Phase 5: Transition + Complete
# ===========================================================================


class TestTransitionPhase:
    """Tasks 5.1/5.2: transition_phase tests."""

    def test_forward_transition_success(self, tmp_path) -> None:
        """SC-1 partial: forward transition updates DB."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # Create required artifacts for design
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        results = engine.transition_phase(type_id, "design")

        assert all(r.allowed for r in results)
        # Verify DB was updated
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["workflow_phase"] == "design"

    def test_blocked_missing_prerequisites(self, tmp_path) -> None:
        """SC-2: missing hard prereqs blocks transition."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # No spec.md created -- design requires it

        results = engine.transition_phase(type_id, "design")

        blocked = [r for r in results if not r.allowed]
        assert len(blocked) > 0
        assert any(r.guard_id == "G-08" for r in blocked)
        # DB should NOT be updated
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["workflow_phase"] == "specify"

    def test_backward_transition_warning(self, tmp_path) -> None:
        """SC-3: backward transition warns but allows."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="design",
        )

        results = engine.transition_phase(type_id, "specify")

        # Should have a G-18 warning but all allowed
        g18 = [r for r in results if r.guard_id == "G-18"]
        assert len(g18) == 1
        assert g18[0].allowed is True
        assert g18[0].severity.value == "warn"

    def test_yolo_mode_passthrough(self, tmp_path) -> None:
        """SC-8: YOLO overrides soft gates."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        results = engine.transition_phase(type_id, "design", yolo_active=True)

        # With YOLO, soft gates should be overridden
        yolo_results = [r for r in results if "YOLO" in r.reason]
        assert len(yolo_results) > 0

    def test_missing_feature_raises_valueerror(self, tmp_path) -> None:
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        with pytest.raises(ValueError, match="Feature not found"):
            engine.transition_phase("feature:999-nonexistent", "specify")


class TestCompletePhase:
    """Tasks 5.3/5.4: complete_phase tests."""

    def test_normal_completion_advances(self, tmp_path) -> None:
        """SC-5: completing specify -> workflow_phase becomes design."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )

        state = engine.complete_phase(type_id, "specify")

        assert state.current_phase == "design"
        assert state.last_completed_phase == "specify"
        assert "specify" in state.completed_phases

    def test_terminal_phase_finish(self, tmp_path) -> None:
        """TD-8: finishing 'finish' keeps workflow_phase='finish', not None."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="finish",
            last_completed_phase="implement",
        )

        state = engine.complete_phase(type_id, "finish")

        assert state.current_phase == "finish"
        assert state.last_completed_phase == "finish"

    def test_backward_rerun_resets(self, tmp_path) -> None:
        """TD-6: backward re-run resets progress."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="create-plan",
            last_completed_phase="design",
        )

        state = engine.complete_phase(type_id, "specify")

        assert state.last_completed_phase == "specify"
        assert state.current_phase == "design"
        assert state.completed_phases == ("brainstorm", "specify")

    def test_phase_mismatch_raises_valueerror(self, tmp_path) -> None:
        """Phase does not match current and is not backward."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )

        with pytest.raises(ValueError, match="Phase mismatch"):
            engine.complete_phase(type_id, "design")

    def test_missing_feature_raises_valueerror(self, tmp_path) -> None:
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        with pytest.raises(ValueError, match="Feature not found"):
            engine.complete_phase("feature:999-nonexistent", "specify")

    def test_no_active_phase_raises_valueerror(self, tmp_path) -> None:
        """current_phase=None -> cannot complete."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase=None,
            last_completed_phase=None,
        )

        with pytest.raises(ValueError, match="no active phase"):
            engine.complete_phase(type_id, "specify")

    def test_phase_mismatch_no_last_completed(self, tmp_path) -> None:
        """phase != current_phase AND last_completed_phase=None -> ValueError."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="brainstorm",
            last_completed_phase=None,
        )

        with pytest.raises(ValueError, match="no phases completed yet"):
            engine.complete_phase(type_id, "specify")


# ===========================================================================
# Phase 6: Query + Validate
# ===========================================================================


class TestValidatePrerequisites:
    """Tasks 6.1/6.2: validate_prerequisites tests."""

    def test_returns_same_results_as_transition(self, tmp_path) -> None:
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        validate_results = engine.validate_prerequisites(type_id, "design")
        transition_results = engine.transition_phase(type_id, "design")

        # Same gate evaluation logic -- same results
        assert len(validate_results) == len(transition_results)
        for v, t in zip(validate_results, transition_results):
            assert v.guard_id == t.guard_id
            assert v.allowed == t.allowed

    def test_no_db_write(self, tmp_path) -> None:
        """SC-6: validate does not update workflow_phase."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        engine.validate_prerequisites(type_id, "design")

        # workflow_phase should still be "specify"
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["workflow_phase"] == "specify"

    def test_missing_feature_raises_valueerror(self, tmp_path) -> None:
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        with pytest.raises(ValueError, match="Feature not found"):
            engine.validate_prerequisites("feature:999-nonexistent", "design")


class TestBatchQueries:
    """Tasks 6.3-6.6: list_by_phase and list_by_status tests."""

    # -- list_by_phase (6.3/6.4) --

    def test_list_by_phase_matches(self, tmp_path) -> None:
        db = _make_db()
        # Create 3 features in different phases
        for i, phase in enumerate(["design", "design", "implement"]):
            slug = f"00{i}-feat"
            tid = _register_feature(db, slug)
            db.create_workflow_phase(tid, workflow_phase=phase)

        engine = WorkflowStateEngine(db, str(tmp_path))
        results = engine.list_by_phase("design")

        assert len(results) == 2
        assert all(r.current_phase == "design" for r in results)
        assert all(r.source == "db" for r in results)

    def test_list_by_phase_empty(self, tmp_path) -> None:
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        results = engine.list_by_phase("design")
        assert results == []

    # -- list_by_status (6.5/6.6) --

    def test_list_by_status_matches(self, tmp_path) -> None:
        db = _make_db()
        tid1 = _register_feature(db, "001-active", status="active")
        db.create_workflow_phase(tid1, workflow_phase="design")
        tid2 = _register_feature(db, "002-active", status="active")
        db.create_workflow_phase(tid2, workflow_phase="specify")
        _register_feature(db, "003-completed", status="completed")

        engine = WorkflowStateEngine(db, str(tmp_path))
        results = engine.list_by_status("active")

        assert len(results) == 2
        type_ids = {r.feature_type_id for r in results}
        assert tid1 in type_ids
        assert tid2 in type_ids

    def test_list_by_status_none_excluded(self, tmp_path) -> None:
        """Entities with status=None should not match any status query."""
        db = _make_db()
        _register_feature(db, "001-nostat", status=None)

        engine = WorkflowStateEngine(db, str(tmp_path))
        results = engine.list_by_status("active")

        assert results == []

    def test_list_by_status_no_workflow_row(self, tmp_path) -> None:
        """SC-7: features without workflow_phases row included with current_phase=None."""
        db = _make_db()
        tid = _register_feature(db, "001-nowp", status="active")
        # Deliberately NOT creating workflow_phase row

        engine = WorkflowStateEngine(db, str(tmp_path))
        results = engine.list_by_status("active")

        assert len(results) == 1
        assert results[0].feature_type_id == tid
        assert results[0].current_phase is None
        assert results[0].completed_phases == ()
        assert results[0].source == "db"


# ===========================================================================
# Phase 7: Integration Tests
# ===========================================================================

# Artifact produced by each phase (used for creating files after completion).
_PHASE_ARTIFACT: dict[str, str] = {
    "specify": "spec.md",
    "design": "design.md",
    "create-plan": "plan.md",
    "create-tasks": "tasks.md",
}


class TestIntegration:
    """Tasks 7.1a/7.1b/7.2/7.3: Full lifecycle integration tests."""

    # -- Task 7.1a + 7.1b: Full lifecycle all 6 command phases (SC-1) --

    def test_full_lifecycle_all_6_phases(self, tmp_path) -> None:
        """SC-1: transition + complete through all 6 command phases.

        Setup (7.1a): EntityDatabase(:memory:), tmp_path for artifacts,
        register entity, create .meta.json, get_state -> source='meta_json'.

        Lifecycle (7.1b): For each command phase: transition_phase() +
        create required artifact + complete_phase().
        """
        # --- 7.1a: Setup ---
        db = EntityDatabase(":memory:")
        slug = "008-lifecycle-test"
        type_id = f"feature:{slug}"
        db.register_entity(
            entity_type="feature",
            entity_id=slug,
            name="Lifecycle Test Feature",
            status="active",
        )

        # Create .meta.json (active, no completed phases)
        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)
        meta = {
            "id": "008",
            "slug": slug,
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": None,
            "phases": {},
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        engine = WorkflowStateEngine(db, str(tmp_path))

        # get_state triggers hydration from .meta.json
        state = engine.get_state(type_id)
        assert state is not None
        assert state.source == "meta_json"
        assert state.current_phase == PHASE_SEQUENCE[0].value  # "brainstorm"
        assert state.last_completed_phase is None

        # --- 7.1b: Lifecycle through 6 command phases ---
        # First, complete brainstorm to move to specify
        # (brainstorm is not a command phase but needs to be completed)
        # The hydrated state has current_phase="brainstorm", so complete it
        state = engine.complete_phase(type_id, "brainstorm")
        assert state.current_phase == "specify"
        assert state.last_completed_phase == "brainstorm"

        # Now iterate through all 6 command phases
        command_phase_values = [p.value for p in COMMAND_PHASES]
        for phase_value in command_phase_values:
            # Transition into the phase
            results = engine.transition_phase(type_id, phase_value)
            assert all(r.allowed for r in results), (
                f"Transition to {phase_value} blocked: "
                + str([r for r in results if not r.allowed])
            )

            # Verify DB reflects the transition
            row = db.get_workflow_phase(type_id)
            assert row is not None
            assert row["workflow_phase"] == phase_value

            # Complete the phase
            state = engine.complete_phase(type_id, phase_value)

            # Create artifact produced by this phase (if any)
            artifact = _PHASE_ARTIFACT.get(phase_value)
            if artifact:
                (feature_dir / artifact).write_text(f"# {phase_value}")

        # Verify final state
        assert state.last_completed_phase == "finish"
        assert state.current_phase == "finish"  # TD-8: terminal stays "finish"
        assert state.completed_phases == tuple(p.value for p in PHASE_SEQUENCE)

    # -- Task 7.2: All 5 consumed gates exercised (SC-10) --

    def test_all_5_consumed_gates_exercised(self, tmp_path) -> None:
        """SC-10: Verify all 5 engine-consumed gates are invoked.

        Patches all 5 gate functions at engine module namespace with
        side_effect=original_fn so calls are tracked but execute normally.
        Runs a lifecycle with yolo_active=True on first transition to
        exercise check_yolo_override.
        """
        import workflow_engine.engine as engine_mod

        # Save originals
        orig_backward = engine_mod.check_backward_transition
        orig_hard = engine_mod.check_hard_prerequisites
        orig_soft = engine_mod.check_soft_prerequisites
        orig_validate = engine_mod.validate_transition
        orig_yolo = engine_mod.check_yolo_override

        db = EntityDatabase(":memory:")
        slug = "008-gate-coverage"
        type_id = f"feature:{slug}"
        db.register_entity(
            entity_type="feature",
            entity_id=slug,
            name="Gate Coverage Test",
            status="active",
        )

        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)

        with (
            patch.object(
                engine_mod,
                "check_backward_transition",
                side_effect=orig_backward,
            ) as mock_backward,
            patch.object(
                engine_mod,
                "check_hard_prerequisites",
                side_effect=orig_hard,
            ) as mock_hard,
            patch.object(
                engine_mod,
                "check_soft_prerequisites",
                side_effect=orig_soft,
            ) as mock_soft,
            patch.object(
                engine_mod,
                "validate_transition",
                side_effect=orig_validate,
            ) as mock_validate,
            patch.object(
                engine_mod,
                "check_yolo_override",
                side_effect=orig_yolo,
            ) as mock_yolo,
        ):
            engine = WorkflowStateEngine(db, str(tmp_path))

            # Set up initial state: brainstorm completed, in specify
            db.create_workflow_phase(
                type_id,
                workflow_phase="specify",
                last_completed_phase="brainstorm",
                mode="standard",
            )

            # First transition with yolo_active=True to exercise check_yolo_override
            results = engine.transition_phase(
                type_id, "specify", yolo_active=True
            )
            assert all(r.allowed for r in results)

            # Complete specify, create artifact
            engine.complete_phase(type_id, "specify")
            (feature_dir / "spec.md").write_text("# Spec")

            # Transition to design (normal, not YOLO) to exercise
            # backward + hard + soft + validate gates
            results = engine.transition_phase(type_id, "design")
            assert all(r.allowed for r in results)

            # Assert all 5 gates were called at least once
            assert mock_backward.call_count >= 1, (
                "check_backward_transition not called"
            )
            assert mock_hard.call_count >= 1, (
                "check_hard_prerequisites not called"
            )
            assert mock_soft.call_count >= 1, (
                "check_soft_prerequisites not called"
            )
            assert mock_validate.call_count >= 1, (
                "validate_transition not called"
            )
            assert mock_yolo.call_count >= 1, (
                "check_yolo_override not called"
            )

    # -- Task 7.3: Hydration then transition (SC-4 + SC-9) --

    def test_hydration_then_transition(self, tmp_path) -> None:
        """SC-4 + SC-9: .meta.json hydration then successful transition.

        Feature has .meta.json with lastCompletedPhase='design' but no DB
        row. get_state hydrates (source='meta_json'). Then transition to
        create-tasks succeeds using hydrated state.
        """
        db = EntityDatabase(":memory:")
        slug = "008-hydrate-transition"
        type_id = f"feature:{slug}"
        db.register_entity(
            entity_type="feature",
            entity_id=slug,
            name="Hydration Transition Test",
            status="active",
        )

        # Create .meta.json with design completed
        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)
        meta = {
            "id": "008",
            "slug": slug,
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "design",
            "phases": {},
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        # Create required artifacts for create-plan (next phase after design)
        (feature_dir / "spec.md").write_text("# Spec")
        (feature_dir / "design.md").write_text("# Design")

        engine = WorkflowStateEngine(db, str(tmp_path))

        # get_state should hydrate from .meta.json
        state = engine.get_state(type_id)
        assert state is not None
        assert state.source == "meta_json"
        assert state.current_phase == "create-plan"
        assert state.last_completed_phase == "design"

        # Transition should succeed using the hydrated state
        results = engine.transition_phase(type_id, "create-plan")
        assert all(r.allowed for r in results)

        # Verify the DB was updated
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["workflow_phase"] == "create-plan"

        # Now get_state should return source="db" (row exists)
        state = engine.get_state(type_id)
        assert state is not None
        assert state.source == "db"


# ===========================================================================
# Phase 8: Deepened Tests (test-deepener)
# ===========================================================================


class TestDeepenedBoundaryValues:
    """Boundary value and equivalence partitioning tests.

    Dimension 2: Tests boundary conditions not covered by existing TDD suite.
    """

    # -- _derive_completed_phases boundary: first phase (brainstorm) --

    def test_derive_completed_phases_first_phase_brainstorm(self) -> None:
        """BVA: first phase returns only that phase in completed tuple.

        Anticipate: Off-by-one in slicing could return empty or include next.
        derived_from: dimension:boundary_values (BVA min)
        """
        # Given the first phase in the sequence (brainstorm)
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        # When deriving completed phases for the first phase
        result = engine._derive_completed_phases("brainstorm")
        # Then only brainstorm is in the completed tuple
        assert result == ("brainstorm",)
        assert len(result) == 1

    # -- _extract_slug boundary: multiple colons --

    def test_extract_slug_multiple_colons_returns_full_slug(self) -> None:
        """BVA: slug with embedded colons preserves everything after first colon.

        Anticipate: Using split() without maxsplit=1 would drop parts after second colon.
        derived_from: dimension:boundary_values (string edge)
        """
        # Given a type_id with multiple colons
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        # When extracting the slug
        result = engine._extract_slug("feature:008-foo:bar:baz")
        # Then everything after first colon is returned
        assert result == "008-foo:bar:baz"

    # -- list_by_status empty results --

    def test_list_by_status_no_entities_returns_empty(self, tmp_path) -> None:
        """BVA: empty DB returns empty list for list_by_status.

        Anticipate: Missing guard on empty entity list could raise.
        derived_from: dimension:boundary_values (empty collection)
        """
        # Given an empty database
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        # When querying by status
        results = engine.list_by_status("active")
        # Then empty list is returned
        assert results == []

    # -- _get_existing_artifacts when feature dir doesn't exist --

    def test_get_existing_artifacts_missing_dir_returns_empty(self, tmp_path) -> None:
        """BVA: non-existent feature dir returns empty list (not error).

        Anticipate: os.path.exists on children of missing dir could raise or
        the sorted() comprehension could fail.
        derived_from: dimension:boundary_values (empty/missing)
        """
        # Given a feature slug whose directory does not exist
        engine = WorkflowStateEngine(_make_db(), str(tmp_path))
        # When checking artifacts
        result = engine._get_existing_artifacts("999-nonexistent")
        # Then empty list is returned (no error)
        assert result == []

    # -- _derive_completed_phases boundary: second phase (specify) --

    def test_derive_completed_phases_second_phase_includes_first(self) -> None:
        """BVA: second phase returns first two phases in order.

        Anticipate: Off-by-one in idx+1 slicing could miss first or include third.
        derived_from: dimension:boundary_values (BVA min+1)
        """
        # Given the second phase (specify)
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        # When deriving completed phases
        result = engine._derive_completed_phases("specify")
        # Then brainstorm and specify are included in order
        assert result == ("brainstorm", "specify")
        assert len(result) == 2

    # -- _next_phase_value boundary: second-to-last phase --

    def test_next_phase_value_second_to_last_returns_finish(self) -> None:
        """BVA: implement (second-to-last) returns finish (last).

        Anticipate: Off-by-one in idx >= len-1 check could wrongly return None.
        derived_from: dimension:boundary_values (BVA max-1)
        """
        # Given the second-to-last phase (implement)
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        # When getting next phase
        result = engine._next_phase_value("implement")
        # Then finish is returned
        assert result == "finish"

    # -- list_by_phase with many features, only one matches --

    def test_list_by_phase_single_match_among_many(self, tmp_path) -> None:
        """BVA: one-of-many match returns exactly one result.

        Anticipate: Filtering bug could return all or none.
        derived_from: dimension:boundary_values (collection single element)
        """
        # Given 5 features in various phases, only 1 in "implement"
        db = _make_db()
        for i, phase in enumerate(
            ["design", "design", "specify", "implement", "finish"]
        ):
            slug = f"00{i}-feat"
            tid = _register_feature(db, slug)
            db.create_workflow_phase(tid, workflow_phase=phase)

        engine = WorkflowStateEngine(db, str(tmp_path))
        # When listing by phase "implement"
        results = engine.list_by_phase("implement")
        # Then exactly one result
        assert len(results) == 1
        assert results[0].current_phase == "implement"


class TestDeepenedAdversarial:
    """Adversarial and negative testing.

    Dimension 3: Edge cases that could reveal hidden bugs.
    """

    def test_transition_to_unknown_phase_gate_returns_invalid(self, tmp_path) -> None:
        """Adversarial: transitioning to a nonexistent phase name.

        Anticipate: _evaluate_gates passes unknown phase to gate functions which
        should return INVALID results, not crash.
        derived_from: dimension:adversarial (wrong data type/logically invalid)
        """
        # Given a feature at specify
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # When transitioning to an invalid phase
        results = engine.transition_phase(type_id, "nonexistent-phase")
        # Then at least one gate blocks with INVALID guard_id
        blocked = [r for r in results if not r.allowed]
        assert len(blocked) > 0

    def test_complete_unknown_phase_raises_valueerror(self, tmp_path) -> None:
        """Adversarial: completing a nonexistent phase name raises ValueError.

        Anticipate: Missing validation on phase name could lead to index errors.
        derived_from: dimension:adversarial (wrong data)
        """
        # Given a feature at specify
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # When completing an unknown phase
        with pytest.raises(ValueError, match="Unknown phase"):
            engine.complete_phase(type_id, "nonexistent-phase")

    def test_hydrate_meta_json_with_corrupt_json(self, tmp_path) -> None:
        """Adversarial: .meta.json contains invalid JSON.

        Engine catches JSONDecodeError and returns None (graceful fallback).
        derived_from: dimension:adversarial (starve/corrupt input)
        """
        # Given corrupt .meta.json
        db = _make_db()
        type_id = _register_feature(db, "008-corrupt")
        feature_dir = tmp_path / "features" / "008-corrupt"
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text("{not valid json!!!")

        engine = WorkflowStateEngine(db, str(tmp_path))
        # When hydrating -- returns None for corrupt JSON
        state = engine._hydrate_from_meta_json(type_id)
        assert state is None

    def test_validate_prerequisites_unknown_phase_gates_handle(
        self, tmp_path
    ) -> None:
        """Adversarial: validate_prerequisites with unknown target phase.

        Anticipate: Gate functions should return blocking results, not crash.
        derived_from: dimension:adversarial (logically invalid but syntactically correct)
        """
        # Given a feature at design
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        # When validating unknown target
        results = engine.validate_prerequisites(type_id, "imaginary-phase")
        # Then should have blocking results (from G-08 at minimum)
        blocked = [r for r in results if not r.allowed]
        assert len(blocked) > 0

    def test_transition_to_same_phase_as_current(self, tmp_path) -> None:
        """Adversarial: transitioning to the same phase you're already in.

        Anticipate: Edge case -- this is technically backward (target_idx <= current_idx).
        G-22 should warn, G-18 should warn if last_completed covers it.
        derived_from: dimension:adversarial (zero/one/many -- zero distance)
        """
        # Given a feature at design with specify completed
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        # When transitioning to the same phase (design)
        results = engine.transition_phase(type_id, "design")
        # Then G-22 should warn about target not ahead
        g22 = [r for r in results if r.guard_id == "G-22"]
        assert len(g22) == 1
        assert g22[0].severity.value == "warn"


class TestDeepenedErrorPropagation:
    """Error propagation and failure mode tests.

    Dimension 4: Verify error messages are informative and errors propagate correctly.
    """

    def test_valueerror_message_contains_feature_type_id(self, tmp_path) -> None:
        """Error messages include the feature_type_id for debuggability.

        Anticipate: Generic "not found" without context makes debugging hard.
        derived_from: dimension:error_propagation (informative error messages)
        """
        # Given a nonexistent feature
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        # When calling transition_phase
        with pytest.raises(ValueError, match="999-nonexistent"):
            engine.transition_phase("feature:999-nonexistent", "specify")

    def test_complete_phase_mismatch_message_includes_both_phases(
        self, tmp_path
    ) -> None:
        """Phase mismatch error includes both current and requested phase.

        Anticipate: Error message missing context makes it unclear what failed.
        derived_from: dimension:error_propagation (informative error messages)
        """
        # Given a feature at specify
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # When completing wrong phase (design, which is ahead)
        with pytest.raises(ValueError) as exc_info:
            engine.complete_phase(type_id, "design")
        # Then error mentions both phases
        msg = str(exc_info.value)
        assert "design" in msg
        assert "specify" in msg

    def test_yolo_override_replaces_gate_result_in_place(self, tmp_path) -> None:
        """YOLO override replaces the gate result entirely (not appended).

        Anticipate: If YOLO result is appended alongside original, result count doubles.
        derived_from: dimension:error_propagation (YOLO override contract)
        """
        # Given a feature at design with specify completed
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        # When evaluating gates with and without YOLO
        state = engine.get_state(type_id)
        assert state is not None

        results_normal = engine._evaluate_gates(
            state, "create-plan", ["spec.md", "design.md"], yolo_active=False
        )
        results_yolo = engine._evaluate_gates(
            state, "create-plan", ["spec.md", "design.md"], yolo_active=True
        )
        # Then both produce the same number of results (replacement, not addition)
        assert len(results_normal) == len(results_yolo)

    def test_transition_blocked_does_not_update_db(self, tmp_path) -> None:
        """When any gate blocks, DB must NOT be updated.

        Anticipate: If DB update happens before gate check, state corrupts.
        derived_from: dimension:error_propagation (partial failure consistency)
        """
        # Given a feature at specify, missing required artifacts for design
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # When transition is blocked (no spec.md for design)
        results = engine.transition_phase(type_id, "design")
        assert any(not r.allowed for r in results)
        # Then DB still shows "specify"
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["workflow_phase"] == "specify"
        assert row["last_completed_phase"] == "brainstorm"


class TestDeepenedMutationMindset:
    """Mutation-targeted behavioral pinning tests.

    Dimension 5: Each test targets a specific mutation operator that could
    silently corrupt behavior if applied.
    """

    def test_complete_phase_updates_both_last_completed_and_workflow_phase(
        self, tmp_path
    ) -> None:
        """Pin: complete_phase must update BOTH last_completed AND workflow_phase.

        Mutation target: Deleting the last_completed_phase= kwarg in update call.
        derived_from: dimension:mutation_mindset (line deletion)
        """
        # Given a feature at specify with brainstorm completed
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # When completing specify
        state = engine.complete_phase(type_id, "specify")
        # Then BOTH fields updated
        assert state.last_completed_phase == "specify"  # last_completed updated
        assert state.current_phase == "design"  # workflow_phase advanced
        # Verify via raw DB too
        row = db.get_workflow_phase(type_id)
        assert row["last_completed_phase"] == "specify"
        assert row["workflow_phase"] == "design"

    def test_transition_phase_only_updates_workflow_phase_not_last_completed(
        self, tmp_path
    ) -> None:
        """Pin: transition_phase must ONLY update workflow_phase.

        Mutation target: Adding last_completed_phase= to the transition update call.
        derived_from: dimension:mutation_mindset (line deletion / return value mutation)
        """
        # Given a feature at specify with brainstorm completed
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        # When transitioning to design
        results = engine.transition_phase(type_id, "design")
        assert all(r.allowed for r in results)
        # Then workflow_phase changed but last_completed_phase did NOT change
        row = db.get_workflow_phase(type_id)
        assert row["workflow_phase"] == "design"
        assert row["last_completed_phase"] == "brainstorm"  # unchanged!

    def test_all_gates_must_pass_for_transition_not_any(self, tmp_path) -> None:
        """Pin: transition uses all() not any() for gate pass check.

        Mutation target: Swapping all(r.allowed ...) to any(r.allowed ...).
        If any() were used, transition would proceed even with one blocking gate.
        derived_from: dimension:mutation_mindset (logic inversion)
        """
        # Given a feature at specify, missing required artifact for design
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # No spec.md -> G-08 will block, but G-23 might pass
        results = engine.transition_phase(type_id, "design")

        # Verify at least one gate blocks
        blocked = [r for r in results if not r.allowed]
        assert len(blocked) >= 1
        # Verify at least one gate passes (so any() would wrongly pass)
        passed = [r for r in results if r.allowed]
        assert len(passed) >= 1
        # And transition did NOT happen (all() correctly blocked)
        row = db.get_workflow_phase(type_id)
        assert row["workflow_phase"] == "specify"  # unchanged

    def test_backward_skip_uses_last_completed_not_current_phase(
        self, tmp_path
    ) -> None:
        """Pin: backward gate skip condition checks last_completed_phase, not current_phase.

        Mutation target: Changing `state.last_completed_phase is not None` to
        `state.current_phase is not None` in _evaluate_gates.
        derived_from: dimension:mutation_mindset (boundary shift)
        """
        # Given a feature with current_phase set but last_completed_phase=None
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="brainstorm",
            last_completed_phase=None,
        )
        state = engine.get_state(type_id)
        assert state is not None
        assert state.current_phase == "brainstorm"  # current_phase IS set
        assert state.last_completed_phase is None  # last_completed IS None

        # When evaluating gates
        results = engine._evaluate_gates(
            state, "brainstorm", [], yolo_active=False
        )
        # Then backward gate (G-18) is SKIPPED (because last_completed is None)
        guard_ids = [r.guard_id for r in results]
        assert "G-18" not in guard_ids
        # If the mutation were applied (checking current_phase instead),
        # G-18 would be included because current_phase is set.

    def test_backward_rerun_boundary_uses_strict_greater_not_gte(
        self, tmp_path
    ) -> None:
        """Pin: backward re-run check uses `phase_idx > last_idx` not `>=`.

        Mutation target: Changing > to >= in complete_phase would cause completing
        the same phase as last_completed to raise ValueError instead of allowing it.
        derived_from: dimension:mutation_mindset (boundary shift >= vs >)
        """
        # Given a feature at design with design as last_completed
        # (i.e., re-running the current phase)
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="design",
        )
        # When completing design (same as last_completed, so phase_idx == last_idx)
        # This is NOT a mismatch, it's the current phase = design
        state = engine.complete_phase(type_id, "design")
        # Then it should succeed (not raise ValueError)
        assert state.last_completed_phase == "design"
        assert state.current_phase == "create-plan"

    def test_hydration_completed_status_overrides_last_completed_to_finish(
        self, tmp_path
    ) -> None:
        """Pin: completed status sets last_completed = last_completed or 'finish'.

        Mutation target: Removing the `or "finish"` fallback would leave
        last_completed as None for completed features without lastCompletedPhase.
        derived_from: dimension:mutation_mindset (return value mutation)
        """
        # Given a completed feature with NO lastCompletedPhase in meta
        db = _make_db()
        type_id = _register_feature(db, "008-comp-null")
        _create_meta_json(
            tmp_path,
            "008-comp-null",
            status="completed",
            last_completed_phase=None,  # absent
        )
        engine = WorkflowStateEngine(db, str(tmp_path))
        # When hydrating
        state = engine._hydrate_from_meta_json(type_id)
        # Then last_completed defaults to "finish" (not None)
        assert state is not None
        assert state.last_completed_phase == "finish"
        assert state.current_phase == "finish"
        assert len(state.completed_phases) == 7  # all phases

    def test_terminal_phase_next_returns_none_triggers_fallback(
        self, tmp_path
    ) -> None:
        """Pin: _next_phase_value('finish') returns None, complete_phase uses fallback.

        Mutation target: Removing `if next_phase is None: next_phase = phase`
        would set workflow_phase to None after finishing.
        derived_from: dimension:mutation_mindset (return value mutation + line deletion)
        """
        # Given a feature at finish
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="finish",
            last_completed_phase="implement",
        )
        # When completing finish
        state = engine.complete_phase(type_id, "finish")
        # Then workflow_phase stays "finish" (not None)
        assert state.current_phase == "finish"
        row = db.get_workflow_phase(type_id)
        assert row["workflow_phase"] == "finish"
        assert row["workflow_phase"] is not None

    def test_hydration_planned_status_clears_non_null_last_completed(
        self, tmp_path
    ) -> None:
        """Pin: planned status nullifies lastCompletedPhase even if non-null in meta.

        Mutation target: Removing `last_completed = None` for non-active/completed
        statuses would preserve stale lastCompletedPhase data.
        derived_from: dimension:mutation_mindset (line deletion)
        """
        # Given a planned feature with stale lastCompletedPhase
        db = _make_db()
        type_id = _register_feature(db, "008-stale-planned")
        _create_meta_json(
            tmp_path,
            "008-stale-planned",
            status="planned",
            last_completed_phase="design",  # stale data
        )
        engine = WorkflowStateEngine(db, str(tmp_path))
        # When hydrating
        state = engine._hydrate_from_meta_json(type_id)
        # Then planned status overrides to null
        assert state is not None
        assert state.last_completed_phase is None
        assert state.current_phase is None
        assert state.completed_phases == ()


class TestDeepenedPerformance:
    """Performance contract tests.

    Dimension 6: Basic timing assertions for engine operations.
    """

    def test_single_transition_under_50ms(self, tmp_path) -> None:
        """Performance: single transition should complete within 50ms.

        derived_from: dimension:performance_contracts (SLA: single operation)
        """
        import time

        # Given a feature ready for transition
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        # When timing a transition
        times = []
        for _ in range(10):
            # Reset state for each iteration
            db.update_workflow_phase(type_id, workflow_phase="specify")
            start = time.perf_counter()
            engine.transition_phase(type_id, "design")
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        # Then median should be under 50ms
        times.sort()
        median = times[len(times) // 2]
        assert median < 50, f"Median transition time {median:.1f}ms exceeds 50ms SLA"

    def test_batch_query_100_features_under_200ms(self, tmp_path) -> None:
        """Performance: batch query of 100 features should complete within 200ms.

        derived_from: dimension:performance_contracts (SLA: batch operation)
        """
        import time

        # Given 100 registered features with workflow rows
        db = _make_db()
        for i in range(100):
            slug = f"{i:03d}-perf-feature"
            tid = _register_feature(db, slug, status="active")
            phase = ["specify", "design", "implement"][i % 3]
            db.create_workflow_phase(tid, workflow_phase=phase)

        engine = WorkflowStateEngine(db, str(tmp_path))

        # When timing list_by_status
        start = time.perf_counter()
        results = engine.list_by_status("active")
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Then under 200ms and correct count
        assert len(results) == 100
        assert elapsed_ms < 200, (
            f"Batch query time {elapsed_ms:.1f}ms exceeds 200ms SLA"
        )


# ---------------------------------------------------------------------------
# TransitionResponse dataclass (Task 1.1)
# ---------------------------------------------------------------------------


class TestTransitionResponse:
    """Tests for the TransitionResponse frozen dataclass."""

    def test_transition_response_construction(self) -> None:
        """TransitionResponse can be constructed with results tuple and degraded bool."""
        r1 = TransitionResult(
            allowed=True, reason="ok", severity=Severity.info, guard_id="g1"
        )
        r2 = TransitionResult(
            allowed=False, reason="blocked", severity=Severity.block, guard_id="g2"
        )
        response = TransitionResponse(results=(r1, r2), degraded=False)
        assert response is not None

    def test_transition_response_frozen(self) -> None:
        """TransitionResponse is frozen -- attributes cannot be reassigned."""
        r1 = TransitionResult(
            allowed=True, reason="ok", severity=Severity.info, guard_id="g1"
        )
        response = TransitionResponse(results=(r1,), degraded=False)
        with pytest.raises(FrozenInstanceError):
            response.degraded = True  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            response.results = ()  # type: ignore[misc]

    def test_transition_response_field_access(self) -> None:
        """TransitionResponse fields are accessible and correct."""
        r1 = TransitionResult(
            allowed=True, reason="ok", severity=Severity.info, guard_id="g1"
        )
        r2 = TransitionResult(
            allowed=False, reason="no", severity=Severity.block, guard_id="g2"
        )
        response = TransitionResponse(results=(r1, r2), degraded=True)
        assert response.results == (r1, r2)
        assert response.degraded is True

    def test_transition_response_results_is_tuple(self) -> None:
        """TransitionResponse.results is a tuple, not a list."""
        r1 = TransitionResult(
            allowed=True, reason="ok", severity=Severity.info, guard_id="g1"
        )
        response = TransitionResponse(results=(r1,), degraded=False)
        assert isinstance(response.results, tuple)

    def test_transition_response_degraded_is_bool(self) -> None:
        """TransitionResponse.degraded is a bool."""
        r1 = TransitionResult(
            allowed=True, reason="ok", severity=Severity.info, guard_id="g1"
        )
        response_normal = TransitionResponse(results=(r1,), degraded=False)
        response_degraded = TransitionResponse(results=(r1,), degraded=True)
        assert isinstance(response_normal.degraded, bool)
        assert isinstance(response_degraded.degraded, bool)
        assert response_normal.degraded is False
        assert response_degraded.degraded is True

    def test_transition_response_empty_results(self) -> None:
        """TransitionResponse can have empty results tuple."""
        response = TransitionResponse(results=(), degraded=False)
        assert response.results == ()
        assert len(response.results) == 0


class TestCheckDbHealth:
    """Tests for _check_db_health() -- DB availability probe."""

    def test_healthy_db_returns_true(self, tmp_path) -> None:
        """A healthy in-memory DB returns True from _check_db_health."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        assert engine._check_db_health() is True

    def test_conn_none_returns_false(self, tmp_path, monkeypatch) -> None:
        """When db._conn is None (defensive guard), returns False."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        monkeypatch.setattr(engine.db, "_conn", None)
        assert engine._check_db_health() is False

    def test_programming_error_returns_false(self, tmp_path, monkeypatch) -> None:
        """When execute raises sqlite3.ProgrammingError (closed DB), returns False."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        class MockConn:
            def execute(self, *a):
                raise sqlite3.ProgrammingError("closed")

        monkeypatch.setattr(engine.db, "_conn", MockConn())
        assert engine._check_db_health() is False

    def test_generic_sqlite_error_returns_false(self, tmp_path, monkeypatch) -> None:
        """When execute raises generic sqlite3.Error, returns False."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        class MockConn:
            def execute(self, *a):
                raise sqlite3.Error("generic error")

        monkeypatch.setattr(engine.db, "_conn", MockConn())
        assert engine._check_db_health() is False
